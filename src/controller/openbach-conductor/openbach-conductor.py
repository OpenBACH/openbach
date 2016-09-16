#!/usr/bin/env python3

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
   
   
   
   @file     openbach-conductor.py
   @brief    The Conductor
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import os
import socket
import shlex
import threading
import subprocess
import yaml
import getpass
import requests
import json
import parse
from queue import Queue
from operator import attrgetter
from datetime import datetime
from contextlib import contextmanager

import sys
sys.path.insert(0, '/opt/openbach-controller/backend')
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()

from django.utils import timezone
from django.db import IntegrityError
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from openbach_django.models import *


_SEVERITY_MAPPING = {
    0: 3,   # Error
    1: 4,   # Warning
    2: 6,   # Informational
    3: 7,   # Debug
}


def convert_severity(severity):
    return _SEVERITY_MAPPING.get(severity, 8)


class WaitingQueueManager:
    __shared_state = {}  # Borg pattern

    def __init__(self, init=False):
        self.__dict__ = self.__class__.__shared_state
        
        if init:
            self.waiting_queues = {}
            self.mutex = threading.Lock()

    def __enter__(self):
        self.mutex.acquire()
        return self.waiting_queues

    def __exit__(self, t, v, tb):
        self.mutex.release()


class PlaybookBuilder():
    def __init__(self, path_to_build, path_src):
        self.path_to_build = path_to_build
        self.path_src = path_src

    def _build_helper(self, instance_type, playbook, extra_vars, extra_vars_filename):
        for key, value in extra_vars.items():
            print(key, value, file=extra_vars_filename)

        if instance_type is not None:
            print('    - include: {}{}.yml'
                      .format(self.path_src, instance_type),
                  file=playbook)

        return bool(instance_type)

    def write_hosts(self, address, host_filename='/tmp/openbach_hosts'):
        with open(host_filename, 'w') as hosts:
            print('[Agents]', file=hosts)
            print(address, file=hosts)

    def write_agent(self, address, agent_filename='/tmp/openbach_agents'):
        with open(agent_filename, 'w') as agents:
            print('agents:', file=agents)
            print('  -', address, file=agents)

    @contextmanager
    def playbook_file(self, filename):
        file_name = os.path.join(self.path_to_build, '{}.yml'.format(filename))
        with open(file_name, 'w') as playbook:
            print('---', file=playbook)
            print(file=playbook)
            print('- hosts: Agents', file=playbook)
            print('  tasks:', file=playbook)
            yield playbook

    @contextmanager
    def extra_vars_file(self, filename='/tmp/openbach_extra_vars'):
        with open(filename, 'w') as extra_vars:
            yield extra_vars

    def build_start(self, job_name, instance_id, job_args, date, interval,
                    playbook_handle, extra_vars_handle):
        instance = 'start_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'job_options:': job_args,
        }

        if date is not None:
            variables['date_interval: date'] = date
        elif interval is not None:
            variables['date_interval: interval'] = interval
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_status(self, job_name, instance_id, date, interval, stop,
                     playbook_handle, extra_vars_handle):
        instance = 'status_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
        }

        if date is not None:
            variables['date_interval_stop: date'] = date
        elif interval is not None:
            variables['date_interval_stop: interval'] = interval
        elif stop is not None:
            variables['date_interval_stop: stop'] = stop
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_restart(self, job_name, instance_id, job_args, date, interval,
                      playbook_handle, extra_vars_handle):
        instance = 'restart_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'job_options:': job_args,
        }
        if date is not None:
            variables['date_interval: date'] = date
        elif interval is not None:
            variables['date_interval: interval'] = interval
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_stop(self, job_name, instance_id, date, playbook, extra_vars):
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'date: date': date,
        }
        return self._build_helper('stop_job_instance_agent', playbook, variables, extra_vars)

    def build_status_agent(self, playbook_file):
        print('    - name: Get status of openbach-agent', file=playbook_file)
        print('      shell: /etc/init.d/openbach-agent status', file=playbook_file)
        return True
    
    def build_list_jobs_agent(self, playbook_file):
        print('    - name: Get the list of the installed jobs', file=playbook_file)
        print('      shell: /opt/openbach-agent/openbach-baton status_jobs_agent', file=playbook_file)
        return True
    
    def build_enable_log(self, syslogseverity, syslogseverity_local, job_path,
            playbook_file):
        if syslogseverity != 8 or syslogseverity_local != 8:
            src_file = 'src={}/templates/{{{{ item.src }}}}'.format(job_path)
            print('    - name: Push new rsyslog conf files', file=playbook_file)
            print('      template:', src_file,
                  'dest=/etc/rsyslog.d/{{ job }}{{ instance_id }}'
                  '{{ item.dst }}.locked owner=root group=root',
                  file=playbook_file)
            print('      with_items:', file=playbook_file)
            if syslogseverity != 8:
                print("         - { src: 'job.j2', dst: '.conf' }", file=playbook_file)
            if syslogseverity_local != 8:
                print("         - { src: 'job_local.j2', dst: '_local.conf' }", file=playbook_file)
            print(file=playbook_file)
            print('      become: yes', file=playbook_file)
        return True
    
    def build_push_file(self, local_path, remote_path, playbook_file):
        print('    - name: Push file', file=playbook_file)
        print('      copy: src={} dest={}'.format(local_path, remote_path), file=playbook_file)
        print('      become: yes', file=playbook_file)
        return True


class BadRequest(Exception):
    """Custom exception raised when parsing of a request failed"""
    def __init__(self, reason, returncode=400, infos=None):
        super().__init__(reason)
        self.reason = reason
        self.returncode = returncode
        if infos:
            self.infos = infos
        else:
            self.infos = {}


