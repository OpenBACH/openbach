import os.path
import json
import socket
import ConfigParser
from functools import wraps

from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from .models import Agent, Job, Installed_Job, Instance, Watch


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
        return f(json.loads(data))
    return wrapper


def conductor_execute(command):
    conductor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conductor.connect(('localhost', 1113))
    conductor.send(command.encode())
    result = conductor.recv(1024).decode()
    conductor.close()
    return result


@check_post_data
def add_agent(data):
    try:
        agent_data = {key: data[key] for key in ('address', 'username', 'collector', 'name')}
        password = data['password']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    agent = Agent(**agent_data)
    agent.set_password(password)
    agent.reachable = True
    agent.update_reachable = timezone.now()
    agent.status = 'Installing ...' 
    agent.update_status = timezone.now()
    try:
        agent.save()
    except IntegrityError:
        response_data = {'msg': 'Name of the Agent already used'}
        return JsonResponse(data=response_data, status=409)

    result = conductor_execute('add_agent {}'.format(agent.address))
    response = {'msg': result}
    status = 200
    if result.startswith('KO'):
        agent.delete()
        status = 404
    agent.status = 'Available'
    agent.update_status = timezone.now()
    agent.save()
    return JsonResponse(data=response, status=status)


@check_post_data
def del_agent(data):
    try:
        ip_address = data['address']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        response_data = {
                'msg': 'This Agent isn\'t in the database',
                'address': ip_address,
        }
        return JsonResponse(data=response_data, status=404)

    result = conductor_execute('del_agent {}'.format(agent.address))
    response = {'msg': result}
    status = 404
    if result == 'OK':
        agent.delete()
        status = 200
    return JsonResponse(data=response, status=status)


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

    return JsonResponse(data=response, status=200)


@check_post_data
def add_job(data):
    try:
        job_name = data['name']
        job_path = data['path']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    config_prefix = os.path.join(job_path, 'files', job_name)
    config = ConfigParser.ConfigParser()
    config.read('{}.cfg'.format(config_prefix))
    job_args = config.get(job_name, 'required').split()
    optional_args = bool(config.get(job_name, 'optional'))
    try:
        with open('{}.help'.format(config_prefix)) as f:
            help = f.read()
    except FileNotFoundError:
        help = ''

    Job(
        name=job_name,
        path=job_path,
        nb_args=len(job_args),
        optional_args=optional_args,
        help=help
    ).save()

    return JsonResponse(data={'msg', 'OK'}, status=200)


@check_post_data
def del_job(data):
    try:
        job_name = data['name']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        response_data = {
                'msg': 'This Job isn\'t in the database',
                'job_name': job_name,
        }
        return JsonResponse(data=response_data, status=404)

    job.delete()
    return JsonResponse(data={'msg': 'OK'}, status=200)


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
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        response_data = {
                'msg': 'This Job isn\'t in the database',
                'job_name': job_name,
        }
        return JsonResponse(data=response_data, status=404)

    response_data = {'job_name': job_name, 'help': job.help}
    return JsonResponse(data=response_data, status=200)


@check_pots_data
def install_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    severity = data.get('severity', 4)
    local_severity = data.get('local_severity', 4)
    agents = Agent.objects.filter(pk__in=addresses)
    jobs = Job.objects.filter(pk__in=names)

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
        response = {'msg': 'OK'}
        status = 200
    else:
        response = {'msg': 'At least one of the installation have failed'}
        status = 404
    return JsonResponse(data=response, status=status)


@check_post_data
def uninstall_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

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
        response = {'msg': error_msg}
        status = 404
    else:
        response = {'msg': 'OK'}
        status = 200
    return JsonResponse(data=response, status=status)


