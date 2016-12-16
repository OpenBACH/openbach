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



   @file     playbookbuilder.py
   @brief    The Playbook Builder
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import subprocess
import os
from contextlib import contextmanager
import sys
import tempfile
sys.path.insert(0, '/opt/openbach-controller/backend')
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()
from openbach_django.utils import BadRequest


class PlaybookBuilder():
    def __init__(self, path_to_build,
                 path_src='/opt/openbach-controller/openbach-conductor/'):
        self.path_to_build = path_to_build
        self.path_src = path_src

    def _build_helper(self, instance_type, playbook, extra_vars,
                      extra_vars_filename):
        for key, value in extra_vars.items():
            print(key, repr(value), file=extra_vars_filename)

        if instance_type is not None:
            print('    - include: {}{}.yml'
                      .format(self.path_src, instance_type),
                  file=playbook)

        return bool(instance_type)

    def write_hosts(self, address, host_filename=None, hosttype='Agents'):
        if host_filename is None:
            host_filename = '/tmp/openbach_hosts'
        else:
            host_filename = '/tmp/openbach_hosts_{}'.format(host_filename)
        host_filename = '{}_{}'.format(host_filename, address)
        with open(host_filename, 'w') as hosts:
            print('[{}]'.format(hosttype), file=hosts)
            print(address, file=hosts)
        return host_filename

    def write_agent(self, address, agent_filename=None):
        if agent_filename is None:
            agent_filename = '/tmp/openbach_agents'
        else:
            agent_filename = '/tmp/openbach_agents_{}'.format(agent_filename)
        agent_filename = '{}_{}'.format(agent_filename, address)
        with open(agent_filename, 'w') as agents:
            print('agents:', file=agents)
            print('  -', address, file=agents)
        return agent_filename

    @contextmanager
    def playbook_file(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as playbook:
            print('---', file=playbook)
            print(file=playbook)
            print('- hosts: Agents', file=playbook)
            print('  tasks:', file=playbook)
            yield playbook

    @contextmanager
    def extra_vars_file(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as extra_vars:
            yield extra_vars

    def build_start(self, job_name, job_instance_id, scenario_instance_id,
                    owner_scenario_instance_id, job_args, date, interval,
                    playbook_handle, extra_vars_handle):
        instance = 'start_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'job_instance_id:': job_instance_id,
                'scenario_instance_id:': scenario_instance_id,
                'owner_scenario_instance_id:': owner_scenario_instance_id,
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

    def build_status(self, job_name, job_instance_id, date, interval, stop,
                     playbook_handle, extra_vars_handle):
        instance = 'status_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'job_instance_id:': job_instance_id,
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

    def build_restart(self, job_name, job_instance_id, scenario_instance_id,
                      job_args, date, interval, playbook_handle,
                      extra_vars_handle):
        instance = 'restart_job_instance_agent'
        variables = {
                'job_name:': job_name,
                'job_instance_id:': job_instance_id,
                'scenario_instance_id:': scenario_instance_id,
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

    def build_stop(self, job_name, job_instance_id, date, playbook, extra_vars):
        variables = {
                'job_name:': job_name,
                'job_instance_id:': job_instance_id,
                'date: date': date,
        }
        return self._build_helper('stop_job_instance_agent', playbook, variables, extra_vars)

    def build_status_agent(self, playbook_file):
        print('    - name: Get status of openbach-agent', file=playbook_file)
        print('      shell: service openbach-agent status', file=playbook_file)
        print('      when: ansible_distribution_version != "16.04"', file=playbook_file)
        print('    - name: Get status of openbach-agent', file=playbook_file)
        print('      service: name=openbach-agent state=reloaded', file=playbook_file)
        print('      become: yes', file=playbook_file)
        print('      when: ansible_distribution_version == "16.04"', file=playbook_file)
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
                  'dest=/etc/rsyslog.d/{{ job }}{{ job_instance_id }}'
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

    def build_assign_collector(self, collector, playbook_file, extra_vars_file):
        print('    - name: Assign new Collector', file=playbook_file)
        print('      template: src=/opt/openbach-controller/src_agent/openbach-agent/collector.yml.j2 dest=/opt/openbach-agent/collector.yml', file=playbook_file)
        print('      become: yes', file=playbook_file)
        variables = {
            'collector_ip:': collector.address,
            'logstash_logs_port:': collector.logs_port,
            'logstash_stats_port:': collector.stats_port
        }
        return self._build_helper(None, None, variables, extra_vars_file)


    def launch_playbook(self, cmd_ansible):
        p = subprocess.Popen(cmd_ansible, shell=True)
        p.wait()
        if p.returncode:
            raise BadRequest('Ansible playbook execution failed')