class ClientThread(threading.Thread):
    UPDATE_AGENT_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}"'
    UPDATE_JOB_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+*+FROM+"{agent.name}.jobs_list"+GROUP+BY+*+ORDER+BY+DESC+LIMIT+1'
    UPDATE_INSTANCE_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}.{}{}"'

    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.path_src = '/opt/openbach-controller/openbach-conductor/'
        self.playbook_builder = PlaybookBuilder('/tmp/', self.path_src)


    def launch_playbook(self, cmd_ansible):
        p = subprocess.Popen(cmd_ansible, shell=True)
        p.wait()
        if p.returncode:
            raise BadRequest('Ansible playbook execution failed')


    def execute_request(self, data):
        data = json.loads(data)
        request = '{}_view'.format(data.pop('command'))

        # From this point on, request should contain the
        # name of one of the following method: call it
        try:
            function = getattr(self, request)
        except AttributeError:
            raise BadRequest('Function {} not implemented yet'.format(request),
                             500)

        return function(**data)


    def install_agent_view(self, address, collector, username, password, name):
        agent = Agent(name=name, address=address, collector=collector,
                      username=username)
        agent.set_password(password)
        agent.reachable = True
        agent.update_reachable = timezone.now()
        agent.status = 'Installing ...' 
        agent.update_status = timezone.now()
        try:
            agent.save()
        except IntegrityError:
            raise BadRequest('Name of the Agent already used')
        self.playbook_builder.write_hosts(agent.address)
        self.playbook_builder.write_agent(agent.address)
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('local_username:', getpass.getuser(), file=extra_vars)
            print('agent_name:', agent.name, file=extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_agents -e '
            '@/opt/openbach-controller/configs/ips -e '
            'collector_ip={agent.collector} -e '
            '@/tmp/openbach_extra_vars -e @/opt/openbach-controller/configs'
            '/all -e ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password}'
            ' /opt/openbach-controller/install_agent/agent.yml --tags install'
            .format(agent=agent))
        agent.status = 'Available'
        agent.update_status = timezone.now()
        agent.save()
        result = { 'msg': 'OK' }
        # Recuperer la liste des jobs a installer
        list_default_jobs = '/opt/openbach-controller/install_agent/list_default_jobs.txt'
        list_jobs = []
        with open(list_default_jobs) as f:
            for line in f:
                list_jobs.append(line.rstrip('\n'))
        # Installer les jobs
        list_jobs_failed = []
        for job in list_jobs:
            try:
                self.install_jobs_view([agent.address], [job])
            except BadRequest:
                list_jobs_failed.append(job)
        if list_jobs_failed != []:
            result['warning'] = 'Some Jobs couldn’t be installed {}'.format(' '.join(list_jobs_failed))
        return result, 200


    def uninstall_agent_view(self, address):
        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent is not in the database', 404,
                             infos={'address': address})
        self.playbook_builder.write_hosts(agent.address)
        self.playbook_builder.write_agent(agent.address)
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('local_username:', getpass.getuser(), file=extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/opt/openbach-controller/configs/all -e '
            '@/tmp/openbach_agents -e '
            '@/tmp/openbach_extra_vars -e ' 
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password}'
            ' /opt/openbach-controller/install_agent/agent.yml --tags uninstall'
            .format(agent=agent))
        result = { 'msg': 'OK' }
        return result, 200


    def list_agents_view(self, update=False):
        agents = Agent.objects.all()
        response = {}
        if update:
            for agent in agents:
                if agent.reachable and agent.update_status < agent.update_reachable:
                    try:
                        self.update_agent(agent)
                    except BadRequest as e:
                        response.setdefault('errors', []).append({
                            'agent_ip': agent.address,
                            'error': result[3:],
                        })
                    else:
                        agent.refresh_from_db()

        response['agents'] = [
            {
                'address': agent.address,
                'status': agent.status,
                'update_status': agent.update_status.astimezone(timezone.get_current_timezone()),
                'name': agent.name,
            } for agent in agents]

        return response, 200


    @staticmethod
    def update_agent(agent):
        url = ClientThread.UPDATE_AGENT_URL.format(agent=agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            raise BadRequest('Required Stats doesn\'t exist in the Database')

        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value/1000,
                        timezone.get_current_timezone())
            elif column == 'last':
                status = value
        if date > agent.update_status:
            agent.update_status = date
            agent.status = status
            agent.save()


    def status_agents_view(self, addresses):
        unknown_agents = []
        for agent_ip in addresses:
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                unknown_agents.append(agent_ip)
                continue
            self.playbook_builder.write_hosts(agent.address)
            try:
                subprocess.check_output(
                        ['ping', '-c1', '-w2', agent.address])
            except subprocess.CalledProcessError:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent unreachable'
                agent.update_status= timezone.now()
                agent.save()
                continue
            with self.playbook_builder.playbook_file('status_agent') as playbook:
                playbook_name = playbook.name
            # [Ugly hack] Reset file to remove the last line
            with open(playbook_name, 'w') as playbook:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook_name, agent=agent))
            except BadRequest:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent reachable but connection impossible'
                agent.update_status= timezone.now()
                agent.save()
                continue
            agent.reachable = True
            agent.update_reachable = timezone.now()
            agent.save()
            with self.playbook_builder.playbook_file('status_agent') as playbook:
                self.playbook_builder.build_status_agent(playbook) 
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook.name, agent=agent))
            except BadRequest:
                pass
        if unknown_agents:
            raise BadRequest('At least one of the Agents isn\'t in the '
                             'database', 404, {'unknown_agents':
                                               unknown_agents})
        return { 'msg': 'OK' }, 200


    def add_job_view(self, name, path):
        config_prefix = os.path.join(path, 'files', name)
        config_file = '{}.yml'.format(config_prefix)
        try:
            with open(config_file, 'r') as stream:
                try:
                    content = yaml.load(stream)
                except yaml.YAMLError:
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file})
        except FileNotFoundError:
            raise BadRequest('The configuration file is not present', 404,
                             {'configuration file': config_file})
        try:
            job_version = content['general']['job_version']
            keywords = content['general']['keywords']
            statistics = content['statistics']
            description = content['general']['description']
            required_args = []
            args = content['arguments']['required']
            if type(args) == list:
                for arg in args:
                    required_args.append(arg)
            optional_args = []
            if content['arguments']['optional'] != None:
                for arg in content['arguments']['optional']:
                    optional_args.append(arg)
        except KeyError:
            raise BadRequest('The configuration file of the Job is not well '
                             'formed', 409, {'configuration file': config_file})
        try:
            with open('{}.help'.format(config_prefix)) as f:
                help = f.read()
        except OSError:
            help = ''

        deleted = False
        try:
            job = Job.objects.get(pk=name)
            job.delete()
            deleted = True
        except ObjectDoesNotExist:
            pass

        job = Job(
            name=name,
            path=path,
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
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file,
                                                          'warning': 'Old Job has'
                                                          ' been deleted'})
                else:
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file})
        elif statistics == None:
            pass
        else:
            job.delete()
            if deleted:
                raise BadRequest('The configuration file of the Job is not '
                                 'well formed', 409, {'configuration file':
                                                      config_file, 'warning':
                                                      'Old Job has been '
                                                      'deleted'})
            else:
                raise BadRequest('The configuration file of the Job is not well'
                                 ' formed', 409, {'configuration file':
                                                  config_file})

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
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file, 'warning':
                                                          'Old Job has been '
                                                          'deleted'})
                else:
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file})

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
                raise BadRequest('The configuration file of the Job is not well'
                                 ' formed', 409, {'configuration file':
                                                  config_file})

        return {'msg': 'OK'}, 200


    def del_job_view(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404, {
                'job_name': name })
        job.delete()
        return {'msg': 'OK'}, 200


    def list_jobs_view(self, verbosity=0):
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


    def get_job_stats_view(self, name, verbosity=0):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        result = {'job_name': name , 'statistics': [] }
        for stat in job.statistic_set.all():
            statistic = { 'name': stat.name }
            if verbosity > 0:
                statistic['description'] = stat.description
            if verbosity > 1:
                statistic['frequency'] = stat.frequency
            result['statistics'].append(statistic)

        return result, 200


    def get_job_help_view(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        return {'job_name': name, 'help': job.help}, 200


    def install_jobs_view(self, addresses, names, severity=4, local_severity=4):
        agents = Agent.objects.filter(pk__in=addresses)
        no_agent = set(addresses) - set(map(attrgetter('address'), agents))

        jobs = Job.objects.filter(pk__in=names)
        no_job = set(names) - set(map(attrgetter('name'), jobs))

        if no_job or no_agent:
            warning = 'At least one of the Agents or one of the Jobs is unknown'
            warning += ' to the Controller'
        else:
            warning = False

        success = True
        for agent in agents:
            for job in jobs:
                self.playbook_builder.write_hosts(agent.address)
                try:
                    self.launch_playbook(
                        'ansible-playbook -i /tmp/openbach_hosts -e '
                        'path_src={path_src} -e '
                        'ansible_ssh_user={agent.username} -e '
                        'ansible_sudo_pass={agent.password} -e '
                        'ansible_ssh_pass={agent.password} '
                        '{job.path}/install_{job.name}.yml'
                        .format(path_src=self.path_src, agent=agent, job=job))
                except BadRequest:
                    sucess = False
                else:
                    installed_job = Installed_Job(
                            agent=agent, job=job,
                            severity=severity,
                            local_severity=local_severity,
                            update_status=timezone.now())
                    try:
                        installed_job.save()
                    except IntegrityError:
                        pass

        if success:
            if warning:
                result = {'msg': 'OK', 'warning': warning, 'unknown Agents':
                          list(no_agent), 'unknown Jobs': list(no_job)}, 200
                return result
            else:
                return {'msg': 'OK'}, 200
        else:
            if warning:
                raise BadRequest('At least one of the installation have failed',
                                 404, infos={ 'warning': warning,
                                              'unknown Agents': list(no_agent),
                                              'unknown Jobs': list(no_job) })
            else:
                raise BadRequest('At least one of the installation have failed',
                                 404)


    def uninstall_jobs_view(self, addresses, names):
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
        jobs_not_installed = []
        for agent in agents:
            for job in jobs:
                installed_job_name = '{} on {}'.format(job, agent)
                try:
                    installed_job = Installed_Job.objects.get(agent=agent,
                                                              job=job)
                except ObjectDoesNotExist:
                    jobs_not_installed.append(installed_job_name)
                    continue
                self.playbook_builder.write_hosts(agent.address)
                try:
                    self.launch_playbook(
                        'ansible-playbook -i /tmp/openbach_hosts -e '
                        'path_src={path_src} -e '
                        'ansible_ssh_user={agent.username} -e '
                        'ansible_sudo_pass={agent.password} -e '
                        'ansible_ssh_pass={agent.password} '
                        '{job.path}/uninstall_{job.name}.yml'
                        .format(path_src=self.path_src, agent=agent, job=job))
                    installed_job.delete()
                except BadRequest:
                    sucess = False

        if success:
            if warning:
                result = {'msg': 'OK', 'warning': warning, 'unknown Agents':
                          list(no_agent), 'unknown Jobs': list(no_job)}, 200
            else:
                result = {'msg': 'OK'}, 200
            if jobs_not_installed:
                result[0]['msg'] = 'OK but some Jobs were not installed'
                result[0]['jobs_not_installed'] = jobs_not_installed
            return result
        else:
            if warning:
                raise BadRequest('At least one of the installation have failed',
                                 404, infos={ 'warning': warning,
                                              'unknown Agents': list(no_agent),
                                              'unknown Jobs': list(no_job) })
            else:
                raise BadRequest('At least one of the installation have failed',
                                 404)


    def list_installed_jobs_view(self, address, update=False, verbosity=0):
        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             {'address': address})

        response = {'agent': agent.address, 'errors': []}
        if update:
            try:
                result = self.update_jobs(agent.address)
            except BadRequest as e:
                error = { 'error': e.reason }
                response.update(error)
                response.update(e.infos)

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
            if not response['errors']:
                del response['errors']
            return response, 200


    @staticmethod
    def update_jobs(agent_id):
        agent = Agent.objects.get(pk=agent_id)
        url = ClientThread.UPDATE_JOB_URL.format(agent=agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            try:
                raise BadRequest('{}'.format(result['results'][0]['error']))
            except KeyError:
                raise BadRequest('No data available', 404)

        jobs_list = []
        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value / 1000,
                        timezone.get_current_timezone())
            elif column != 'nb':
                jobs_list.append(value)

        for job in agent.installed_job_set.all():
            job_name = job.job.name
            if job_name not in jobs_list:
                job.delete()
            else:
                job.update_status = date
                job.save()
                jobs_list.remove(job_name)

        error = False
        unknown_jobs = []
        for job_name in jobs_list:
            try:
                job = Job.objects.get(pk=job_name)
            except ObjectDoesNotExist:
                unknown_jobs.append(job_name)
                error = True
                continue
            installed_job = Installed_Job(agent=agent, job=job,
                                          udpate_status=date, severity=4,
                                          local_severity=4)
            installed_job.save()

        if error:
            raise BadRequest('These Jobs aren\'t in the Job list of the '
                             'Controller', 404, {'unknown_jobs': unknown_jobs})


    def status_jobs_view(self, addresses):
        error = False
        unknown_agents = []
        for agent_ip in addresses:
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                unknown_agents.append(agent_ip)
                error = True
                continue

            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file('status_jobs') as playbook:
                self.playbook_builder.build_list_jobs_agent(playbook) 
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook.name, agent=agent))
            except BadRequest:
                pass
        if error:
            raise BadRequest('At least one of the Agents isn\'t in the '
                             'database', 404, {'addresses': unknown_agents})
        return { 'msg': 'OK' }, 200


    def push_file_view(self, local_path, remote_path, agent_ip):
        try:
            agent = Agent.objects.get(pk=agent_ip)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             {'address': agent_ip})

        agent = Agent.objects.get(pk=agent_ip)
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file('push_file') as playbook:
            self.playbook_builder.build_push_file(
                    local_path, remote_path, playbook)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))
        return { 'msg': 'OK' }, 200


    @staticmethod
    def format_args(job_instance):
        args = ''
        for argument in job_instance.required_job_argument_instance_set.all().order_by('argument__rank'):
            for job_argument_value in argument.job_argument_value_set.all():
                if args == '':
                    args = '{}'.format(job_argument_value.value)
                else:
                    args = '{} {}'.format(args, job_argument_value.value)
        for optional_argument in job_instance.optional_job_argument_instance_set.all():
            if args == '':
                args = '{}'.format(optional_argument.argument.flag)
            else:
                args = '{} {}'.format(args, optional_argument.argument.flag)
            if optional_argument.argument.type != Optional_Job_Argument.NONE:
                for job_argument_value in optional_argument.job_argument_value_set.all():
                    args = '{} {}'.format(args, job_argument_value.value)
        return args


    @staticmethod
    def fill_and_check_args(job_instance, instance_args):
        for arg_name, arg_values in instance_args.items():
            try:
                argument_instance = Required_Job_Argument_Instance(
                    argument=job_instance.job.job.required_job_argument_set.filter(name=arg_name)[0],
                    job_instance=job_instance
                )
                argument_instance.save()
            except IndexError:
                try:
                    argument_instance = Optional_Job_Argument_Instance(
                        argument=job_instance.job.job.optional_job_argument_set.filter(name=arg_name)[0],
                        job_instance=job_instance
                    )
                    argument_instance.save()
                except IndexError:
                    raise BadRequest('Argument \'{}\' don\'t match with'
                                     ' arguments needed or '
                                     'optional'.format(arg_name), 400)
            if isinstance(arg_values, list):
                for arg_value in arg_values:
                    jav = Job_Argument_Value(job_argument_instance=argument_instance)
                    try:
                        jav.check_and_set_value(arg_value)
                    except ValueError as e:
                        raise BadRequest(e.args[0], 400)
                    jav.save()
            else:
                jav = Job_Argument_Value(job_argument_instance=argument_instance)
                try:
                    jav.check_and_set_value(arg_values)
                except ValueError as e:
                    raise BadRequest(e.args[0], 400)
                jav.save()


    @staticmethod
    def fill_job_instance(job_instance, instance_args, date=None, interval=None,
                          restart=False):
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()

        if interval:
            job_instance.start_date = timezone.now()
            job_instance.periodic = True
            job_instance.save()
        else:
            if not date:
                job_instance.start_date = timezone.now()
                date = 'now'
            else:
                start_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())
                job_instance.start_date = start_date
            job_instance.periodic = False
            job_instance.save()

        if restart:
            job_instance.required_job_argument_instance_set.all().delete()
            job_instance.optional_job_argument_instance_set.all().delete()

        ClientThread.fill_and_check_args(job_instance, instance_args)
        return date


    def start_job_instance(self, scenario_instance_id, agent_ip, job_name,
                           instance_args, ofi_id, finished_queues, offset=None,
                           origin=int(timezone.now().timestamp()*1000),
                           interval=None):
        date = origin + int(offset)*1000
        try:
            result, _ = self.start_job_instance_view(agent_ip, job_name,
                                                     instance_args, date,
                                                     interval)
        except BadRequest as e:
            # TODO gerer les erreurs
            print(e)
            return

        job_instance_id = result['instance_id']
        try:
            self.watch_job_instance_view(job_instance_id, interval=2)
        except BadRequest as e:
            # TODO gerer les erreurs
            print(e)
            return

        with WaitingQueueManager() as waiting_queues:
            waiting_queues[job_instance_id] = (ofi_id, finished_queues)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(('', 2845))
        except socket.error as serr:
            # TODO status manager injoignable, arrete le scenario ?
            print('error de connexion')
            return
        message = { 'type': 'watch', 'scenario_instance_id':
                    scenario_instance_id, 'job_instance_id': job_instance_id }
        sock.send(json.dumps(message).encode())
        sock.close()


    def start_job_instance_view(self, agent_ip, job_name, instance_args, date=None,
                                interval=None):
        try:
            agent = Agent.objects.get(pk=agent_ip)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             {'address': agent_ip})
        try:
            job = Job.objects.get(pk=job_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': job_name})
        try:
            installed_job = Installed_Job.objects.get(agent=agent, job=job)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             {'job_name': '{} on {}'.format(job_name,
                                                            agent_ip)})

        job_instance = Job_Instance(job=installed_job)
        date = self.fill_job_instance(job_instance, instance_args, date, interval)
        self.playbook_builder.write_hosts(agent.address)
        args = self.format_args(job_instance)
        with self.playbook_builder.playbook_file(
                'start_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_start(
                    job.name, job_instance.id,
                    args, date, interval,
                    playbook, extra_vars)
        try:
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))
        except BadRequest:
            job_instance.delete()
            raise
        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        return { 'msg': 'OK', 'instance_id': job_instance.id }, 200


    def stop_job_instance_view(self, instance_ids, date=None):
        job_instances = Job_Instance.objects.filter(pk__in=instance_ids)
        warnings = []

        no_job_instance = set(instance_ids) - set(map(attrgetter('id'), job_instances))
        if no_job_instance:
            warnings.append({'msg': 'At least one of the Job_Instances is '
                             'unknown to the Controller', 'unknown_job_instance':
                             list(no_job_instance)})

        if not date:
            date = 'now'
            stop_date = timezone.now()
        else:
            stop_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())

        already_stopped = {'msg': 'Those Job_Instances are already stopped',
                           'job_instance_ids': []}
        for job_instance in job_instances:
            if job_instance.is_stopped:
                already_stopped['job_instance_ids'].append(job_instance.id)
                continue
            job_instance.stop_date = stop_date
            job_instance.save()
            job = job_instance.job.job
            agent = job_instance.job.agent
            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file(
                    'stop_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
                self.playbook_builder.build_stop(
                        job.name, job_instance.id, date,
                        playbook, extra_vars)
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    '@/tmp/openbach_extra_vars -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_sudo_pass={agent.password} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook.name, agent=agent))
            except BadRequest as e:
                warnings.append({'msg': e.reason, 'job_instance_id':
                                 job_instance.id})
            else:
                if stop_date <= timezone.now():
                    job_instance.is_stopped = True
                    job_instance.save()

        if already_stopped['job_instance_ids']:
            warnings.append(already_stopped)
        response = {'msg': 'OK'}
        if warnings:
            response.update({'warning': warnings})
        return response, 200


    def restart_job_instance_view(self, instance_id, instance_args, date=None,
                                  interval=None):
        try:
            job_instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})

        date = self.fill_job_instance(job_instance, instance_args, date, interval,
                                      True)
        job = job_instance.job.job
        agent = job_instance.job.agent
        self.playbook_builder.write_hosts(agent.address)
        args = self.format_args(job_instance)
        with self.playbook_builder.playbook_file(
                'restart_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_restart(
                    job.name, job_instance.id,
                    args, date, interval,
                    playbook, extra_vars)
        try:
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))
        except BadRequest:
            job_instance.delete()
            raise
        job_instance.is_stopped = False
        job_instance.status = "Restarted"
        job_instance.update_status = timezone.now()
        job_instance.save()
        return { 'msg': 'OK' }, 200


    def watch_job_instance_view(self, instance_id, date=None, interval=None,
                                stop=None):
        try:
            job_instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})
        installed_job = job_instance.job

        try:
            watch = Watch.objects.get(pk=instance_id)
            if not interval and not stop:
                raise BadRequest('A Watch already exists in the database', 400)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, instance_id=instance_id)

        should_delete_watch = True
        if interval:
            should_delete_watch = False
            watch.interval = interval
        elif stop:
            pass
        else:
            if not date:
                date = 'now'
        watch.save()

        job = watch.job.job
        agent = watch.job.agent
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file(
                'status_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_status(
                    job.name, instance_id,
                    date, interval, stop,
                    playbook, extra_vars)
        try:
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))
        except BadRequest:
            watch.delete()
            raise

        if should_delete_watch:
            watch.delete()
        return { 'msg': 'OK' }, 200


    @staticmethod
    def update_instance(instance_id):
        job_instance = Job_Instance.objects.get(pk=instance_id)
        url = ClientThread.UPDATE_INSTANCE_URL.format(
                job_instance.job.job.name, job_instance.id, agent=job_instance.job.agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            try:
                raise BadRequest(result['results'][0]['error'])
            except KeyError:
                raise BadRequest('No data available')

        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value / 1000,
                        timezone.get_current_timezone())
            elif column == 'last':
                status = value
        job_instance.update_status = date
        job_instance.status = status
        job_instance.save()


    def status_job_instance_view(self, instance_id, verbosity=0, update=False):
        error_msg = None
        if update:
            try:
                ClientThread.update_instance(instance_id)
            except BadRequest as e:
                error_msg = e.reason
        try:
            job_instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})
        instance_infos = {
                'id': job_instance.id,
                'arguments': {}
        }
        for required_job_argument in job_instance.required_job_argument_instance_set.all():
            for value in required_job_argument.job_argument_value_set.all():
                if required_job_argument.argument.name not in instance_infos['arguments']:
                    instance_infos['arguments'][required_job_argument.argument.name] = []
                instance_infos['arguments'][required_job_argument.argument.name].append(value.value)
        for optional_job_argument in job_instance.optional_job_argument_instance_set.all():
            for value in optional_job_argument.job_argument_value_set.all():
                if optional_job_argument.argument.name not in instance_infos['arguments']:
                    instance_infos['arguments'][optional_job_argument.argument.name] = []
                instance_infos['arguments'][optional_job_argument.argument.name].append(value.value)
        if verbosity > 0:
            instance_infos['update_status'] = job_instance.update_status.astimezone(
                timezone.get_current_timezone())
            instance_infos['status'] = job_instance.status
        if verbosity > 1:
            instance_infos['start_date'] = job_instance.start_date.astimezone(timezone.get_current_timezone())
        if verbosity > 2:
            try:
                instance_infos['stop_date'] = job_instance.stop_date.astimezone(timezone.get_current_timezone())
            except AttributeError:
                instance_infos['stop_date'] = 'Not programmed yet'
        if error_msg is not None:
            instance_infos['error'] = error_msg
        return instance_infos, 200


    def list_job_instances_view(self, addresses, update=False, verbosity=0):
        if not addresses:
            agents = Agent.objects.all()
        else:
            agents = Agent.objects.filter(pk__in=addresses)
        agents = agents.prefetch_related('installed_job_set')

        response = { 'instances': [] }
        for agent in agents:
            job_instances_for_agent = { 'address': agent.address, 'installed_jobs':
                                      []}
            for job in agent.installed_job_set.all():
                job_instances_for_job = { 'job_name': job.name, 'instances': [] }
                for job_instance in job.job_instance_set.filter(is_stopped=False):
                    instance_infos, _ = self.status_job_instance(job_instance.id,
                                                                    verbosity,
                                                                    update)
                    job_instances_for_job['instances'].append(instance_infos)
                if job_instances_for_job['instances']:
                    job_instances_for_agent['installed_jobs'].append(job_instances_for_job)
            if job_instances_for_agent['installed_jobs']:
                response['instances'].append(job_instances_for_agent)
        return response, 200


    def set_job_log_severity_view(self, address, job_name, severity, date=None,
                                  local_severity=None):
        try:
            job = Job.objects.get(name=job_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             infos={'job_name': job_name})
        try:
            agent = Job.objects.get(address=address)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             infos={'agent_ip': address})
        try:
            installed_job = Installed_Job.objects.get(agent=agent, job=job)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             infos={'job_name': installed_job})

        try:
            job = Job.objects.get(name='rsyslog_job')
        except ObjectDoesNotExist:
            raise BadRequest('The Job rsyslog_job isn\'t in the database', 404,
                             infos={'job_name': 'rsyslog_job'})
        try:
            logs_job = Installed_Job.objects.get(job=job, agent=agent)
        except ObjectDoesNotExist:
            raise BadRequest('The Installed_Job rsyslog isn\'t in the database',
                             404, infos={'job_name': 'rsyslog_job on '
                                         '{}'.format(address)})

        job_instance = Job_Instance(job=logs_job)
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()
        job_instance.start_date = timezone.now()
        job_instance.periodic = False
        job_instance.save()

        instance_args = { 'job_name': [job_name], 'instance_id': [job_instance.id] }
        date = self.fill_job_instance(job_instance, instance_args, date)

        logs_job_path = job_instance.job.job.path
        syslogseverity = convert_severity(int(severity))
        if not local_severity:
            local_severity = installed_job.local_severity
        syslogseverity_local = convert_severity(int(local_severity))
        disable = 0
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file('logs') as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            if syslogseverity == 8:
                disable += 1
            else:
                print('collector_ip:', agent.collector, file=extra_vars)
                print('syslogseverity:', syslogseverity, file=extra_vars)
            if syslogseverity_local == 8:
                disable += 2
            else:
                print('syslogseverity_local:', syslogseverity_local, file=extra_vars)
            print('job:', job_name, file=extra_vars)
            print('instance_id:', job_instance.id, file=extra_vars)

            argument_instance = Optional_Job_Argument_Instance(
                argument=job_instance.job.job.optional_job_argument_set.filter(name='disable_code')[0],
                job_instance=job_instance
            )
            argument_instance.save()
            Job_Argument_Value(
                value=disable,
                job_argument_instance=argument_instance
            ).save()

            args = self.format_args(job_instance)
            self.playbook_builder.build_enable_log(
                    syslogseverity, syslogseverity_local,
                    logs_job_path, playbook)
            self.playbook_builder.build_start(
                    'rsyslog_job', job_instance.id, args,
                    date, None, playbook, extra_vars)
        try:
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                '@/opt/openbach-controller/configs/all -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))
        except BadRequest as e:
            job_instance.delete()
            return e.reason, 404

        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        result = { 'msg': 'OK' }
        return result, 200


    def set_job_stat_policy_view(self, address, job_name, stat_name=None,
                                 storage=None, broadcast=None, date=None):
        try:
            job = Job.objects.get(name=job_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             infos={'job_name': job_name})
        try:
            agent = Job.objects.get(address=address)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             infos={'agent_ip': address})
        try:
            installed_job = Installed_Job.objects.get(agent=agent, job=job)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             infos={'job_name': installed_job})

        if stat_name != None:
            statistic = installed_job.job.statistic_set.filter(name=stat_name)
            if not statistic:
                raise BadRequest('The statistic \'{}\' isn\'t produce by the'
                                 ' Job \'{}\''.format(stat_name, job_name))
            statistic = statistic[0]
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

        rstat_name = 'rstats_job on {}'.format(address)
        try:
            job = Job.objects.get(name='rstats_job')
        except ObjectDoesNotExist:
            raise BadRequest('The Job rstats_job isn\'t in the database', 404,
                             infos={'job_name': 'rstats_job'})
        try:
            rstats_job = Installed_Job.objects.get(job=job, agent=agent)
        except ObjectDoesNotExist:
            raise BadRequest('The Installed_Job rstats_job isn\'t in the database',
                             404, infos={'job_name': rstat_job})

        job_instance = Job_Instance(job=rstats_job)
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()
        job_instance.start_date = timezone.now()
        job_instance.periodic = False
        job_instance.save()
 
        instance_args = { 'job_name': [job_name], 'instance_id': [job_instance.id] }
        date = self.fill_job_instance(job_instance, instance_args, date)

        rstats_job_path = job_instance.job.job.path
        with open('/tmp/openbach_rstats_filter', 'w') as rstats_filter:
            print('[default]', file=rstats_filter)
            print('storage =', installed_job.default_stat_storage,
                    file=rstats_filter)
            print('broadcast =', installed_job.default_stat_broadcast,
                    file=rstats_filter)
            for stat in installed_job.statistic_instance_set.all():
                print('[{}]'.format(stat.stat.name), file=rstats_filter)
                print('storage =', stat.storage, file=rstats_filter)
                print('broadcast =', stat.broadcast, file=rstats_filter)
        self.playbook_builder.write_hosts(agent.address)
        remote_path = ('/opt/openbach-jobs/{0}/{0}{1}'
                '_rstats_filter.conf.locked').format(job_name, job_instance.id)
        with self.playbook_builder.playbook_file('rstats') as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_push_file(
                    rstats_filter.name, remote_path, playbook)
            args = self.format_args(job_instance)
            self.playbook_builder.build_start(
                    'rstats_job', job_instance.id, args,
                    date, None, playbook, extra_vars)
        try:
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                '@/opt/openbach-controller/configs/all -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))
        except BadRequest as e:
            job_instance.delete()
            return e.reason, 404
        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        result = { 'msg': 'OK' }
        return result, 200


    @staticmethod
    def first_check_on_scenario(scenario_json):
        required_parameters = ('name', 'description', 'arguments', 'constants',
                               'openbach_functions')
        try:
            for k in required_parameters:
                scenario_json[k]
        except KeyError:
            return False
        if not isinstance(scenario_json['name'], str):
            return False
        if not isinstance(scenario_json['description'], str):
            return False
        if not isinstance(scenario_json['arguments'], dict):
            return False
        for argument, description in scenario_json['arguments'].items():
            if not isinstance(argument, str):
                return False
            if not isinstance(description, str):
                return False
        if not isinstance(scenario_json['constants'], dict):
            return False
        for constant, _ in scenario_json['constants'].items():
            if not isinstance(constant, str):
                return False
        if not isinstance(scenario_json['openbach_functions'], list):
            return False
        known = { 'wait' }
        for openbach_function in scenario_json['openbach_functions']:
            if not isinstance(openbach_function['wait'], dict):
                return False
            other = [ k for k in openbach_function if k not in known ]
            if len(other) != 1:
                return False
            if not isinstance(openbach_function[other[0]], dict):
                return False
            try:
                if not isinstance(openbach_function['wait']['time'], int):
                    return False
                if not isinstance(openbach_function['wait']['finished_indexes'],
                                  list):
                    return False
                if not isinstance(openbach_function['wait']['launched_indexes'],
                                  list):
                    return False
            except KeyError:
                return False
            #if openbach_function['name'] == 'start_job_instance':
            #    if 'args' not in openbach_function:
            #        return False
            #    if not isinstance(openbach_function['args'], list):
            #        return False
            #    try:
            #        for arg in openbach_function['args']:
            #            for k in required_parameters:
            #                arg[k]
            #    except KeyError:
            #        return False
        return True


    @staticmethod
    def check_type_or_get_reference(argument, arg_value):
        expected_type = argument.type
        if isinstance(arg_value, str):
            substitution_pattern = '${}'
            escaped_substitution_pattern = '\${}'
            try:
                scenario_arg = parse.parse(substitution_pattern, arg_value)[0]
            except TypeError:
                try:
                    value = parse.parse(escaped_substitution_pattern, arg_value)[0]
                    value = '${}'.format(value)
                except TypeError:
                    value = arg_value
            else:
                return scenario_arg
        else:
            value = arg_value
        av = Argument_Value()
        try:
            av._check_type_internal(expected_type, value)
        except ValueError:
            raise BadRequest('The type of this argument is not valid', 404,
                             {'name': argument.name})
        return False


    @staticmethod
    def check_type(argument, arg_value, scenario_arguments, scenario_constants):
        is_reference = ClientThread.check_type_or_get_reference(
            argument, arg_value)
        if is_reference:
            scenario_arg = is_reference
            if scenario_arg in scenario_arguments:
                sa = scenario_arguments[scenario_arg]
                if not sa.check_or_set_type(argument.type):
                    raise BadRequest('This scenario argument is use on '
                                     'two different types', 404,
                                     {'scenario_argument':
                                      scenario_arg})
            elif scenario_arg in scenario_constants:
                sc = scenario_constants[scenario_arg]['scenario_constant']
                if not sc.check_or_set_type(argument.type):
                    raise BadRequest('This scenario constant is use on '
                                     'two different types', 404,
                                     {'scenario_argument':
                                      scenario_arg})
            else:
                raise BadRequest('Reference to an argument or a constant'
                                 ' that does not exist', 404, {'name':
                                                               scenario_arg})


    @staticmethod
    def register_scenario(scenario_json, name):
        try:
            description = scenario_json['description']
        except KeyError:
            description = None
        scenario_string = json.dumps(scenario_json)

        scenario = Scenario(name=name, description=description,
                            scenario=scenario_string)
        try:
            scenario.save(force_insert=True)
            #TODO delete scenario if an error occurs !
        except IntegrityError:
            raise BadRequest('This name of Scenario \'{}\' is already'
                             ' used'.format(name), 409)
        try:
            result = ClientThread.register_scenario_arguments(scenario, scenario_json)
        except BadRequest:
            scenario.delete()
            raise
        return result


    @staticmethod
    def register_scenario_arguments(scenario, scenario_json):
        scenario_arguments = {}
        for arg_name, description in scenario_json['arguments'].items():
            try:
                sa = Scenario_Argument(
                    name=arg_name,
                    description=description,
                    scenario=scenario
                )
            except KeyError:
                raise BadRequest('At least one of the args is malformed')
            scenario_arguments[arg_name] = sa
        scenario_constants = {}
        for const_name, const_value in scenario_json['constants'].items():
            sa = Scenario_Argument(
                name=const_name,
                scenario=scenario
            )
            scenario_constants[const_name] = { 'value': const_value,
                                               'scenario_constant': sa }
        for openbach_function in scenario_json['openbach_functions']:
            wait = openbach_function.pop('wait')
            (name, args), = openbach_function.items()
            try:
                of = Openbach_Function.objects.get(pk=name)
            except ObjectDoesNotExist:
                raise BadRequest('This Openbach_Function doesn\'t exist', 404,
                                 {'name': openbach_function['name']})
            if name == 'start_job_instance':
                try:
                    agent_ip = args.pop('agent_ip')
                    offset = args.pop('offset')
                except KeyError:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 404, {'name':
                                                             'start_job_instance'})
                of_argument = of.openbach_function_argument_set.get(
                    name='agent_ip')
                ClientThread.check_type(of_argument, agent_ip,
                                        scenario_arguments, scenario_constants)
                of_argument = of.openbach_function_argument_set.get(
                    name='offset')
                ClientThread.check_type(of_argument, offset,
                                        scenario_arguments, scenario_constants)
                try:
                    (job_name, job_args), = args.items()
                except ValueError:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 404, {'name':
                                                             'start_job_instance'})
                try:
                    job = Job.objects.get(name=job_name)
                except ObjectDoesNotExist:
                    raise BadRequest('This Job does not exist', 404, {'name':
                                                                      job_name})
                if not isinstance(job_args, dict):
                    raise BadRequest('Your Scenario is malformed')
                for job_arg, job_value in job_args.items():
                    try:
                        ja = job.required_job_argument_set.get(name=job_arg)
                    except ObjectDoesNotExist:
                        try:
                            ja = job.optional_job_argument_set.get(name=job_arg)
                        except ObjectDoesNotExist:
                            raise BadRequest('This Job_Argument does not exist',
                                             404, {'job_name': job_name,
                                                   'argument_name': job_arg})
                    if isinstance(job_value, list):
                        for v in job_value:
                            ClientThread.check_type(ja, v,
                                                    scenario_arguments,
                                                    scenario_constants)
                    else:
                        ClientThread.check_type(ja, job_value,
                                                scenario_arguments,
                                                scenario_constants)
            else:
                for of_arg, of_value in args.items():
                    try:
                        of_argument = Openbach_Function_Argument.objects.get(
                            name=of_arg, openbach_function=of)
                    except ObjectDoesNotExist:
                        raise BadRequest('This Openbach_Function doesn\'t have this'
                                         ' argument', 404, {'name': name,
                                                            'argument': of_arg})
                ClientThread.check_type(of_argument, of_value,
                                        scenario_arguments, scenario_constants)
        result = {}
        for _, sa in scenario_arguments.items():
            try:
                sa.save()
            except IntegrityError:
                raise BadRequest('At least two args have the same name', 409,
                                 infos={'name': arg['name']})
            result[sa.name] = sa.type
        for const_name, sc_dict in scenario_constants.items():
            sc = sc_dict['scenario_constant']
            value = sc_dict['value']
            try:
                sc.save()
            except IntegrityError:
                raise BadRequest('At least two constants have the same name', 409,
                                 infos={'name': arg['name']})
            sai = Scenario_Argument_Instance(argument=sc)
            try:
                sai.check_and_set_value(value)
            except ValueError:
                raise BadRequest('This constant does not have the good type',
                                 409, {'constant': sc.name, 'expected_type':
                                       sc.type})
            try:
                sai.save()
            except IntegrityError:
                raise BadRequest('At least two constants have the same name', 409,
                                 infos={'name': arg['name']})

        result['scenario_name'] = name
        return result, 200


    def create_scenario_view(self, scenario_json):
        if not self.first_check_on_scenario(scenario_json):
            raise BadRequest('Your Scenario is malformed')
        name = scenario_json['name']

        return self.register_scenario(scenario_json, name)


    def del_scenario_view(self, scenario_name):
        try:
            scenario = Scenario.objects.get(pk=scenario_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name})

        scenario.delete()

        return { 'msg': 'OK' }, 200


    def modify_scenario_view(self, scenario_json, scenario_name):
        if not self.first_check_on_scenario(scenario_json):
            raise BadRequest('Your Scenario is malformed')
        name = scenario_json['name']
        if name != scenario_name:
            raise BadRequest('The name in the Scenario \'{}\' doesn\'t '
                             'correspond with the name of the route '
                             '\'{}\''.format(name, scenario_name))
        try:
            scenario = Scenario.objects.get(pk=scenario_name)
        except ObjectDoesNotExist:
            pass
        else:
            scenario.delete()

        return self.register_scenario(scenario_json, name)


    def get_scenario_view(self, scenario_name):
        try:
            scenario = Scenario.objects.get(pk=scenario_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name})

        return json.loads(scenario.scenario), 200


    def list_scenarios_view(self, verbosity=0):
        scenarios = Scenario.objects.all()
        response = { 'scenarios': [] }
        for scenario in scenarios:
            if verbosity == 0:
                response['scenarios'].append(scenario.name)
            elif verbosity == 1:
                response['scenarios'].append({ 'name': scenario.name,
                                               'description':
                                               scenario.description })
            else:
                response['scenarios'].append(json.loads(scenario.scenario))

        return response, 200


    @staticmethod
    def register_openbach_function_argument_instance(arg_name, arg_value,
                                                     openbach_function_instance,
                                                     scenario_instance):
        of = openbach_function_instance.openbach_function
        ofai = Openbach_Function_Argument_Instance(
            argument=Openbach_Function_Argument.objects.get(name=arg_name,
                                                            openbach_function=of),
            openbach_function_instance=openbach_function_instance)
        of_argument = Openbach_Function_Argument.objects.get(
            name=arg_name, openbach_function=of)
        is_reference = ClientThread.check_type_or_get_reference(
            of_argument, arg_value)
        try:
            if is_reference:
                sa = scenario_instance.scenario.scenario_argument_set.get(
                    name=is_reference)
                try:
                    spi = scenario_instance.scenario_argument_instance_set.get(
                        argument=sa)
                except ObjectDoesNotExist:
                    spi = scenario_instance.scenario.scenario_argument_set.get(
                        name=is_reference).scenario_argument_instance_set.get(
                            scenario_instance=None)
                ofai.check_and_set_value(spi.value)
            else:
                escaped_substitution_pattern = '\${}'
                try:
                    value = parse.parse(escaped_substitution_pattern, arg_value)[0]
                    value = '${}'.format(value)
                except TypeError:
                    value = arg_value
                ofai.check_and_set_value(value)
        except ValueError as e:
            raise BadRequest(e.args[0], 400)
        ofai.save()


    @staticmethod
    def register_openbach_function_instances(scenario_instance):
        scenario_json = json.loads(scenario_instance.scenario.scenario)
        openbach_function_id = 0
        scenario_arguments = {}
        for sai in scenario_instance.scenario_argument_instance_set.all():
            scenario_arguments[sai.argument.name] = sai
        for sa in scenario_instance.scenario.scenario_argument_set.all():
            try:
                sc = sa.scenario_argument_instance_set.get(scenario_instance=None)
            except ObjectDoesNotExist:
                continue
            scenario_arguments[sc.argument.name] = sc
        for openbach_function in scenario_json['openbach_functions']:
            wait = openbach_function.pop('wait')
            (name, args), = openbach_function.items()
            of = Openbach_Function.objects.get(pk=name)
            ofi = Openbach_Function_Instance(openbach_function=of,
                                             scenario_instance=scenario_instance,
                                             openbach_function_instance_id=openbach_function_id)
            ofi.save()
            if name == 'start_job_instance':
                agent_ip = args.pop('agent_ip')
                ClientThread.register_openbach_function_argument_instance(
                    'agent_ip', agent_ip, ofi, scenario_instance)
                offset = args.pop('offset')
                ClientThread.register_openbach_function_argument_instance(
                    'offset', offset, ofi, scenario_instance)
                (job_name, job_args), = args.items()
                ClientThread.register_openbach_function_argument_instance(
                    'job_name', job_name, ofi, scenario_instance)
                job = Job.objects.get(name=job_name)
                instance_args = {}
                for job_arg, job_value in job_args.items():
                    try:
                        ja = job.required_job_argument_set.get(name=job_arg)
                    except ObjectDoesNotExist:
                        ja = job.optional_job_argument_set.get(name=job_arg)
                    if isinstance(job_value, list):
                        instance_args[job_arg] = []
                        for v in job_value:
                            is_reference = ClientThread.check_type_or_get_reference(
                                ja, v)
                            if is_reference:
                                sa = scenario_instance.scenario.scenario_argument_set.get(
                                    name=is_reference)
                                try:
                                    spi = scenario_instance.scenario_argument_instance_set.get(
                                        argument=sa)
                                except ObjectDoesNotExist:
                                    spi = scenario_instance.scenario.scenario_argument_set.get(
                                        name=is_reference).scenario_argument_instance_set.get(
                                            scenario_instance=None)
                                instance_args[job_arg].append(spi.value)
                            else:
                                escaped_substitution_pattern = '\${}'
                                try:
                                    value = parse.parse(
                                        escaped_substitution_pattern,
                                        arg_value)[0]
                                    value = '${}'.format(value)
                                except TypeError:
                                    value = arg_value
                                instance_args[job_arg].append(value)
                    else:
                        is_reference = ClientThread.check_type_or_get_reference(
                            ja, job_value)
                        if is_reference:
                            sa = scenario_instance.scenario.scenario_argument_set.get(
                                name=is_reference)
                            try:
                                spi = scenario_instance.scenario_argument_instance_set.get(
                                    argument=sa)
                            except ObjectDoesNotExist:
                                spi = scenario_instance.scenario.scenario_argument_set.get(
                                    name=is_reference).scenario_argument_instance_set.get(
                                        scenario_instance=None)
                            instance_args[job_arg] = spi.value
                        else:
                            escaped_substitution_pattern = '\${}'
                            try:
                                value = parse.parse(
                                    escaped_substitution_pattern,
                                    arg_value)[0]
                                value = '${}'.format(value)
                            except TypeError:
                                value = arg_value
                            instance_args[job_arg] = value
                ofai = Openbach_Function_Argument_Instance(
                    argument=Openbach_Function_Argument.objects.get(
                        name='instance_args', openbach_function=of),
                    openbach_function_instance=ofi)
                try:
                    ofai.check_and_set_value(instance_args)
                except ValueError as e:
                    raise BadRequest(e.args[0], 400)
                ofai.save()
            else:
                for arg_name, arg_value in args.items():
                    ClientThread.register_openbach_function_argument_instance(
                        arg_name, arg_value, ofi, scenario_instance)
            wf = Wait_For(scenario_instance=scenario_instance,
                          openbach_function_instance=ofi,
                          time=wait['time'])
            wf.save()
            for index in wait['launched_indexes']:
                wfl = Wait_For_Launched(wait_for=wf,
                                        openbach_function_instance_id=index)
                wfl.save()
            for index in wait['finished_indexes']:
                wff = Wait_For_Finished(wait_for=wf, job_instance_id=index)
                wff.save()
            openbach_function_id += 1


    @staticmethod
    def register_scenario_instance(scenario, args):
        scenario_instance = Scenario_Instance(scenario=scenario)
        scenario_instance.status = "Starting ..."
        scenario_instance.status_date = timezone.now()
        scenario_instance.save()
        # Enregistrer les args de l'instance de scenario
        for arg_name, arg_value in args.items():
            try:
                scenario_argument = scenario.scenario_argument_set.get(
                    name=arg_name)
            except ObjectDoesNotExist:
                raise BadRequest('Argument \'{}\' don\'t match with'
                                 ' the arguments'.format(arg_name))
            try:
                scenario_argument.scenario_argument_instance_set.get(scenario_instance=None)
            except ObjectDoesNotExist:
                sai = Scenario_Argument_Instance(
                    argument=scenario_argument,
                    scenario_instance=scenario_instance)
                try:
                    sai.check_and_set_value(arg_value)
                except ValueError as e:
                    raise BadRequest(e.args[0], 400)
                sai.save()

        ClientThread.register_openbach_function_instances(scenario_instance)

        return scenario_instance


    @staticmethod
    def build_table(scenario_instance):
        table = {}
        for wf in scenario_instance.wait_for_set.all():
            ofi_id = wf.openbach_function_instance.openbach_function_instance_id
            table[ofi_id] = { 'wait_for_launched': set(),
                              'is_waited_for_launched': set(),
                              'wait_for_finished': set(),
                              'is_waited_for_finished': set() }
            for wfl in wf.wait_for_launched_set.all():
                ofi_waited_id = wfl.openbach_function_instance_id
                if ofi_waited_id not in table:
                    table[ofi_waited_id] = { 'wait_for_launched': set(),
                                             'is_waited_for_launched': set(),
                                             'wait_for_finished': set(),
                                             'is_waited_for_finished': set() }
                table[ofi_id]['wait_for_launched'].add(ofi_waited_id)
                table[ofi_waited_id]['is_waited_for_launched'].add(ofi_id)
            for wff in wf.wait_for_finished_set.all():
                ji_waited_id = wff.job_instance_id
                if ji_waited_id not in table:
                    table[ji_waited_id] = { 'wait_for_launched': set(),
                                            'is_waited_for_launched': set(),
                                            'wait_for_finished': set(),
                                            'is_waited_for_finished': set() }
                table[ofi_id]['wait_for_finished'].add(ji_waited_id)
                table[ji_waited_id]['is_waited_for_finished'].add(ofi_id)
        return table


    def launch_openbach_function_instance(self, scenario_instance, ofi_id, l,
                                          queue, launch_queues, finished_queues,
                                          date):
        while l:
            x = queue.get()
            l.remove(x)
        ofi = scenario_instance.openbach_function_instance_set.filter(
            openbach_function_instance_id=ofi_id)[0]
        try:
            function = getattr(self, ofi.openbach_function.name)
        except AttributeError:
            #TODO gerer mieux l'erreur
            raise BadRequest('Function {} not implemented yet'.format(request),
                             500)
        arguments = {}
        for arg in ofi.openbach_function_argument_instance_set.all():
            if arg.argument.type == 'json':
                arguments[arg.argument.name] = json.loads(arg.value)
            else:
                arguments[arg.argument.name] = arg.value
        if ofi.openbach_function.name == 'start_job_instance':
            arguments['scenario_instance_id'] = scenario_instance.id
            arguments['ofi_id'] = ofi_id
            arguments['finished_queues'] = finished_queues
        function(**arguments)
        for queue in launch_queues:
            queue.put(ofi_id)


    def start_scenario_instance_view(self, scenario_name, args, date=None):
        try:
            scenario = Scenario.objects.get(pk=scenario_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name})
        scenario_instance = self.register_scenario_instance(scenario, args)
        table = self.build_table(scenario_instance)
        queues = { id: Queue() for id in table }
        for ofi_id, data in table.items():
            queue = queues[ofi_id]
            launch_queues = [ queues[id] for id in data['is_waited_for_launched'] ]
            finished_queues = tuple([ queues[id] for id in
                                     data['is_waited_for_finished'] ])
            waited_ids = data['wait_for_launched'].union(data['wait_for_finished'])
            thread = threading.Thread(
                target=self.launch_openbach_function_instance,
                args=(scenario_instance, ofi_id, waited_ids, queue,
                      launch_queues, finished_queues, date))
            thread.start()

        return { 'scenario_instance_id': scenario_instance.id }, 200


    def stop_scenario_instance_view(self, scenario_instance_id, date=None):

        return { 'error': 'TODO' }, 400


    def list_scenario_instances_view(self, scenario_ids=[]):

        return { 'error': 'TODO' }, 400


    def status_scenario_instance_view(self, scenario_instance_id, verbosity=0):

        return { 'error': 'TODO' }, 400


    def run(self):
        request = self.clientsocket.recv(2048)
        try:
            result, returncode = self.execute_request(request.decode())
        except BadRequest as e:
            result = { 'error': e.reason, 'returncode': e.returncode }
            if e.infos:
                result.update(e.infos)
        except UnicodeError:
            result = { 'error': 'KO Undecypherable request', 'returncode': 400 }
        else:
            result['returncode'] = returncode
        finally:
            self.clientsocket.send(json.dumps(result, cls=DjangoJSONEncoder).encode())
            self.clientsocket.close()