@check_post_data
def list_installed_jobs(data):
    '''
    list all the Jobs installed on an Agent
    '''
    try:
        ip_address = data['address']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

    update = data.get('update', False)
    try:
        agent = Agent.objects.get(pk=ip_address)
    except ObjectDoesNotExist:
        response_data = {
            'msg': 'This Agent isn\'t in the database',
            'address': ip_address,
        }
        return JsonResponse(data=response_data, status=404)

    response = {'errors': [], 'agent': agent.address}
    if update:
        result = conductor_execute('update_jobs {}'.format(agent.address))
        if result.startswith('KO 1'):
            response_data['errors'].append({'error': result[5:]})
        elif result.startswith('KO 2'):
            response_data['errors'].append({
                'jobs_name': results[5:],
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
        return JsonResponse(data=response, status=200)


@check_post_data
def push_file(data):
    try:
        local_path = data['local_path']
        remote_path = data['remote_path']
        agent_ip = data['agent_ip']
    except KeyError:
        response_data = {'msg': 'POST data malformed'}
        return JsonResponse(data=response_data, status=400)

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
        return JsonResponse(data=response_data, status=200)
    return JsonResponse(data=response_data, status=404)


def start_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agent_ip = data['agent_ip']
        job_name = data['job_name']
        instance_args = data['instance_args']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    name = job_name + " on " + agent_ip
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Installed_Job isn't in the database",
                         'job_name': name}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
        date_interval = 'date'
    elif 'interval' in data:
        interval = data['interval']
        date_interval = 'interval'
    else:
        date = 'now'
        date_interval = 'date'
    instance = Instance(job=installed_job)
    for i in range(len(instance_args)):
        instance.args += str(instance_args[i])
    if not instance.check_args():
        response_data = {'msg': "Arguments given don't match with arguments "
                         "needed"}
        return JsonResponse(data=response_data, status=404)
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()
    instance_id = str(instance.id)
    cmd = "start_instance "
    if date_interval == 'date':
        cmd += "date " + str(date)
    else:
        cmd += "interval " + str(interval)
    cmd += " " + instance_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        response_data['instance_id'] = instance_id
        return JsonResponse(data=response_data, status=200)
    else:
        instance.delete()
        return JsonResponse(data=response_data, status=404)


def stop_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_ids = data['instance_ids']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    instances = {}
    response_data = {}
    for instance_id in instance_ids:
        try:
            instance = Instance.objects.get(pk=instance_id)
            instances[instance_id] = instance
        except ObjectDoesNotExist:
            response_data['errors'] = "These Instances aren't in the database"
            if 'instance_ids' not in response_data:
                response_data['instance_ids'] = []
            response_data['instance_id'].append(instance_id)
            return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
    else:
        date = "now"
    status = 200
    response_data['error'] = []
    for instance_id in instance_ids:
        cmd = "stop_instance " + date + " " + instance_id
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(('localhost', 1113))
        s.send(cmd)
        r = s.recv(1024)
        s.close()
        if r.split()[0] == 'OK':
            instances[instance_id].delete()
        else:
            status = 404
            response_data['msg'] = "Some went wrong"
            response_data['error'].append({'msg': r, 'instance': instance_id})
    if 'msg' not in response_data:
        response_data['msg'] = "OK"
    return JsonResponse(data=response_data, status=status)


def restart_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_id = data['instance_id']
        instance_args = data['instance_args']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        instance = Instance.objects.get(pk=instance_id)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Instance isn't in the database",
                         'instance_id': instance_id}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
        date_interval = 'date'
    elif 'interval' in data:
        interval = data['interval']
        date_interval = 'interval'
    else:
        date = 'now'
        date_interval = 'date'
    if len(instance_args) != 0:
        instance.args = " ".join(instance_args)
        if not instance.check_args():
            response_data = {'msg': "Arguments given don't match with arguments "
                             "needed"}
            return JsonResponse(data=response_data, status=404)
        instance.save()
    instance_id = str(instance.id)
    cmd = "restart_instance "
    if date_interval == 'date':
        cmd += "date " + date
    else:
        cmd += "interval " + interval
    cmd += " " + instance_id
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        return JsonResponse(data=response_data, status=200)
    else:
        # TODO delete or keep the instance in the database ?
        return JsonResponse(data=response_data, status=404)


