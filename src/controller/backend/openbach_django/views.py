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

from django.http import JsonResponse


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


@check_post_data
def list_job_instances(data):
    try:
        agents_ip = data['addresses']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'list_job_instances'

    return conductor_execute(data)


@check_post_data
def set_job_log_severity(data):
    try:
        agent_ip = data['address']
        job_name = data['job_name']
        severity = data['severity']
    except KeyError:
        return {'msg': 'POST data malformed'}, 400

    data['command'] = 'set_job_log_severity'

    return conductor_execute(data)


@check_post_data
def set_job_stat_policy(data):
    try:
        agent_ip = data['address']
        job_name = data['job_name']
    except KeyError:
        return {'msg': 'POST data malformed'}, 404

    data['command'] = 'set_job_stat_policy'

    return conductor_execute(data)

