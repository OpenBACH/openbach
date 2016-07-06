import os.path
import json
import socket
from configparser import ConfigParser
from functools import wraps
from operator import attrgetter

from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from .models import Agent, Job, Installed_Job, Job_Instance, Watch


def check_post_data(f):
    @wraps(f)
    def wrapper(request):
        if request.method != 'POST':
            response = {'msg': 'Only POST methods are accepted'}
            return JsonResponse(data=response, status=405)
        try:
            data = request.POST['data']
        except KeyError:
            response = {'msg': '"data" payload missing'}
            return JsonResponse(data=response, status=400)
        response, status = f(json.loads(data))
        return JsonResponse(data=response, status=status)
    return wrapper


def conductor_execute(command):
    conductor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conductor.connect(('localhost', 1113))
    conductor.send(command.encode())
    result = conductor.recv(1024).decode()
    conductor.close()
    return result


@check_post_data
def install_agent(data):
    list_default_jobs = '/opt/openbach-controller/install_agent/list_default_jobs.txt'
    try:
        agent_data = {key: data[key] for key in ('address', 'username', 'collector', 'name')}
        password = data['password']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    agent = Agent(**agent_data)
    agent.set_password(password)
    agent.reachable = True
    agent.update_reachable = timezone.now()
    agent.status = 'Installing ...' 
    agent.update_status = timezone.now()
    try:
        agent.save()
    except IntegrityError:
        return {'msg': 'Name of the Agent already used'}, 409

    result = conductor_execute('install_agent {}'.format(agent.address))
    response = {'msg': result}
    if result.startswith('KO'):
        agent.delete()
        return response, 404
    agent.status = 'Available'
    agent.update_status = timezone.now()
    agent.save()
    # Recuperer la liste des jobs a installer
    list_jobs = []
    with open(list_default_jobs) as f:
        for line in f:
            list_jobs.append(line.rstrip('\n'))
    # Installer les jobs
    results = internal_install_jobs([agent.address], list_jobs)
    if results[1] != 200:
        response['warning'] = 'At least one of the default Jobs installation have failed'
    elif 'warning' in results:
        response['warning'] = results['warning']
        response['unknown Jobs'] = results['unknown Jobs']

    return response, 200


@check_post_data
def uninstall_agent(data):
    try:
        ip_address = data['address']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Agent isn\'t in the database',
                'address': ip_address,
        }, 404

    result = conductor_execute('uninstall_agent {}'.format(agent.address))
    response = {'msg': result}
    if result == 'OK':
        agent.delete()
        return response, 200
    return response, 404


@check_post_data
def list_agents(data):
    agents = Agent.objects.all()
    update = data.get('update', False)
    response = {}
    if update:
        for agent in agents:
            if agent.reachable and agent.update_status < agent.update_reachable:
                result = conductor_execute('update_agent {}'.format(agent.address))
                if result.startswith('KO'):
                    response.setdefault('errors', []).append({
                        'agent_ip': agent.address,
                        'error': result[3:],
                    })
            # Moved it here to avoid extra checks in the next loop
            # Don't really know if it is OK
            agent.refresh_from_db()

    response['agents'] = [
        {
            'address': agent.address,
            'status': agent.status,
            'update_status': agent.update_status,
            'name': agent.name,
        } for agent in agents]

    return response, 200


@check_post_data
def add_job(data):
    try:
        job_name = data['name']
        job_path = data['path']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    config_prefix = os.path.join(job_path, 'files', job_name)
    config = ConfigParser()
    config_file = '{}.cfg'.format(config_prefix)
    try:
        config.read_file(open(config_file))
    except FileNotFoundError:
        return {'msg': 'KO, the configuration file is not present',
                'configuration file': config_file}, 404
    try:
        job = config[job_name]
    except KeyError:
        return {'msg': 'KO, the configuration file of the Job is not well '
                'formed', 'configuration file': config_file}, 404
    job_args = job['required'].split()
    optional_args = job.getboolean('optional')
    try:
        with open('{}.help'.format(config_prefix)) as f:
            help = f.read()
    except OSError:
        help = ''

    Job(
        name=job_name,
        path=job_path,
        nb_args=len(job_args),
        optional_args=optional_args,
        help=help
    ).save()

    return {'msg': 'OK'}, 200


@check_post_data
def del_job(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Job isn\'t in the database',
                'job_name': job_name,
        }, 404

    job.delete()
    return {'msg': 'OK'}, 200


def list_jobs_url(request):
    dispatch = {
        'GET': list_jobs,
        'POST': list_installed_jobs,
    }

    try:
        method = dispatch[request.method]
    except KeyError:
        list_methods = ' or '.join(dispatch.keys())
        response = {'msg': 'Only {} methods are accepted'.format(list_methods)}
        return JsonResponse(data=response, status=405)
    else:
        return method(request)