def status_agents(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    if 'addresses' not in data:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    agents_ip = data['addresses']
    cmd = "status_agents " + ' '.join(agents_ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response = r.split()
    if response[0] == 'OK':
        response_data = {'msg': r}
        return JsonResponse(data=response_data, status=200)
    else:
        response_data = {'msg': "At least one of the Agents isn't in the"
                         "database", 'addresses': response}
        return JsonResponse(data=response_data, status=404)

def status_jobs(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    if 'addresses' not in data:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    agents_ip = data['addresses']
    cmd = "status_jobs " + ' '.join(agents_ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response = r.split()
    if response[0] == 'OK':
        response_data = {'msg': r}
        return JsonResponse(data=response_data, status=200)
    else:
        response_data = {'msg': "At least one of the Agents isn't in the"
                         "database", 'addresses': response}
        return JsonResponse(data=response_data, status=404)


def status_instance(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        instance_id = data['instance_id']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    try:
        instance = Instance.objects.get(pk=instance_id)
        installed_job = instance.job
    except ObjectDoesNotExist:
        if 'agent_ip' not in data or 'job_name' not in data:
            response_data = {'msg': "POST data malformed"}
            return JsonResponse(data=response_data, status=404)
        else:
            agent_ip = data['agent_ip']
            job_name = data['job_name']
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Agent isn't in the database", 'address':
                                 agent_ip}
                return JsonResponse(data=response_data, status=404)
            try:
                job = Job.objects.get(pk=job_name)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Job isn't in the database", 'job_name':
                                 job_name}
                return JsonResponse(data=response_data, status=404)
            name = job.name + " on " + agent.address
            try:
                installed_job = Installed_Job.objects.get(pk=name)
            except ObjectDoesNotExist:
                response_data = {'msg': "This Installed_Job isn't in the database",
                                 'job_name': name}
                return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        try:
            Watch.objects.get(pk=instance_id)
            response_data = {'msg': "A Watch already exist in the database"}
            return JsonResponse(data=response_data, status=404)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0) 
        watch_type = 'date'
        cmd_type = "date " + str(data['date']) + " "
    elif 'interval' in data:
        try:
            watch = Watch.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id)
        watch_type = 'interval'
        interval = int(data['interval'])
        watch.interval = interval
        cmd_type = "interval " + str(interval) + " "
    elif 'stop' in data:
        try:
            watch = Watch.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0)
        watch_type = 'stop'
        cmd_type = "stop " + str(data['stop']) + " "
    else:
        try:
            Watch.objects.get(pk=instance_id)
            response_data = {'msg': "A Watch already exist in the database"}
            return JsonResponse(data=response_data, status=404)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id,
                          interval=0)
        watch_type = 'date'
        cmd_type = "date now "
    watch.save()
    cmd = "status_instance " + cmd_type +  str(instance_id)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg': r}
    if r.split()[0] == 'OK':
        if watch_type != 'interval':
            watch.delete()
        return JsonResponse(data=response_data, status=200)
    else:
        watch.delete()
        return JsonResponse(data=response_data, status=404)


