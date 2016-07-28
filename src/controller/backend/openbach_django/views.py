""" 
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).
   
   
   Copyright © 2016 CNES
   
   
   This file is part of the OpenBACH testbed.
   
   
   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.
   
   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.
   
   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.
   
   
   
   @file     views.py
   @brief    The implementation of the openbach-function
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import os.path
import json
import socket
import yaml
from functools import wraps
from operator import attrgetter
from datetime import datetime

from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

from .models import Agent, Job, Installed_Job, Job_Instance, Watch, Job_Keyword
from .models import Statistic, Required_Job_Argument, Optional_Job_Argument
from .models import Required_Job_Argument_Instance, Optional_Job_Argument_Instance
from .models import Job_Argument_Value, Statistic_Instance


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
            'update_status': agent.update_status.astimezone(timezone.get_current_timezone()),
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
    config_file = '{}.yml'.format(config_prefix)
    try:
        with open(config_file, 'r') as stream:
            try:
                content = yaml.load(stream)
            except yaml.YAMLError:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file}, 404
    except FileNotFoundError:
        return {'msg': 'KO, the configuration file is not present',
                'configuration file': config_file}, 404
    try:
        job_version = content['general']['job_version']
        keywords = content['general']['keywords']
        statistics = content['statistics']
        description = content['general']['description']
        required_args = []
        for arg in content['arguments']['required']:
            required_args.append(arg)
        optional_args = []
        if content['arguments']['optional'] != None:
            for arg in content['arguments']['optional']:
                optional_args.append(arg)
    except KeyError:
        return {'msg': 'KO, the configuration file of the Job is not well '
                'formed', 'configuration file': config_file}, 404
    try:
        with open('{}.help'.format(config_prefix)) as f:
            help = f.read()
    except OSError:
        help = ''

    deleted = False
    try:
        job = Job.objects.get(pk=job_name)
        job.delete()
        deleted = True
    except ObjectDoesNotExist:
        pass

    job = Job(
        name=job_name,
        path=job_path,
        help=help,
        job_version=job_version,
        description=description
    )
    job.save()

    for keyword in keywords:
        job_keyword = Job_Keyword(
            name=keyword
        )
        job_keyword.save()
        job.keywords.add(job_keyword)

    if type(statistics) == list:
        try:
            for statistic in statistics:
                Statistic(
                    name=statistic['name'],
                    job=job,
                    description=statistic['description'],
                    frequency=statistic['frequency']
                ).save()
        except IntegrityError:
            job.delete()
            if deleted:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file, 'warning':
                        'Old Job has been deleted'}, 409
            else:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file}, 409
    elif statistics == None:
        pass
    else:
        job.delete()
        if deleted:
            return {'msg': 'KO, the configuration file of the Job is not well '
                    'formed', 'configuration file': config_file, 'warning':
                    'Old Job has been deleted'}, 409
        else:
            return {'msg': 'KO, the configuration file of the Job is not well '
                    'formed', 'configuration file': config_file}, 409

    rank = 0
    for required_arg in required_args:
        try:
            Required_Job_Argument(
                name=required_arg['name'],
                description=required_arg['description'],
                type=required_arg['type'],
                rank=rank,
                job=job
            ).save()
            rank += 1
        except IntegrityError:
            job.delete()
            if deleted:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file, 'warning':
                        'Old Job has been deleted'}, 409
            else:
                return {'msg': 'KO, the configuration file of the Job is not well '
                        'formed', 'configuration file': config_file}, 409

    for optional_arg in optional_args:
        try:
            Optional_Job_Argument(
                name=optional_arg['name'],
                flag=optional_arg['flag'],
                type=optional_arg['type'],
                description=optional_arg['description'],
                job=job
            ).save()
        except IntegrityError:
            job.delete()
            return {'msg': 'KO, the configuration file of the Job is not well '
                    'formed', 'configuration file': config_file}, 409

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


@check_post_data
def list_jobs(data):
    '''
    list all the Jobs available on the benchmark
    '''
    verbosity = 0
    if 'verbosity' in data:
        verbosity = data['verbosity']
    response = {
        'jobs': []
    }
    for job in Job.objects.all():
        job_info = {
            'name': job.name
        }
        if verbosity > 0:
            job_info['statistics'] = [ stat.name for stat in
                                      job.statistic_set.all()]
        response['jobs'].append(job_info)
    return response, 200


@check_post_data
def get_job_stats(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    verbosity = 0
    if 'verbosity' in data:
        verbosity = data['verbosity']
    try:
        job = Job.objects.get(pk=job_name)
    except ObjectDoesNotExist:
        return {
                'msg': 'This Job isn\'t in the database',
                'job_name': job_name,
        }, 404

    result = {'job_name': job_name , 'statistics': [] }
    for stat in job.statistic_set.all():
        statistic = { 'name': stat.name }
        if verbosity > 0:
            statistic['description'] = stat.description
        if verbosity > 1:
            statistic['frequency'] = stat.frequency
        result['statistics'].append(statistic)

    return result, 200


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
                        local_severity=local_severity)
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
    verbosity = 0
    if 'verbosity' in data:
        verbosity = data['verbosity']
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
        response['installed_jobs'] = []
        for job in installed_jobs:
            job_infos = {
                'name': job.job.name,
                'update_status':
                job.update_status.astimezone(timezone.get_current_timezone()),
            }
            if verbosity > 0:
                job_infos['severity'] = job.severity
                job_infos['default_stat_policy'] = { 'storage':
                                                    job.default_stat_storage,
                                                    'broadcast':
                                                    job.default_stat_broadcast }
            if verbosity > 1:
                job_infos['local_severity'] = job.local_severity
                for statistic_instance in job.statistic_instance_set.all():
                    if 'statistic_instances' not in job_infos:
                        job_infos['statistic_instances'] = []
                    job_infos['statistic_instances'].append({ 'name':
                                                             statistic_instance.stat.name,
                                                             'storage':
                                                             statistic_instance.storage,
                                                             'broadcast':
                                                             statistic_instance.broadcast
                                                             })
            response['installed_jobs'].append(job_infos)
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


def fill_and_launch_job_instance(instance, data, instance_args, restart=False,
                                 launch=True):
    instance.status = "starting ..."
    instance.update_status = timezone.now()

    if 'interval' in data:
        interval = data['interval']
        instance.start_date = timezone.now()
        instance.periodic = True
        instance.save()
        cmd = 'start_job_instance interval {} {}'.format(interval, instance.id)
    else:
        date = data.get('date', 'now')
        if date == 'now':
            instance.start_date = timezone.now()
        else:
            start_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())
            instance.start_date = start_date
        instance.periodic = False
        instance.save()
        cmd = 'start_job_instance date {} {}'.format(date, instance.id)

    if restart:
        cmd = 're{}'.format(cmd)
        instance.required_job_argument_instance_set.all().delete()
        instance.optional_job_argument_instance_set.all().delete()

    for arg_name, arg_values in instance_args.items():
        try:
            argument_instance = Required_Job_Argument_Instance(
                argument=instance.job.job.required_job_argument_set.filter(name=arg_name)[0],
                job_instance=instance
            )
            argument_instance.save()
        except IndexError:
            try:
                argument_instance = Optional_Job_Argument_Instance(
                    argument=instance.job.job.optional_job_argument_set.filter(name=arg_name)[0],
                    job_instance=instance
                )
                argument_instance.save()
            except IndexError:
                return {
                        'msg': 'Argument \'{}\' don\'t match with arguments needed'
                               ' or optional'.format(arg_name),
                }, 400
        for arg_value in arg_values:
            Job_Argument_Value(
                value=arg_value,
                argument_instance=argument_instance
            ).save()

    try:
        instance.check_args()
    except ValueError as e:
        return {
                'msg': 'Arguments given don\'t match with arguments needed',
                'error': e.args[0],
        }, 400

    if launch:
        result = conductor_execute(cmd)
        response = {'msg': result}
        if result == 'OK':
            instance.status = "Started"
            instance.update_status = timezone.now()
            instance.save()
            if not restart:
                response['instance_id'] = instance.id
            return response, 200
        else:
            instance.delete()
            return response, 404
    else:
        return date


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

    return fill_and_launch_job_instance(instance, data, instance_args)


@check_post_data
def stop_job_instance(data):
    try:
        instance_ids = data['instance_ids']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    
    instances = Job_Instance.objects.filter(pk__in=instance_ids)
    date = data.get('date', 'now')
    if date == 'now':
        stop_date = timezone.now()
    else:
        stop_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())

    response = {'msg': 'OK', 'error': []}
    for instance in instances:
        instance.stop_date = stop_date
        instance.save()
        result = conductor_execute('stop_job_instance {} {}'.format(date, instance.id))
        if result == 'OK':
            if stop_date <= timezone.now():
                instance.is_stopped = True
                instance.save()
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

    return fill_and_launch_job_instance(instance, data, instance_args,
                                        restart=True)

    if not instance_args:
        try:
            instance.check_args()
        except ValueError as e:
            return {
                    'msg': 'Arguments given don\'t match with arguments needed',
                    'error': e.args[0],
            }, 400


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


def _build_instance_infos(instance, update, verbosity):
    """Helper function to simplify `list_job_instances`"""
    error_msg = None
    if update:
        result = conductor_execute('update_instance {}'.format(instance.id))
        if result.startswith('KO'):
            error_msg = result[3:]
        instance.refresh_from_db()
    instance_infos = {
            'id': instance.id,
            'arguments': {}
    }
    for required_job_argument in instance.required_job_argument_instance_set.all():
        for value in required_job_argument.job_argument_value_set.all():
            if required_job_argument.argument.name not in instance_infos['arguments']:
                instance_infos['arguments'][required_job_argument.argument.name] = []
            instance_infos['arguments'][required_job_argument.argument.name].append(value.value)
    for optional_job_argument in instance.optional_job_argument_instance_set.all():
        for value in optional_job_argument.job_argument_value_set.all():
            if optional_job_argument.argument.name not in instance_infos['arguments']:
                instance_infos['arguments'][optional_job_argument.argument.name] = []
            instance_infos['arguments'][optional_job_argument.argument.name].append(value.value)
    if verbosity > 0:
        instance_infos['update_status'] = instance.update_status.astimezone(timezone.get_current_timezone())
        instance_infos['status'] = instance.status
    if verbosity > 1:
        instance_infos['start_date'] = instance.start_date.astimezone(timezone.get_current_timezone())
    if verbosity > 2:
        try:
            instance_infos['stop_date'] = instance.stop_date.astimezone(timezone.get_current_timezone())
        except AttributeError:
            instance_infos['stop_date'] = 'Not programmed yet'
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
    verbosity = 0
    if 'verbosity' in data:
        verbosity = data['verbosity'] if data['verbosity'] else 0

    # TODO: see prefetch_related or select_related to avoid
    # hitting the DB once more for each agent in the next loop
    if not agents_ip:
        agents = Agent.objects.all()
    else:
        agents = Agent.objects.filter(pk__in=agents_ip)

    response = { 'instances': [] }
    for agent in agents:
        job_instances_for_agent = { 'address': agent.address, 'installed_jobs':
                                  []}
        for job in agent.installed_job_set.all():
            job_instances_for_job = { 'job_name': job.name, 'instances': [] }
            for job_instance in job.job_instance_set.filter(is_stopped=False):
                job_instances_for_job['instances'].append(_build_instance_infos(job_instance,
                                                                                update,
                                                                                verbosity))
            if job_instances_for_job['instances']:
                job_instances_for_agent['installed_jobs'].append(job_instances_for_job)
        if job_instances_for_agent['installed_jobs']:
            response['instances'].append(job_instances_for_agent)
    return response, 200


@check_post_data
def set_job_log_severity(data):
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
                'msg': 'The Installed_Job rsyslog isn\'t in the database',
                'job_name': 'logs on {}'.format(agent_ip),
        }, 404

    instance = Job_Instance(job=logs_job)
    instance.status = "starting ..."
    instance.update_status = timezone.now()

    date = data.get('date', 'now')
    if date == 'now':
        instance.start_date = timezone.now()
    else:
        start_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())
        instance.start_date = start_date
    instance.periodic = False
    instance.save()
 
    instance_args = { 'job_name': [job_name], 'instance_id': [instance.id] }
    date = fill_and_launch_job_instance(instance, data, instance_args, launch=False)

    result = conductor_execute(
            'set_job_log_severity {} {} {} {}'
            .format(
                date,
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
def set_job_stat_policy(data):
    try:
        agent_ip = data['address']
        job_name = data['job_name']
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

    stat_name = data.get('stat_name', None)
    storage = data.get('storage', None)
    broadcast = data.get('broadcast', None)
    if stat_name != None:
        statistic = installed_job.job.statistic_set.filter(name=stat_name)[0]
        stat = Statistic_Instance.objects.filter(stat=statistic,
                                                 job=installed_job)
        if not stat:
            stat = Statistic_Instance(stat=statistic, job=installed_job)
        else:
            stat = stat[0]
        if storage == None and broadcast == None:
            try:
                stat.delete()
            except AssertionError:
                pass
        else:
            if broadcast != None:
                stat.broadcast = broadcast
            if storage != None:
                stat.storage = storage
            stat.save()
    else:
        if broadcast != None:
            installed_job.broadcast = broadcast
        if storage != None:
            installed_job.storage = storage
    installed_job.save()

    rstat_name = 'rstats_job on {}'.format(agent_ip)
    try:
        rstats_job = Installed_Job.objects.get(pk=rstat_name)
    except ObjectDoesNotExist:
        return {
                'msg': 'The Installed_Job rstats isn\'t in the database',
                'job_name': rstat_name,
        }, 404

    instance = Job_Instance(job=rstats_job)
    instance.status = "starting ..."
    instance.update_status = timezone.now()

    date = data.get('date', 'now')
    if date == 'now':
        instance.start_date = timezone.now()
    else:
        start_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())
        instance.start_date = start_date
    instance.periodic = False
    instance.save()
 
    instance_args = { 'job_name': [job_name], 'instance_id': [instance.id] }
    date = fill_and_launch_job_instance(instance, data, instance_args, launch=False)

    result = conductor_execute(
            'set_job_stat_policy {} {}'
            .format(date, instance.id))
    response = {'msg' : result}
    if result == 'KO':
        instance.delete()
        installed_job.save()
        return response, 404
    instance.status = "Started"
    instance.update_status = timezone.now()
    instance.save()
    return response, 200

