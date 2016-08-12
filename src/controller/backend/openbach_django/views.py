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


import json
import socket
from functools import wraps
from datetime import datetime

from django.utils import timezone
from django.http import JsonResponse
from django.core.exceptions import ObjectDoesNotExist

from .models import Agent, Installed_Job, Job_Instance
from .models import Statistic_Instance


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
    conductor.send(json.dumps(command).encode())
    recv = conductor.recv(9999)
    result = json.loads(recv.decode())
    returncode = result['returncode']
    del result['returncode']
    conductor.close()
    return result, returncode


@check_post_data
def install_agent(data):
    try:
        address = data['address']
        collector = data['collector']
        username = data['username']
        password = data['password']
        name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'install_agent'

    return conductor_execute(data)


@check_post_data
def uninstall_agent(data):
    try:
        ip_address = data['address']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'uninstall_agent'

    return conductor_execute(data)


@check_post_data
def list_agents(data):
    data['command'] = 'list_agents'

    return conductor_execute(data)


@check_post_data
def status_agents(data):
    try:
        agents_ips = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'status_agents'

    return conductor_execute(data)


@check_post_data
def add_job(data):
    try:
        job_name = data['name']
        job_path = data['path']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'add_job'

    return conductor_execute(data)


@check_post_data
def del_job(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'del_job'

    return conductor_execute(data)


@check_post_data
def list_jobs(data):
    data['command'] = 'list_jobs'

    return conductor_execute(data)


@check_post_data
def get_job_stats(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'get_job_stats'

    return conductor_execute(data)


@check_post_data
def get_job_help(data):
    try:
        job_name = data['name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'get_job_help'

    return conductor_execute(data)


@check_post_data
def install_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'install_jobs'

    return conductor_execute(data)


@check_post_data
def uninstall_jobs(data):
    try:
        addresses = data['addresses']
        names = data['names']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'uninstall_jobs'

    return conductor_execute(data)


@check_post_data
def list_installed_jobs(data):
    try:
        ip_address = data['address']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'list_installed_jobs'

    return conductor_execute(data)


@check_post_data
def status_jobs(data):
    try:
        agents_ips = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'status_jobs'

    return conductor_execute(data)


@check_post_data
def push_file(data):
    try:
        local_path = data['local_path']
        remote_path = data['remote_path']
        agent_ip = data['agent_ip']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'push_file'

    return conductor_execute(data)


@check_post_data
def start_job_instance(data):
    try:
        agent_ip = data['agent_ip']
        job_name = data['job_name']
        instance_args = data['instance_args']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'start_job_instance'

    return conductor_execute(data)


@check_post_data
def stop_job_instance(data):
    try:
        instance_ids = data['instance_ids']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'stop_job_instance'

    return conductor_execute(data)


@check_post_data
def restart_job_instance(data):
    try:
        instance_id = data['instance_id']
        instance_args = data['instance_args']
    except:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'restart_job_instance'

    return conductor_execute(data)


@check_post_data
def status_job_instance(data):
    try:
        instance_id = data['instance_id']
    except:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'status_job_instance'

    return conductor_execute(data)


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