def list_instances(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agents_ip = data['addresses']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    if 'update' in data:
        update = data['update']
    else:
        update = False
    response_data = {}
    response_data['instances'] = list()
    if len(agents_ip) == 0:
        agents = Agent.objects.all()
        for agent in agents:
            agents_ip.append(agent.address)
    for ip_address in agents_ip:
        try:
            agent = Agent.objects.get(pk=ip_address)
        except ObjectDoesNotExist:
            response_data = {'msg': "At least one of the Agents isn't in the"
                             " database", 'address': ip_address}
            return JsonResponse(data=response_data, status=404)
        else:
            instances_for_agent = {'address': ip_address}
            instances_for_agent['installed_job'] = list()
            for installed_job in agent.installed_job_set.get_queryset().iterator():
                installed_job_json = {'job_name': installed_job.job.name}
                installed_job_json['instances'] = list()
                for instance in installed_job.instance_set.get_queryset().iterator():
                    error_msg = ''
                    if update:
                        cmd = "update_instance " + str(instance.id)
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.connect(('localhost', 1113))
                        s.send(cmd)
                        r = s.recv(1024)
                        s.close()
                        return_msg = r.split()
                        if return_msg[0] == 'KO':
                            error_msg = ' '.join(return_msg[1:])
                        instance.refresh_from_db()
                    instance_json = {'id': instance.id, 'arguments': instance.args,
                                     'update_status': instance.update_status, 'status':
                                     instance.status}
                    if error_msg != '':
                        instance_json['error'] = error_msg
                    installed_job_json['instances'].append(instance_json)
                instances_for_agent['installed_job'].append(installed_job_json)
        response_data['instances'].append(instances_for_agent)
    return JsonResponse(response_data, status=200)


def update_job_log_severity(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agent_ip = data['address']
        job_name = data['job_name']
        severity = data['severity']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    if 'date' in data:
        date = data['date']
    else:
        date = 'now'
    name = job_name + " on " + agent_ip
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Installed_Job isn't in the database",
                         'job_name': name}
        return JsonResponse(data=response_data, status=404)
    try:
        logs_job = Installed_Job.objects.get(pk="rsyslog_job on " + agent_ip)
    except ObjectDoesNotExist:
        response_data = {'msg': "The Logs Job isn't in the database",
                         'job_name': "logs on " + agent_ip}
        return JsonResponse(data=response_data, status=404)
    if 'local_severity' in data:
        local_severity = data['local_severity']
    else:
        local_severity = installed_job.local_severity
    instance = Instance(job=logs_job)
    instance.args = ""
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()
    instance.args = job_name + " " + str(instance.id)
    if not instance.check_args():
        response_data = {'msg': "Arguments given don't match with arguments "
                         "needed"}
        return JsonResponse(data=response_data, status=404)
    instance.save()
    cmd = "update_job_log_severity " + date + " " + str(instance.id) + " "
    cmd += str(severity) + " " + str(local_severity)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg' : r}
    if r.split()[0] == 'KO':
        instance.delete()
        return JsonResponse(data=response_data, status=404)
    return JsonResponse(data=response_data, status=200)


def update_job_stat_policy(request):
    if request.method != 'POST':
        response_data = {'msg': "Only POST method are accepted"}
        return JsonResponse(data=response_data, status=404)
    data = json.loads(request.POST['data'])
    try:
        agent_ip = data['address']
        job_name = data['job_name']
        accept_stats = data['accept_stats']
        deny_stats = data['deny_stats']
    except:
        response_data = {'msg': "POST data malformed"}
        return JsonResponse(data=response_data, status=404)
    if 'default_policy' in data:
        default_policy = bool(data['default_policy'])
    else:
        default_policy = True
    if 'date' in data:
        date = data['date']
    else:
        date = 'now'
    name = job_name + " on " + agent_ip
    try:
        installed_job = Installed_Job.objects.get(pk=name)
    except ObjectDoesNotExist:
        response_data = {'msg': "This Installed_Job isn't in the database",
                         'job_name': name}
        return JsonResponse(data=response_data, status=404)
    old_default_policy = installed_job.stats_default_policy
    old_accept_stats = installed_job.accept_stats
    old_deny_stats = installed_job.deny_stats
    installed_job.stats_default_policy = default_policy
    installed_job.accept_stats = ' '.join(accept_stats)
    installed_job.deny_stats = ' '.join(deny_stats)
    installed_job.save()
    try:
        rstats_job = Installed_Job.objects.get(pk="rstats_job on " + agent_ip)
    except ObjectDoesNotExist:
        response_data = {'msg': "The Rstats Job isn't in the database",
                         'job_name': "rstats_job on " + agent_ip}
        return JsonResponse(data=response_data, status=404)
    instance = Instance(job=rstats_job)
    instance.args = ""
    instance.status = "starting ..."
    instance.update_status = timezone.now()
    instance.save()
    instance.args = job_name + " " + str(instance.id)
    if not instance.check_args():
        response_data = {'msg': "Arguments given don't match with arguments "
                         "needed"}
        return JsonResponse(data=response_data, status=404)
    instance.save()
    cmd = "update_job_stat_policy " + date + " " + str(instance.id)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 1113))
    s.send(cmd)
    r = s.recv(1024)
    s.close()
    response_data = {'msg' : r}
    if r.split()[0] == 'KO':
        instance.delete()
        installed_job.stats_default_policy = old_default_policy
        installed_job.accept_stats = old_accept_stats
        installed_job.deny_stats = old_deny_stats
        installed_job.save()
        return JsonResponse(data=response_data, status=404)
    return JsonResponse(data=response_data, status=200)