# Should be called only by list_jobs_url => method already verified
def list_jobs(request):
    '''
    list all the Jobs available on the benchmark
    '''
    response = {
        'jobs': [job.name for job in Job.objects.all()],
    }
    return JsonResponse(data=response, status=200)


@check_post_data
def get_job_help(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Job isn\'t in the database',
                'job_name': job_name,
        }, 404

    return {'job_name': job_name, 'help': job.help}, 200


@check_post_data
def install_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    severity = data.get('severity', 4)
    local_severity = data.get('local_severity', 4)

    return internal_install_jobs(addresses, names, severity, local_severity)


def internal_install_jobs(addresses, names, severity=4, local_severity=4):
    agents = Agent.objects.filter(pk__in=addresses)
    no_agent = set(addresses) - set(map(attrgetter('address'), agents))
    
    jobs = Job.objects.filter(pk__in=names)
    no_job = set(names) - set(map(attrgetter('name'), jobs))
    
    if no_job or no_agent:
        warning = 'At least one of the Agents or one of the Jobs is unknown to'
        warning += ' the Controller'
    else:
        warning = False

    success = True
    for agent in agents:
        for job in jobs:
            result = conductor_execute('install_job {} "{}"'.format(agent.address, job.name))
            if result == 'OK':
                installed_job = Installed_Job(
                        agent=agent, job=job,
                        severity=severity,
                        local_severity=local_severity,
                        stats_default_policy=True,
                        accept_stats="",
                        deny_stats="")
                installed_job.set_name()
                installed_job.update_status = timezone.now()
                installed_job.save()
            else:
                success = False

    if success:
        if warning:
            result = {'msg': 'OK', 'warning': warning, 'unknown Agents':
                      list(no_agent), 'unknown Jobs': list(no_job)}, 200
            return result
        else:
            return {'msg': 'OK'}, 200
    else:
        if warning:
            return {'msg': 'At least one of the installation have failed',
                    'warning': warning, 'unknown Agents': list(no_agent),
                    'unknown Jobs': list(no_job)}, 404
        else:
            return {'msg': 'At least one of the installation have failed'}, 404


@check_post_data
def uninstall_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    agents = Agent.objects.filter(pk__in=addresses)
    jobs = Job.objects.filter(pk__in=names)

    error_msg = []
    for agent in agents:
        for job in jobs:
            installed_job_name = '{} on {}'.format(job, agent)
            try:
                installed_job = Installed_Job.objects.get(pk=installed_job_name)
            except ObjectDoesNotExist:
                error_msg.append({
                    'error': 'The no job installed in the database',
                    'job_name': installed_job_name,
                })
                continue

            result = conductor_execute('uninstall_job {} "{}"'.format(agent.address, job.name))
            if result == 'OK':
                installed_job.delete()
            else:
                error_msg.append({
                    'error': 'Failed to uninstall a job',
                    'job_name': installed_job_name,
                })

    if error_msg:
        return {'msg': error_msg}, 404
    else:
        return {'msg': 'OK'}, 200


@check_post_data
def list_installed_jobs(data):
    '''
    list all the Jobs installed on an Agent
    '''
    try:
        ip_address = data['address']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    update = data.get('update', False)
    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        return {
            'msg': 'This Agent isn\'t in the database',
            'address': ip_address,
        }, 404

    response = {'errors': [], 'agent': agent.address}
    if update:
        result = conductor_execute('update_jobs {}'.format(agent.address))
        if result.startswith('KO 1'):
            response['errors'].append({'error': result[5:]})
        elif result.startswith('KO 2'):
            response['errors'].append({
                'jobs_name': result[5:],
                'error': 'These Jobs aren\'t in the Job list of the Controller',
            })

    try:
        installed_jobs = agent.installed_job_set.all()
    except (KeyError, Installed_Job.DoesNotExist):
        response['installed_jobs'] = []
    else:
        response['installed_jobs'] = [
            {
                'name': job.job.name,
                'update_status': job.update_status,
            } for job in installed_jobs
        ]
    finally:
        return response, 200


@check_post_data
def push_file(data):
    try:
        local_path = data['local_path']
        remote_path = data['remote_path']
        agent_ip = data['agent_ip']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    try:
        agent = Agent.objects.get(pk=agent_ip)
    except ObjectDoesNotExist:
        response_data = {
            'msg': 'This Agent isn\'t in the database',
            'address': agent_ip,
        }

    result = conductor_execute('push_file {} {} {}'.format(local_path, remote_path, agent_ip))
    response_data = {'msg': result}
    if result == 'OK':
        return response_data, 200
    return response_data, 404


