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
from operator import attrgetter
from datetime import datetime
from django.core.serializers.json import DjangoJSONEncoder
from contextlib import contextmanager

import sys
sys.path.insert(0, '/opt/openbach-controller/backend')
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()

from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from openbach_django.models import Agent, Job, Installed_Job, Job_Instance, Watch, Job_Keyword
from openbach_django.models import Statistic, Required_Job_Argument, Optional_Job_Argument
from openbach_django.models import Required_Job_Argument_Instance, Optional_Job_Argument_Instance
from openbach_django.models import Job_Argument_Value, Statistic_Instance


_SEVERITY_MAPPING = {
    0: 3,   # Error
    1: 4,   # Warning
    2: 6,   # Informational
    3: 7,   # Debug
}


def convert_severity(severity):
    return _SEVERITY_MAPPING.get(severity, 8)


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
        request = data.pop('command')

        # From this point on, request should contain the
        # name of one of the following method: call it
        try:
            function = getattr(self, request)
        except AttributeError:
            raise BadRequest('Function {} not implemented yet'.format(request),
                             500)

        return function(**data)


    def install_agent(self, address, collector, username, password, name):
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
                self.install_jobs([agent.address], [job])
            except BadRequest:
                list_jobs_failed.append(job)
        if list_jobs_failed != []:
            result['warning'] = 'Some Jobs couldn’t be installed {}'.format(' '.join(list_jobs_failed))
        return result, 200


    def uninstall_agent(self, address):
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


    def list_agents(self, update=False):
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


    def update_agent(self, agent):
        url = self.UPDATE_AGENT_URL.format(agent=agent)
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


    def status_agents(self, addresses):
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


    def add_job(self, name, path):
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


    def del_job(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404, {
                'job_name': name })
        job.delete()
        return {'msg': 'OK'}, 200


    def list_jobs(self, verbosity=0):
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


    def get_job_stats(self, name, verbosity=0):
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


    def get_job_help(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        return {'job_name': name, 'help': job.help}, 200


    def install_jobs(self, addresses, names, severity=4, local_severity=4):
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
                    installed_job = Installed_Job(
                            agent=agent, job=job,
                            severity=severity,
                            local_severity=local_severity)
                    installed_job.set_name()
                    installed_job.update_status = timezone.now()
                    installed_job.save()
                except BadRequest:
                    sucess = False

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


    def uninstall_jobs(self, addresses, names):
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
                    installed_job = Installed_Job.objects.get(pk=installed_job_name)
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


    def list_installed_jobs(self, address, update=False, verbosity=0):
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


    def update_jobs(self, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        url = self.UPDATE_JOB_URL.format(agent=agent)
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
            installed_job = Installed_Job(agent=agent, job=job)
            installed_job.set_name()
            installed_job.update_status = date
            installed_job.severity = 4
            installed_job.local_severity = 4
            installed_job.save()

        if error:
            raise BadRequest('These Jobs aren\'t in the Job list of the '
                             'Controller', 404, {'unknown_jobs': unknown_jobs})


    def status_jobs(self, addresses):
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


    def push_file(self, local_path, remote_path, agent_ip):
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
    def format_args(instance):
        args = ''
        for argument in instance.required_job_argument_instance_set.all().order_by('argument__rank'):
            for job_argument_value in argument.job_argument_value_set.all():
                if args == '':
                    args = '{}'.format(job_argument_value.value)
                else:
                    args = '{} {}'.format(args, job_argument_value.value)
        for optional_argument in instance.optional_job_argument_instance_set.all():
            if args == '':
                args = '{}'.format(optional_argument.argument.flag)
            else:
                args = '{} {}'.format(args, optional_argument.argument.flag)
            if optional_argument.argument.type != Optional_Job_Argument.NONE:
                for job_argument_value in optional_argument.job_argument_value_set.all():
                    args = '{} {}'.format(args, job_argument_value.value)
        return args


    @staticmethod
    def fill_and_check_args(instance, instance_args):
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
                    raise BadRequest('Argument \'{}\' don\'t match with'
                                     ' arguments needed or '
                                     'optional'.format(arg_name), 400)
            for arg_value in arg_values:
                Job_Argument_Value(
                    value=arg_value,
                    argument_instance=argument_instance
                ).save()

        try:
            instance.check_args()
        except ValueError as e:
            raise BadRequest(e.args[0], 400)


    @staticmethod
    def fill_job_instance(instance, instance_args, date=None, interval=None,
                          restart=False):
        instance.status = "Starting ..."
        instance.update_status = timezone.now()

        if interval:
            instance.start_date = timezone.now()
            instance.periodic = True
            instance.save()
        else:
            if not date:
                instance.start_date = timezone.now()
                date = 'now'
            else:
                start_date = datetime.fromtimestamp(date/1000,tz=timezone.get_current_timezone())
                instance.start_date = start_date
            instance.periodic = False
            instance.save()

        if restart:
            instance.required_job_argument_instance_set.all().delete()
            instance.optional_job_argument_instance_set.all().delete()

        ClientThread.fill_and_check_args(instance, instance_args)
        return date


    def start_job_instance(self, agent_ip, job_name, instance_args, date=None,
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
        name = '{} on {}'.format(job_name, agent_ip)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             {'job_name': name})

        instance = Job_Instance(job=installed_job)
        date = self.fill_job_instance(instance, instance_args, date, interval)
        self.playbook_builder.write_hosts(agent.address)
        args = self.format_args(instance)
        with self.playbook_builder.playbook_file(
                'start_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_start(
                    job.name, instance.id,
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
            instance.delete()
            raise
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        return { 'msg': 'OK', 'instance_id': instance.id }, 200


    def stop_job_instance(self, instance_ids, date=None):
        instances = Job_Instance.objects.filter(pk__in=instance_ids)
        warnings = []

        no_job_instance = set(instance_ids) - set(map(attrgetter('id'), instances))
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
        for instance in instances:
            if instance.is_stopped:
                already_stopped['job_instance_ids'].append(instance.id)
                continue
            instance.stop_date = stop_date
            instance.save()
            job = instance.job.job
            agent = instance.job.agent
            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file(
                    'stop_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
                self.playbook_builder.build_stop(
                        job.name, instance.id, date,
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
                                 instance.id})
            else:
                if stop_date <= timezone.now():
                    instance.is_stopped = True
                    instance.save()

        if already_stopped['job_instance_ids']:
            warnings.append(already_stopped)
        response = {'msg': 'OK'}
        if warnings:
            response.update({'warning': warnings})
        return response, 200


    def restart_job_instance(self, instance_id, instance_args, date=None,
                             interval=None):
        try:
            instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})

        date = self.fill_job_instance(instance, instance_args, date, interval,
                                      True)
        job = instance.job.job
        agent = instance.job.agent
        self.playbook_builder.write_hosts(agent.address)
        args = self.format_args(instance)
        with self.playbook_builder.playbook_file(
                'restart_{}'.format(job.name)) as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_restart(
                    job.name, instance.id,
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
            instance.delete()
            raise
        instance.is_stopped = False
        instance.status = "Restarted"
        instance.update_status = timezone.now()
        instance.save()
        return { 'msg': 'OK' }, 200


    def watch_job_instance(self, instance_id, date=None, interval=None,
                           stop=None):
        try:
            instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})
        installed_job = instance.job

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
        instance = Job_Instance.objects.get(pk=instance_id)
        url = ClientThread.UPDATE_INSTANCE_URL.format(
                instance.job.job.name, instance.id, agent=instance.job.agent)
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
        instance.update_status = date
        instance.status = status
        instance.save()


    def status_job_instance(self, instance_id, verbosity=0, update=False):
        error_msg = None
        if update:
            try:
                ClientThread.update_instance(instance_id)
            except BadRequest as e:
                error_msg = e.reason
        try:
            instance = Job_Instance.objects.get(pk=instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'instance_id': instance_id})
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
        return instance_infos, 200


    def list_job_instances(self, addresses, update=False, verbosity=0):
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


    def set_job_log_severity(self, address, job_name, severity, date=None,
                             local_severity=None):
        name = '{} on {}'.format(job_name, address)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             infos={'job_name': name})

        try:
            logs_job = Installed_Job.objects.get(pk='rsyslog_job on '
                                                 '{}'.format(address))
        except ObjectDoesNotExist:
            raise BadRequest('The Installed_Job rsyslog isn\'t in the database',
                             404, infos={'job_name': 'rsyslog_job on '
                                         '{}'.format(address)})

        instance = Job_Instance(job=logs_job)
        instance.status = "Starting ..."
        instance.update_status = timezone.now()
        instance.start_date = timezone.now()
        instance.periodic = False
        instance.save()

        instance_args = { 'job_name': [job_name], 'instance_id': [instance.id] }
        date = self.fill_job_instance(instance, instance_args, date)

        agent = instance.job.agent
        logs_job_path = instance.job.job.path
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
            print('instance_id:', instance.id, file=extra_vars)

            argument_instance = Optional_Job_Argument_Instance(
                argument=instance.job.job.optional_job_argument_set.filter(name='disable_code')[0],
                job_instance=instance
            )
            argument_instance.save()
            Job_Argument_Value(
                value=disable,
                argument_instance=argument_instance
            ).save()

            args = self.format_args(instance)
            self.playbook_builder.build_enable_log(
                    syslogseverity, syslogseverity_local,
                    logs_job_path, playbook)
            self.playbook_builder.build_start(
                    'rsyslog_job', instance.id, args,
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
            instance.delete()
            return e.reason, 404

        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        result = { 'msg': 'OK' }
        return result, 200


    def set_job_stat_policy(self, address, job_name, stat_name=None,
                            storage=None, broadcast=None, date=None):
        name = '{} on {}'.format(job_name, address)
        try:
            installed_job = Installed_Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Installed_Job isn\'t in the database', 404,
                             infos={'job_name': name})

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
            rstats_job = Installed_Job.objects.get(pk=rstat_name)
        except ObjectDoesNotExist:
            raise BadRequest('The Installed_Job rstats_job isn\'t in the database',
                             404, infos={'job_name': rstat_name})

        instance = Job_Instance(job=rstats_job)
        instance.status = "Starting ..."
        instance.update_status = timezone.now()
        instance.start_date = timezone.now()
        instance.periodic = False
        instance.save()
 
        instance_args = { 'job_name': [job_name], 'instance_id': [instance.id] }
        date = self.fill_job_instance(instance, instance_args, date)

        agent = instance.job.agent
        rstats_job_path = instance.job.job.path
        installed_name = '{} on {}'.format(job_name, agent.address)
        installed_job = Installed_Job.objects.get(pk=installed_name)
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
                '_rstats_filter.conf.locked').format(job_name, instance.id)
        with self.playbook_builder.playbook_file('rstats') as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_push_file(
                    rstats_filter.name, remote_path, playbook)
            args = self.format_args(instance)
            self.playbook_builder.build_start(
                    'rstats_job', instance.id, args,
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
            instance.delete()
            installed_job.save()
            return e.reason, 404
        instance.status = "Started"
        instance.update_status = timezone.now()
        instance.save()
        result = { 'msg': 'OK' }
        return result, 200


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


if __name__ == '__main__':
    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 1113))
    tcp_socket.listen(10)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()