def listen_message_from_backend(tcp_socket):
    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()


def handle_message_from_status_manager(clientsocket):
    request = clientsocket.recv(2048)
    clientsocket.close()
    message = json.loads(request.decode())
    type_ = message['type']
    scenario_instance_id = message['scenario_instance_id']
    job_instance_id = message['job_instance_id']
    if type_ == 'Finished':
        with WaitingQueueManager() as waiting_queues:
            ofi_id, finished_queues = waiting_queues[job_instance_id]
        for queue in finished_queues:
            queue.put(ofi_id)
        # TODO Stopper la watch ?


def listen_message_from_status_manager(tcp_socket):
    while True:
        client_socket, _ = tcp_socket.accept()
        threading.Thread(target=handle_message_from_status_manager,
                         args=(client_socket,)).start()


if __name__ == '__main__':
    # Ouverture de la socket d'ecoute avec le backend
    tcp_socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket1.bind(('', 1113))
    tcp_socket1.listen(10)

    # Ouverture de la socket d'ecoute avec le status_manager
    tcp_socket2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket2.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket2.bind(('', 2846))
    tcp_socket2.listen(10)

    # Initialiser le WaitingQueueManager
    WaitingQueueManager(init=True)

    thread1 = threading.Thread(target=listen_message_from_backend,
                               args=(tcp_socket1,))
    thread1.start()
    thread2 = threading.Thread(target=listen_message_from_status_manager,
                               args=(tcp_socket2,))
    thread2.start()