@check_post_data
def start_job_instance(data):
    try:
        agent_ip = data['agent_ip']
        job_name = data['job_name']
        instance_args = data['instance_args']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    name = '{} on {}'.format(job_name, agent_ip)
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Installed_Job isn\'t in the database',
                'job_name': name,
        }, 404

    instance = Job_Instance(job=installed_job)
    instance.args = ' '.join(instance_args)
    try:
        instance.validate_args_len()  # Maybe use instance.set_arguments(instance_args) instead
    except ValueError:
        return {
                'msg': 'Arguments given don\'t match with arguments needed',
        }, 400

    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()

    if 'interval' in data:
        cmd = 'start_job_instance interval {} {}'.format(data['interval'], instance.id)
    else:
        cmd = 'start_job_instance date {} {}'.format(data.get('date', 'now'), instance.id)

    result = conductor_execute(cmd)
    response = {'msg': result}
    if result == 'OK':
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        response['instance_id'] = instance.id
        return response, 200
    else:
        instance.delete()
        return response, 404


@check_post_data
def stop_job_instance(data):
    try:
        instance_ids = data['instance_ids']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    
    instances = Job_Instance.objects.filter(pk__in=instance_ids)
    date = data.get('date', 'now')

    response = {'msg': 'OK', 'error': []}
    for instance in instances:
        result = conductor_execute('stop_job_instance {} {}'.format(date, instance.id))
        if result == 'OK':
            instance.delete()
        else:
            response['msg'] = 'Something went wrong'
            response['error'].append({'msg': result, 'instance': instance.id})

    if response['error']:
        return response, 404
    else:
        return response, 200


@check_post_data
def restart_job_instance(data):
    try:
        instance_id = data['instance_id']
        instance_args = data['instance_args']
    except:
        return {'msg': 'POST data malformed'}, 400

    try:
        instance = Job_Instance.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Job Instance isn\'t in the database',
                'instance_id': instance_id,
        }, 404

    # TODO: keep it consistent with start_job_instance
    if not instance_args:
        instance.args = ' '.join(instance_args)
        try:
            instance.validate_args_len()
        except ValueError:
            return {
                    'msg': 'Arguments given don\'t match with arguments needed',
            }, 400

        instance.save()

    if 'interval' in data:
        cmd = 'restart_job_instance interval {} {}'.format(data['interval'], instance.id)
    else:
        cmd = 'restart_job_instance date {} {}'.format(data.get('date', 'now'), instance.id)

    result = conductor_execute(cmd)
    response = {'msg': result}
    if result == 'OK':
        return response, 200
    else:
        # TODO delete or keep the instance in the database ?
        return response, 404


@check_post_data
def status_agents(data):
    try:
        agents_ips = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    result = conductor_execute('status_agents {}'.format(' '.join(agents_ips)))
    if result == 'OK':
        return {'msg': result}, 200
    else:
        return {
                'msg': 'At least one of the Agents isn\'t in the database',
                'addresses': result,
        }, 404


@check_post_data
def status_jobs(data):
    try:
        agents_ips = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    result = conductor_execute('status_jobs {}'.format(' '.join(agents_ips)))
    if result == 'OK':
        return {'msg': result}, 200
    else:
        return {
                'msg': 'At least one of the Agents isn\'t in the database',
                'addresses': result,
        }, 404


@check_post_data
def status_job_instance(data):
    try:
        instance_id = data['instance_id']
    except:
        return {'msg': 'POST data malformed'}, 400

    try:
        instance = Job_Instance.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        # User didn't specify a valid instance, try to get it from
        # the agent ip and job name provided, if any
        try:
            agent_ip = data['agent_ip']
            job_name = data['job_name']
        except KeyError:
            return {'msg': 'POST data malformed'}, 400

        try:
            agent = Agent.objects.get(pk=agent_ip)
        except ObjectDoesNotExist:
            return {
                    'msg': 'This Agent isn\'t in the database',
                    'address': agent_ip,
            }, 404

        try:
            job = Job.objects.get(pk=job_name)
        except ObjectDoesNotExist:
            return {
                    'msg': 'This Job isn\'t in the database',
                    'job_name': job_name,
            }, 404

        name = '{} on {}'.format(job.name, agent.address)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            return {
                    'msg': 'This Installed_Job isn\'t in the database',
                     'job_name': name,
            }, 404
    else:
        installed_job = instance.job

    try:
        watch = Watch.objects.get(pk=instance_id)
        if 'interval' not in data and 'stop' not in data:
            return {'msg': 'A Watch already exists in the database'}, 400
    except ObjectDoesNotExist:
        watch = Watch(job=installed_job, instance_id=instance_id, interval=0)

    should_delete_watch = True
    if 'interval' in data:
        should_delete_watch = False
        interval = int(data['interval'])
        watch.interval = interval
        cmd = 'status_job_instance interval {} {}'.format(interval, instance_id)
    elif 'stop' in data:
        cmd = 'status_job_instance stop {} {}'.format(data['stop'], instance_id)
    else:
        cmd = 'status_job_instance date {} {}'.format(data.get('date', 'now'), instance_id)
    watch.save()

    result = conductor_execute(cmd)
    response = {'msg': result}
    if result == 'OK':
        if should_delete_watch:
            watch.delete()
        return response, 200
    else:
        watch.delete()
        return response, 404


def _build_instance_infos(instance, update):
    """Helper function to simplify `list_job_instances`"""
    error_msg = None
    if update:
        result = conductor_execute('update_instance {}'.format(instance.id))
        if result.startswith('KO'):
            error_msg = result[3:]
        instance.refresh_from_db()
    instance_infos = {
            'id': instance.id,
            'arguments': instance.args,
            'update_status': instance.update_status,
            'status': instance.status,
    }
    if error_msg is not None:
        instance_infos['error'] = error_msg
    return instance_infos


@check_post_data
def list_job_instances(data):
    try:
        agents_ip = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    update = data.get('update', False)

    # TODO: see prefetch_related or select_related to avoid
    # hitting the DB once more for each agent in the next loop
    if not agents_ip:
        agents = Agent.objects.all()
    else:
        agents = Agent.objects.filter(pk__in=agents_ip)

    response = {'instances': [
        {
            'address': agent.address,
            'installed_job': [
                {
                    'job_name': j.job.name,
                    'instances': [
                        _build_instance_infos(i, update)
                        for i in j.job_instance_set.all()
                    ],
                } for j in agent.installed_job_set.all()
            ],
        } for agent in agents
    ]}
    return response, 200


@check_post_data
def update_job_log_severity(data):
    try:
        agent_ip = data['address']
        job_name = data['job_name']
        severity = data['severity']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    name = '{} on {}'.format(job_name, agent_ip)
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Installed_Job isn\'t in the database',
                 'job_name': name,
        }, 404

    try:
        logs_job = Installed_Job.objects.get(pk='rsyslog_job on {}'.format(agent_ip))
    except ObjectDoesNotExist:
        return {
                'msg': 'The Logs Job isn\'t in the database',
                'job_name': 'logs on {}'.format(agent_ip),
        }, 404

    instance = Job_Instance(job=logs_job)
    instance.args = ''
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()
    instance.args = '{} {}'.format(job_name, instance.id)
    try:
        instance.validate_args_len()
    except ValueError:
        return {'msg', 'Arguments given don\'t match with arguments needed'}, 400
    instance.save()

    result = conductor_execute(
            'update_job_log_severity {} {} {} {}'
            .format(
                data.get('date', 'now'),
                instance.id, severity,
                data.get('local_severity', installed_job.local_severity)))
    response = {'msg' : result}
    if result == 'KO':
        instance.delete()
        return response, 404
    instance.status = "Started"
    instance.update_status = timezone.now()
    instance.save()
    return response, 200


@check_post_data
def update_job_stat_policy(data):
    try:
        agent_ip = data['address']
        job_name = data['job_name']
        accept_stats = data['accept_stats']
        deny_stats = data['deny_stats']
    except KeyError:
        return {'msg': 'POST data malformed'}, 404

    name = '{} on {}'.format(job_name, agent_ip)
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Installed_Job isn\'t in the database',
                'job_name': name,
        }, 404

    old_default_policy = installed_job.stats_default_policy
    old_accept_stats = installed_job.accept_stats
    old_deny_stats = installed_job.deny_stats
    installed_job.stats_default_policy = bool(data.get('default_policy', True))
    installed_job.accept_stats = ' '.join(accept_stats)
    installed_job.deny_stats = ' '.join(deny_stats)
    installed_job.save()

    rstat_name = 'rstats_job on {}'.format(agent_ip)
    try:
        rstats_job = Installed_Job.objects.get(pk=rstat_name)
    except ObjectDoesNotExist:
        return {
                'msg': 'The Rstats Job isn\'t in the database',
                'job_name': rstat_name,
        }, 404

    instance = Job_Instance(job=rstats_job)
    instance.args = '{} {}'.format(job_name, instance.id)
    try:
        instance.validate_args_len()
    except ValueError:
        return {'msg': 'Arguments given don\'t match with arguments needed'}, 400
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()

    result = conductor_execute(
            'update_job_stat_policy {} {}'
            .format(data.get('date', 'now'), instance.id))
    response = {'msg' : result}
    if result == 'KO':
        instance.delete()
        installed_job.stats_default_policy = old_default_policy
        installed_job.accept_stats = old_accept_stats
        installed_job.deny_stats = old_deny_stats
        installed_job.save()
        return response, 404
    instance.status = "Started"
    instance.update_status = timezone.now()
    instance.save()
    return response, 200

