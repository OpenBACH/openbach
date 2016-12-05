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
import signal
import time
import re
from playbookbuilder import PlaybookBuilder
from queue import Queue, Empty
from operator import attrgetter
from datetime import datetime
from fuzzywuzzy import fuzz, process


import sys
sys.path.insert(0, '/opt/openbach-controller/backend')
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()

from django.utils import timezone
from django.db import IntegrityError, transaction
from django.db.utils import DataError
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from openbach_django.models import *
from openbach_django.utils import BadRequest, convert_severity
from openbach_django.utils import send_all, recv_fifo


def signal_term_handler(signal, frame):
    for scenario_instance in Scenario_Instance.objects.all():
        if not scenario_instance.is_stopped:
            scenario_instance.status = "Stopped"
            scenario_instance.status_date = timezone.now()
            scenario_instance.is_stopped = True
            scenario_instance.save()

    exit(0)


class ThreadManager:
    __shared_state = {}  # Borg pattern

    def __init__(self, init=False):
        self.__dict__ = self.__class__.__shared_state
        
        if init:
            self.threads = {}
            self.mutex = threading.Lock()

    def __enter__(self):
        self.mutex.acquire()
        return self.threads

    def __exit__(self, t, v, tb):
        self.mutex.release()


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


class ClientThread(threading.Thread):
    UPDATE_AGENT_URL = 'http://{agent.collector.address}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}"'
    UPDATE_JOB_URL = 'http://{agent.collector.address}:8086/query?db=openbach&epoch=ms&q=SELECT+*+FROM+"0.0.{agent.name}.openbach-agent"+where+_type+=\'job_list\'+GROUP+BY+*+ORDER+BY+DESC+LIMIT+1'
    UPDATE_INSTANCE_URL = 'http://{agent.collector.address}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"0.0.{agent.name}.openbach-agent+"+where+job_name+=+{}+and+job_instance_id+=+{}'

    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.path_src = '/opt/openbach-controller/openbach-conductor/'
        self.playbook_builder = PlaybookBuilder('/tmp/', self.path_src)

    def execute_request(self, data):
        request = '{}_action'.format(data.pop('command'))

        # From this point on, request should contain the
        # name of one of the following method: call it
        try:
            function = getattr(self, request)
        except AttributeError:
            raise BadRequest('Function {} not implemented yet'.format(request),
                             500)

        return function(**data)

    def add_collector_action(self, address, username, password, name,
                             logs_port=None, stats_port=None):
        thread = threading.Thread(
            target=self.add_collector,
            args=(address, username, password, name, logs_port, stats_port))
        thread.start()

        return {}, 202

    def add_collector(self, address, username, password, name, logs_port=None,
                      stats_port=None):
        try:
            command_result = Collector_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            command_result = Collector_Command_Result(address=address)
        if command_result.status_add == None:
            status_add = Command_Result()
            status_add.save()
            command_result.status_add = status_add
            command_result.save()
        else:
            command_result.status_add.reset()
        collector = Collector(address=address)
        if logs_port:
            collector.logs_port = logs_port
        if stats_port:
            collector.stats_port = stats_port
        collector.save()
        host_filename = self.playbook_builder.write_hosts(
            address, 'add_collector', 'Collector')
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('collector_ip:', address, file=extra_vars)
            print('logstash_logs_port:', collector.logs_port, file=extra_vars)
            print('logstash_stats_port:', collector.stats_port, file=extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {0} '
                '-e @/opt/openbach-controller/configs/ips '
                '-e collector_ip={1} '
                '-e @/opt/openbach-controller/configs/all '
                '-e @/opt/openbach-controller/configs/proxy '
                '-e @{2} '
                '-e ansible_ssh_user="{3}" '
                '-e ansible_sudo_pass="{4}" '
                '-e ansible_ssh_pass="{4}" '
                '/opt/openbach-controller/install_collector/collector.yml'
                ' --tags install'
                .format(host_filename, address, extra_vars.name, username, password))
        except BadRequest as e:
            collector.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_add.response = json.dumps(response)
            command_result.status_add.returncode = e.returncode
            command_result.status_add.save()
            raise
        try:
            self.install_agent(address, address, username, password, name)
        except BadRequest as e:
            collector.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_add.response = json.dumps(response)
            command_result.status_add.returncode = e.returncode
            command_result.status_add.save()
            raise
        command_result.status_add.response = json.dumps(None)
        command_result.status_add.returncode = 204
        command_result.status_add.save()

    def modify_collector_action(self, address, logs_port=None, stats_port=None):
        thread = threading.Thread(
            target=self.modify_collector,
            args=(address, logs_port, stats_port))
        thread.start()

        return {}, 202

    def modify_collector(self, address, logs_port=None, stats_port=None):
        try:
            command_result = Collector_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            command_result = Collector_Command_Result(address=address)
        if command_result.status_modify == None:
            status_modify = Command_Result()
            status_modify.save()
            command_result.status_modify = status_modify
            command_result.save()
        else:
            command_result.status_modify.reset()
        try:
            collector = Collector.objects.get(pk=address)
        except ObjectDoesNotExist:
            response = {'address': address}
            response['error'] = 'This Collector is not in the database'
            returncode = 404
            command_result.status_modify.response = json.dumps(response)
            command_result.status_modify.returncode = returncode
            command_result.status_modify.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        if logs_port == None and stats_port == None:
            response = {'error': 'This Collector is not in the database'}
            returncode = 404
            command_result.status_modify.response = json.dumps(
                response)
            command_result.status_modify.returncode = returncode
            command_result.status_modify.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

            raise BadRequest('No modification to do')
        if logs_port:
            collector.logs_port = logs_port
        if stats_port:
            collector.stats_port = stats_port
        collector.save()
        for agent in collector.agent_set.all():
            try:
                self.assign_collector(agent.address, address)
            except BadRequest as e:
                response = e.infos
                response['error'] = e.reason
                command_result.status_modify.response = json.dumps(response)
                command_result.status_modify.returncode = e.returncode
                command_result.status_modify.save()
                raise
        command_result.status_modify.response = json.dumps(None)
        command_result.status_modify.returncode = 204
        command_result.status_modify.save()

    def del_collector_action(self, address):
        thread = threading.Thread(
            target=self.del_collector,
            args=(address,))
        thread.start()

        return {}, 202

    def del_collector(self, address):
        """ returncode is 404 only if the given address does not correspond to a
        collector in the database """
        try:
            command_result = Collector_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            command_result = Collector_Command_Result(address=address)
        if command_result.status_del == None:
            status_del = Command_Result()
            status_del.save()
            command_result.status_del = status_del
            command_result.save()
        else:
            command_result.status_del.reset()
        try:
            collector = Collector.objects.get(pk=address)
        except ObjectDoesNotExist:
            response = {'address': address}
            response['error'] = 'This Collector is not in the database'
            returncode = 404
            command_result.status_del.response = json.dumps(response)
            command_result.status_del.returncode = returncode
            command_result.status_del.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            response = {'address': address}
            response['error'] = 'No Agent is installed on this Collector'
            returncode = 400
            command_result.status_del.response = json.dumps(response)
            command_result.status_del.returncode = returncode
            command_result.status_del.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        if collector.agent_set.exclude(pk=address):
            response = {'address': address}
            response['error'] = 'This Collector is still associated to some Agents'
            returncode = 409
            command_result.status_del.response = json.dumps(response)
            command_result.status_del.returncode = returncode
            command_result.status_del.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        host_filename = self.playbook_builder.write_hosts(
            address, 'del_collector', 'Collector')
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {0} '
                '-e @/opt/openbach-controller/configs/ips '
                '-e collector_ip={1} '
                '-e @/opt/openbach-controller/configs/all '
                '-e @/opt/openbach-controller/configs/proxy '
                '-e ansible_ssh_user="{2}" '
                '-e ansible_sudo_pass="{3}" '
                '-e ansible_ssh_pass="{3}" '
                '/opt/openbach-controller/install_collector/collector.yml'
                ' --tags uninstall'
                .format(host_filename, address, agent.username, agent.password))
        except BadRequest as e:
            response = e.infos
            response['error'] = e.reason
            command_result.status_del.response = json.dumps(response)
            command_result.status_del.returncode = e.returncode
            command_result.status_del.save()
            raise
        try:
            self.uninstall_agent(address)
        except BadRequest as e:
            response = e.infos
            response['error'] = e.reason
            command_result.status_del.response = json.dumps(response)
            command_result.status_del.returncode = e.returncode
            command_result.status_del.save()
            raise
        collector.delete()
        command_result.status_del.response = json.dumps(None)
        command_result.status_del.returncode = 204
        command_result.status_del.save()

    def get_collector_action(self, address):
        return self.get_collector(address)

    def get_collector(self, address):
        try:
            collector = Collector.objects.get(pk=address)
        except ObjectDoesNotExist:
            raise BadRequest('This Collector is not in the database', 404,
                             infos={'address': address})
        response = {'address': collector.address, 'logs_port':
                    collector.logs_port, 'stats_port': collector.stats_port}
        return response, 200

    def list_collectors_action(self):
        return self.list_collectors()

    def list_collectors(self):
        response = []
        for collector in Collector.objects.all():
            collector_info, _ = self.get_collector(collector.address)
            response.append(collector_info)
        return response, 200

    def install_agent_of(self, address, collector_ip, username, password, name):
        self.install_agent(address, collector_ip, username, password, name)

        return []

    def install_agent_action(self, address, collector_ip, username, password,
                             name):
        return self.install_agent(address, collector_ip, username, password,
                                  name, True)

    def install_agent(self, address, collector_ip, username, password, name,
                      action=False):
        try:
            command_result = Agent_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            command_result = Agent_Command_Result(address=address)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        if command_result.status_install == None:
            status_install = Command_Result()
            status_install.save()
            command_result.status_install = status_install
            command_result.save()
        else:
            command_result.status_install.reset()
        agent = Agent(name=name, address=address, username=username)
        agent.set_password(password)
        agent.reachable = True
        agent.update_reachable = timezone.now()
        agent.status = 'Installing ...' 
        agent.update_status = timezone.now()
        try:
            collector = Collector.objects.get(pk=collector_ip)
        except DataError:
            raise BadRequest('You must give an ip address for the Collector')
        except ObjectDoesNotExist:
            response = {'address': collector_ip}
            response['error'] = 'This Collector is not in the database'
            returncode = 404
            command_result.status_install.response = json.dumps(response)
            command_result.status_install.returncode = returncode
            command_result.status_install.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        agent.collector = collector
        try:
            agent.save()
        except IntegrityError:
            response = {'error': 'Name of the Agent already used'}
            command_result.status_install.response = json.dumps(response)
            command_result.status_install.returncode = 400
            command_result.status_install.save()
            raise BadRequest(response['error'])
        if action:
            thread = threading.Thread(
                target=self.launch_install_agent,
                args=(agent, collector))
            thread.start()
            return {}, 202
        self.launch_install_agent(agent, collector)

    def launch_install_agent(self, agent, collector):
        command_result = Agent_Command_Result.objects.get(pk=agent.address)
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'install_agent')
        agent_filename = self.playbook_builder.write_agent(agent.address,
                                                           'install')
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('collector_ip:', collector.address, file=extra_vars)
            print('logstash_logs_port:', collector.logs_port, file=extra_vars)
            print('logstash_stats_port:', collector.stats_port, file=extra_vars)
            print('local_username:', getpass.getuser(), file=extra_vars)
            print('agent_name:', agent.name, file=extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} -e @{} '
                '-e @/opt/openbach-controller/configs/ips '
                '-e @/opt/openbach-controller/configs/proxy '
                '-e @/opt/openbach-controller/configs/all '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" '
                '/opt/openbach-controller/install_agent/agent.yml --tags install'
                .format(host_filename, agent_filename, extra_vars.name, agent=agent))
        except BadRequest as e:
            agent.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_install.response = json.dumps(response)
            command_result.status_install.returncode = e.returncode
            command_result.status_install.save()
            raise
        agent.status = 'Available'
        agent.update_status = timezone.now()
        agent.save()
        # Recuperer la liste des jobs a installer
        list_default_jobs = '/opt/openbach-controller/install_agent/list_default_jobs.txt'
        list_jobs = []
        with open(list_default_jobs, 'r') as f:
            for line in f:
                list_jobs.append(line.rstrip('\n'))
        # Installer les jobs
        list_jobs_failed = []
        for job in list_jobs:
            try:
                self.install_jobs([agent.address], [job])
            except BadRequest:
                list_jobs_failed.append(job)
        result = None
        returncode = 204
        if list_jobs_failed != []:
            result = {'warning': 'Some Jobs couldn’t be installed {}'.format(
                ' '.join(list_jobs_failed))}
            returncode = 200
        command_result.status_install.response = json.dumps(result)
        command_result.status_install.returncode = returncode
        command_result.status_install.save()

    def uninstall_agent_of(self, address):
        self.uninstall_agent(address)

        return []

    def uninstall_agent_action(self, address):
        return self.uninstall_agent(address, True)

    def uninstall_agent(self, address, action=False):
        try:
            command_result = Agent_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            command_result = Agent_Command_Result(address=address)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        if command_result.status_uninstall == None:
            status_uninstall = Command_Result()
            status_uninstall.save()
            command_result.status_uninstall = status_uninstall
            command_result.save()
        else:
            command_result.status_uninstall.reset()
        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            response = {'address': address}
            response['error'] = 'This Agent is not in the database'
            returncode = 404
            command_result.status_uninstall.response = json.dumps(response)
            command_result.status_uninstall.returncode = returncode
            command_result.status_uninstall.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        if action:
            thread = threading.Thread(
                target=self.launch_uninstall_agent,
                args=(agent,))
            thread.start()
            return {}, 202
        self.launch_uninstall_agent(agent)

    def launch_uninstall_agent(self, agent):
        command_result = Agent_Command_Result.objects.get(pk=agent.address)
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'uninstall_agent')
        agent_filename = self.playbook_builder.write_agent(agent.address,
                                                           'uninstall')
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('local_username:', getpass.getuser(), file=extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} -e @{} '
                '-e @/opt/openbach-controller/configs/all '
                '-e @/opt/openbach-controller/configs/proxy '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}"'
                ' /opt/openbach-controller/install_agent/agent.yml --tags uninstall'
                .format(host_filename, agent_filename, extra_vars.name, agent=agent))
        except BadRequest as e:
            agent.status = 'Uninstall failed'
            agent.update_status = timezone.now()
            agent.save()
            response = e.infos
            response['error'] = e.reason
            command_result.status_uninstall.response = json.dumps(response)
            command_result.status_uninstall.returncode = e.returncode
            command_result.status_uninstall.save()
            raise

        agent.delete()
        command_result.status_uninstall.response = json.dumps(None)
        command_result.status_uninstall.returncode = 204
        command_result.status_uninstall.save()

#    def list_agents_of(self, update=False):
#        self.list_agents(update)
#
#        return []

    def list_agents_action(self, update=False):
        return self.list_agents(update)

    def list_agents(self, update=False):
        agents = Agent.objects.all()
        response = []
        for agent in agents:
            agent_infos = agent.get_json()
            if update:
                if agent.reachable and agent.update_status < agent.update_reachable:
                    try:
                        self.update_agent(agent)
                    except BadRequest as e:
                        agent_infos['error'] = e.reason
                    else:
                        agent.refresh_from_db()
            agent_infos['status'] = agent.status
            agent_infos['update_status'] = agent.update_status.astimezone(
                timezone.get_current_timezone())
            response.append(agent_infos)

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

    def retrieve_status_agents_of(self, addresses, update=False):
        self.retrieve_status_agents(addresses, update)

        return []

    def retrieve_status_agents_action(self, addresses, update=False):
        for address in addresses:
            try:
                command_result = Agent_Command_Result.objects.get(pk=address)
            except DataError:
                raise BadRequest('You must give an ip address for all the'
                                 ' Agents')
        thread = threading.Thread(
            target=self.retrieve_status_agents,
            args=(addresses, update))
        thread.start()

        return {}, 202

    def retrieve_status_agents(self, addresses, update=False):
        command_results = {}
        for address in addresses:
            try:
                command_result = Agent_Command_Result.objects.get(pk=address)
            except ObjectDoesNotExist:
                command_result = Agent_Command_Result(address=address)
            if command_result.status_retrieve_status_agent == None:
                status_retrieve_status_agent = Command_Result()
                status_retrieve_status_agent.save()
                command_result.status_retrieve_status_agent = status_retrieve_status_agent
                command_result.save()
            else:
                command_result.status_retrieve_status_agent.reset()
            command_results[address] = command_result
        for agent_ip in addresses:
            command_result = command_results[agent_ip]
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                response = {'error': 'Agent unknown'}
                command_result.status_retrieve_status_agent.response = json.dumps(
                    response)
                command_result.status_retrieve_status_agent.returncode = 404
                command_result.status_retrieve_status_agent.save()
                continue
            host_filename = self.playbook_builder.write_hosts(
                agent.address, 'retrieve_status_agents')
            try:
                subprocess.check_output(
                        ['ping', '-c1', '-w2', agent.address])
            except subprocess.CalledProcessError:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent unreachable'
                agent.update_status= timezone.now()
                agent.save()
                command_result.status_retrieve_status_agent.response = json.dumps(
                    None)
                command_result.status_retrieve_status_agent.returncode = 204
                command_result.status_retrieve_status_agent.save()
                continue
            with self.playbook_builder.playbook_file() as playbook:
                playbook_name = playbook.name
            # [Ugly hack] Reset file to remove the last line
            with open(playbook_name, 'w') as playbook:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
            try:
                self.playbook_builder.launch_playbook(
                    'ansible-playbook -i {} '
                    '-e ansible_ssh_user="{agent.username}" '
                    '-e ansible_ssh_pass="{agent.password}" {}'
                    .format(host_filename, playbook_name, agent=agent))
            except BadRequest:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent reachable but connection impossible'
                agent.update_status= timezone.now()
                agent.save()
                command_result.status_retrieve_status_agent.response = json.dumps(
                    None)
                command_result.status_retrieve_status_agent.returncode = 204
                command_result.status_retrieve_status_agent.save()
                continue
            agent.reachable = True
            agent.update_reachable = timezone.now()
            agent.save()
            with self.playbook_builder.playbook_file() as playbook:
                self.playbook_builder.build_status_agent(playbook) 
            try:
                self.playbook_builder.launch_playbook(
                    'ansible-playbook -i {} '
                    '-e ansible_ssh_user="{agent.username}" '
                    '-e ansible_sudo_pass="{agent.username}" '
                    '-e ansible_ssh_pass="{agent.password}" {}'
                    .format(host_filename, playbook.name, agent=agent))
            except BadRequest as e:
                response = e.infos
                response['error'] = e.reason
                returncode = 404
                command_result.status_retrieve_status_agent.response = json.dumps(
                    response)
                command_result.status_retrieve_status_agent.returncode = returncode
                command_result.status_retrieve_status_agent.save()
                continue
            if update:
                if agent.reachable and agent.update_status < agent.update_reachable:
                    try:
                        self.update_agent(agent)
                    except BadRequest as e:
                        response = e.infos
                        response['error'] = e.reason
                        returncode = 404
                        command_result.status_retrieve_status_agent.response = json.dumps(
                            response)
                        command_result.status_retrieve_status_agent.returncode = returncode
                        command_result.status_retrieve_status_agent.save()
                        continue

        command_result.status_retrieve_status_agent.response = json.dumps(None)
        command_result.status_retrieve_status_agent.returncode = 204
        command_result.status_retrieve_status_agent.save()

    def assign_collector_of(self, address, collector_ip):
        self.assign_collector(address, collector_ip)

    def assign_collector_action(self, address, collector_ip):
        return self.assign_collector(address, collector_ip, True)

    def assign_collector(self, address, collector_ip, action=False):
        try:
            command_result = Agent_Command_Result.objects.get(pk=address)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        except ObjectDoesNotExist:
            command_result = Agent_Command_Result(address=address)
        if command_result.status_assign == None:
            status_assign = Command_Result()
            status_assign.save()
            command_result.status_assign = status_assign
            command_result.save()
        else:
            command_result.status_assign.reset()
        try:
            agent = Agent.objects.get(pk=address)
        except ObjectDoesNotExist:
            response = {'address': address}
            response['error'] = 'This Agent is not in the database'
            returncode = 404
            command_result.status_assign.response = json.dumps(
                response)
            command_result.status_assign.returncode = returncode
            command_result.status_assign.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            collector = Collector.objects.get(pk=collector_ip)
        except DataError:
            raise BadRequest('You must give an ip address for the Collector')
        except ObjectDoesNotExist:
            response = {'address': collector_ip}
            response['error'] = 'This Collector is not in the database'
            returncode = 404
            command_result.status_assign.response = json.dumps(
                response)
            command_result.status_assign.returncode = returncode
            command_result.status_assign.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        if action:
            thread = threading.Thread(
                target=self.launch_assign_collector,
                args=(agent, collector))
            thread.start()
            return {}, 202
        self.launch_assign_collector(agent)

    def launch_assign_collector(self, agent, collector):
        command_result = Agent_Command_Result.objects.get(pk=agent.address)
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'assign_collector')
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_assign_collector(collector, playbook, extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_ssh_pass="{agent.password}" '
                '-e ansible_sudo_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name, agent=agent))
        except BadRequest as e:
            response = e.infos
            response['error'] = e.reason
            command_result.status_assign.response = json.dumps(
                response)
            command_result.status_assign.returncode = e.returncode
            command_result.status_assign.save()
            raise
        agent.collector = collector
        command_result.status_assign.response = json.dumps(None)
        command_result.status_assign.returncode = 204
        command_result.status_assign.save()

    def add_job_of(self, name, path):
        self.add_job(name, path)

        return []

    def add_job_action(self, name, path):
        return self.add_job(name, path)

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
            job_conf = json.dumps(content)
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

        with transaction.atomic():
            try:
                job = Job.objects.get(pk=name)
                job.delete()
            except ObjectDoesNotExist:
                pass

            job = Job(
                name=name,
                path=path,
                help=help,
                job_version=job_version,
                description=description,
                job_conf=job_conf
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
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file})
            elif statistics == None:
                pass
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
                        count=required_arg['count'],
                        rank=rank,
                        job=job
                    ).save()
                    rank += 1
                except IntegrityError:
                    raise BadRequest('The configuration file of the Job is not '
                                     'well formed', 409, {'configuration file':
                                                          config_file})

            for optional_arg in optional_args:
                try:
                    Optional_Job_Argument(
                        name=optional_arg['name'],
                        flag=optional_arg['flag'],
                        type=optional_arg['type'],
                        count=optional_arg['count'],
                        description=optional_arg['description'],
                        job=job
                    ).save()
                except IntegrityError:
                    raise BadRequest('The configuration file of the Job is not well'
                                     ' formed', 409, {'configuration file':
                                                      config_file})
                except KeyError:
                    raise BadRequest('The configuration file of the Job is not well'
                                     ' formed', 409, {'configuration file':
                                                      config_file})

        return None, 204

    def del_job_of(self, name):
        self.del_job(name)

        return []

    def del_job_action(self, name):
        return self.del_job(name)

    def del_job(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404, {
                'job_name': name })
        job.delete()
        return None, 204

#    def list_jobs_of(self):
#        self.list_jobs()
#
#        return []

    def list_jobs_action(self, string_to_search=None, ratio=60):
        return self.list_jobs(string_to_search, ratio)

    def list_jobs(self, string_to_search=None, ratio=60):
        response = []
        if string_to_search:
            try:
                for job in Job.objects.all():
                    match=False
                    #look for a job name matching the string
                    split_job_name=re.split('_|-',job.name)
                    for word in split_job_name:
                        #print("Match ratio of ", fuzz.token_set_ratio(word, string_to_search), "of job ", job.name, word)
                        if fuzz.token_set_ratio(word, string_to_search) > int(ratio):
                            match=True
                            break
                    #look for job keywords matching the string
                    if not match:
                        for keyword in job.keywords.all():
                            #print("Match ratio of ", fuzz.token_set_ratio(keyword, string_to_search), "for keyword", keyword, "of job ", job.name)
                            if fuzz.token_set_ratio(keyword, string_to_search) > int(ratio):
                                match=True
                                break
                    if match:
                        response.append(json.loads(job.job_conf))
                    
                    
            except:
                raise BadRequest('Error when looking for keyword matches', 404, {'job_name': job})
        
        else:
            for job in Job.objects.all():
                response.append(json.loads(job.job_conf))
           
        return response, 200

    def get_job_json_action(self, name):
        return self.get_job_json(name)

    def get_job_json(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExists:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        result = json.loads(job.job_conf)
        return result, 200


    def get_job_keywords_action(self, name):
        return self.get_job_keywords(name)

    def get_job_keywords(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExists:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        result = {'job_name': name, 'keywords': [
            keyword.name for keyword in job.keywords.all()
        ]}
        return result, 200
       

#    def get_job_stats_of(self, name):
#        self.get_job_stats(name)
#
#        return []

    def get_job_stats_action(self, name):
        return self.get_job_stats(name)

    def get_job_stats(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})


        result = {'job_name': name , 'statistics': [] }
        for stat in job.statistic_set.all():
            statistic = {'name': stat.name}
            statistic['description'] = stat.description
            statistic['frequency'] = stat.frequency
            result['statistics'].append(statistic)

        return result, 200

#    def get_job_help_of(self, name):
#        self.get_job_help(name)
#
#        return []

    def get_job_help_action(self, name):
        return self.get_job_help(name)

    def get_job_help(self, name):
        try:
            job = Job.objects.get(pk=name)
        except ObjectDoesNotExist:
            raise BadRequest('This Job isn\'t in the database', 404,
                             {'job_name': name})

        return {'job_name': name, 'help': job.help}, 200

    def install_jobs_of(self, addresses, names, severity=4, local_severity=4):
        self.install_jobs(addresses, names, severity, local_severity)

        return []

    def install_jobs_action(self, addresses, names, severity=4,
                            local_severity=4):
        for address in addresses:
            try:
                command_result = Agent_Command_Result.objects.get(pk=address)
            except DataError:
                raise BadRequest('You must give an ip address for all the'
                                 ' Agents')
        thread = threading.Thread(
            target=self.install_jobs,
            args=(addresses, names, severity, local_severity))
        thread.start()

        return {}, 202

    def install_jobs(self, addresses, names, severity=4, local_severity=4):
        agents = Agent.objects.filter(pk__in=addresses)
        no_agent = set(addresses) - set(map(attrgetter('address'), agents))

        jobs = Job.objects.filter(pk__in=names)
        no_job = set(names) - set(map(attrgetter('name'), jobs))

        for job_name in no_job:
            for address in addresses:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=address, job_name=job_name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=address, job_name=job_name)
                if command_result.status_install == None:
                    status_install = Command_Result()
                    status_install.save()
                    command_result.status_install = status_install
                    command_result.save()
                else:
                    command_result.status_install.reset()
                if address in no_agent:
                    response = {'error': 'Job and Agent unknown'}
                else:
                    response = {'error': 'Job unknown'}
                command_result.status_install.response = json.dumps(response)
                command_result.status_install.returncode = 404
                command_result.status_install.save()

        for agent_ip in no_agent:
            for job_name in names:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=agent_ip, job_name=job_name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=agent_ip, job_name=job_name)
                if command_result.status_install == None:
                    status_install = Command_Result()
                    status_install.save()
                    command_result.status_install = status_install
                    command_result.save()
                else:
                    command_result.status_install.reset()
                if job_name in no_job:
                    continue
                response = {'error': 'Agent unknown'}
                command_result.status_install.response = json.dumps(response)
                command_result.status_install.returncode = 404
                command_result.status_install.save()

        success = True
        for agent in agents:
            for job in jobs:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=agent.address, job_name=job.name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=agent.address, job_name=job.name)
                if command_result.status_install == None:
                    status_install = Command_Result()
                    status_install.save()
                    command_result.status_install = status_install
                    command_result.save()
                else:
                    command_result.status_install.reset()
                host_filename = self.playbook_builder.write_hosts(
                    agent.address, 'install_job')
                try:
                    self.playbook_builder.launch_playbook(
                        'ansible-playbook -i {} '
                        '-e @/opt/openbach-controller/configs/proxy '
                        '-e path_src={path_src} '
                        '-e ansible_ssh_user="{agent.username}" '
                        '-e ansible_sudo_pass="{agent.password}" '
                        '-e ansible_ssh_pass="{agent.password}" '
                        '{job.path}/install_{job.name}.yml'
                        .format(host_filename, path_src=self.path_src,
                                agent=agent, job=job))
                except BadRequest as e:
                    success = False
                    command_result.status_install.response = json.dumps({
                        'error': e.reason})
                    command_result.status_install.returncode = e.returncode
                    command_result.status_install.save()
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
                    command_result.status_install.response = json.dumps(None)
                    command_result.status_install.returncode = 204
                    command_result.status_install.save()

        if not success:
            raise BadRequest('At least one of the installation have failed',
                             404)

    def uninstall_jobs_of(self, addresses, names):
        self.uninstall_jobs(addresses, names)

        return []

    def uninstall_jobs_action(self, addresses, names):
        thread = threading.Thread(
            target=self.uninstall_jobs,
            args=(addresses, names))
        thread.start()

        return {}, 202

    def uninstall_jobs(self, addresses, names):
        agents = Agent.objects.filter(pk__in=addresses)
        no_agent = set(addresses) - set(map(attrgetter('address'), agents))

        jobs = Job.objects.filter(pk__in=names)
        no_job = set(names) - set(map(attrgetter('name'), jobs))

        for job_name in no_job:
            for address in addresses:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=address, job_name=job_name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=address, job_name=job_name)
                if command_result.status_uninstall == None:
                    status_uninstall = Command_Result()
                    status_uninstall.save()
                    command_result.status_uninstall = status_uninstall
                    command_result.save()
                else:
                    command_result.status_install.reset()
                if address in no_agent:
                    response = {'error': 'Job and Agent unknown'}
                else:
                    response = {'error': 'Job unknown'}
                command_result.status_uninstall.response = json.dumps(response)
                command_result.status_uninstall.returncode = 404
                command_result.status_uninstall.save()

        for agent_ip in no_agent:
            for job_name in names:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=agent_ip, job_name=job_name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=agent_ip, job_name=job_name)
                if command_result.status_uninstall == None:
                    status_uninstall = Command_Result()
                    status_uninstall.save()
                    command_result.status_uninstall = status_uninstall
                    command_result.save()
                else:
                    command_result.status_uninstall.reset()
                if job_name in no_job:
                    continue
                response = {'error': 'Agent unknown'}
                command_result.status_uninstall.response = json.dumps(response)
                command_result.status_uninstall.returncode = 404
                command_result.status_uninstall.save()

        for agent in agents:
            for job in jobs:
                try:
                    command_result = Installed_Job_Command_Result.objects.get(
                        agent_ip=agent.address, job_name=job.name)
                except ObjectDoesNotExist:
                    command_result = Installed_Job_Command_Result(
                        agent_ip=agent.address, job_name=job.name)
                if command_result.status_uninstall == None:
                    status_uninstall = Command_Result()
                    status_uninstall.save()
                    command_result.status_uninstall = status_uninstall
                    command_result.save()
                else:
                    command_result.status_uninstall.reset()
                installed_job_name = '{} on {}'.format(job, agent)
                try:
                    installed_job = Installed_Job.objects.get(agent=agent, job=job)
                except ObjectDoesNotExist:
                    jobs_not_installed.append(installed_job_name)
                    command_result.status_uninstall.response = json.dumps(
                        {'msg': 'Job already not installed'})
                    command_result.status_uninstall.returncode = 200
                    command_result.status_uninstall.save()
                    continue
                host_filename = self.playbook_builder.write_hosts(
                    agent.address, 'uninstall_job')
                try:
                    self.playbook_builder.launch_playbook(
                        'ansible-playbook -i {} '
                        '-e path_src={path_src} '
                        '-e ansible_ssh_user="{agent.username}" '
                        '-e ansible_sudo_pass="{agent.password}" '
                        '-e ansible_ssh_pass="{agent.password}" '
                        '{job.path}/uninstall_{job.name}.yml'
                        .format(host_filename, path_src=self.path_src,
                                agent=agent, job=job))
                    installed_job.delete()
                except BadRequest as e:
                    response['error'] = e.reason
                    command_result.status_uninstall.response = json.dumps(response)
                    command_result.status_uninstall.returncode = e.returncode
                    command_result.status_uninstall.save()
                command_result.status_uninstall.response = json.dumps(None)
                command_result.status_uninstall.returncode = 204
                command_result.status_uninstall.save()

    def list_installed_jobs_of(self, address, update=False):
        self.list_installed_jobs(address, update)

        return []

    def list_installed_jobs_action(self, address, update=False):
        return self.list_installed_jobs(address, update)

    def list_installed_jobs(self, address, update=False):
        try:
            agent = Agent.objects.get(pk=address)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             {'address': address})

        response = {'agent': agent.address, 'errors': []}
        if update:
            try:
                result = self.update_jobs(agent.address)
            except BadRequest as e:
                error = {'error': e.reason}
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
                    'update_status': job.update_status.astimezone(
                        timezone.get_current_timezone()),
                }
                job_infos['severity'] = job.severity
                job_infos['default_stat_policy'] = {'storage':
                                                    job.default_stat_storage,
                                                    'broadcast':
                                                    job.default_stat_broadcast}
                job_infos['local_severity'] = job.local_severity
                for statistic_instance in job.statistic_instance_set.all():
                    if 'statistic_instances' not in job_infos:
                        job_infos['statistic_instances'] = []
                    job_infos['statistic_instances'].append({'name':
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
            elif column != 'nb' and column != '_type':
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

    def retrieve_status_jobs_of(self, addresses):
        self.retrieve_status_jobs(addresses)

        return []

    def retrieve_status_jobs_action(self, addresses):
        for address in addresses:
            try:
                command_result = Agent_Command_Result.objects.get(pk=address)
            except DataError:
                raise BadRequest('You must give an ip address for all the'
                                 ' Agents')
        thread = threading.Thread(
            target=self.retrieve_status_jobs,
            args=(addresses,))
        thread.start()

        return {}, 202

    def retrieve_status_jobs(self, addresses):
        error = False
        unknown_agents = []
        for agent_ip in addresses:
            try:
                command_result = Agent_Command_Result.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                command_result = Agent_Command_Result(address=agent_ip)
            if command_result.status_retrieve_status_jobs == None:
                status_retrieve_status_jobs = Command_Result()
                status_retrieve_status_jobs.save()
                command_result.status_retrieve_status_jobs = status_retrieve_status_jobs
                command_result.save()
            else:
                command_result.status_retrieve_status_jobs.reset()
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                response = {'error': 'Agent unknown'}
                command_result.status_retrieve_status_jobs.response = json.dumps(
                    response)
                command_result.status_retrieve_status_jobs.returncode = 404
                command_result.status_retrieve_status_jobs.save()
                continue

            host_filename = self.playbook_builder.write_hosts(
                agent.address, 'retrieve_status_jobs')
            with self.playbook_builder.playbook_file() as playbook:
                self.playbook_builder.build_list_jobs_agent(playbook) 
            try:
                self.playbook_builder.launch_playbook(
                    'ansible-playbook -i {} '
                    '-e ansible_ssh_user="{agent.username}" '
                    '-e ansible_ssh_pass="{agent.password}" {}'
                    .format(host_filename, playbook.name, agent=agent))
            except BadRequest as e:
                response = e.infos
                response['error'] = e.reason
                command_result.status_retrieve_status_jobs.response = json.dumps(
                    response)
                command_result.status_retrieve_status_jobs.returncode = e.returncode
                command_result.status_retrieve_status_jobs.save()
            command_result.status_retrieve_status_jobs.response = json.dumps(
                None)
            command_result.status_retrieve_status_jobs.returncode = 204
            command_result.status_retrieve_status_jobs.save()

    def push_file_of(self, local_path, remote_path, agent_ip):
        self.push_file(local_path, remote_path, agent_ip)

        return []

    def push_file_action(self, local_path, remote_path, agent_ip):
        thread = threading.Thread(
            target=self.push_file,
            args=(local_path, remote_path, agent_ip))
        thread.start()

        return {}, 202

    def push_file(self, local_path, remote_path, agent_ip):
        try:
            agent = Agent.objects.get(pk=agent_ip)
        except ObjectDoesNotExist:
            raise BadRequest('This Agent isn\'t in the database', 404,
                             {'address': agent_ip})

        agent = Agent.objects.get(pk=agent_ip)
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'push_file')
        with self.playbook_builder.playbook_file() as playbook:
            self.playbook_builder.build_push_file(
                    local_path, remote_path, playbook)
        self.playbook_builder.launch_playbook(
            'ansible-playbook -i {} '
            '-e ansible_ssh_user="{agent.username}" '
            '-e ansible_sudo_pass="{agent.password}" '
            '-e ansible_ssh_pass="{agent.password}" {}'
            .format(host_filename, playbook.name, agent=agent))
        return None, 204

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
                    argument=job_instance.job.job.required_job_argument_set.filter(
                        name=arg_name)[0],
                    job_instance=job_instance
                )
                argument_instance.save()
            except IndexError:
                try:
                    argument_instance = Optional_Job_Argument_Instance(
                        argument=job_instance.job.job.optional_job_argument_set.filter(
                            name=arg_name)[0],
                        job_instance=job_instance
                    )
                    argument_instance.save()
                except IndexError:
                    raise BadRequest('Argument \'{}\' don\'t match with'
                                     ' arguments needed or '
                                     'optional'.format(arg_name), 400)
            if isinstance(arg_values, list):
                if not argument_instance.argument.check_count(len(arg_values)):
                    raise BadRequest('This argument \'{}\' does not have the '
                                     'right number of values'.format(arg_name),
                                     400, {'needed_count':
                                           argument_instance.argument.count})
                for arg_value in arg_values:
                    jav = Job_Argument_Value(
                        job_argument_instance=argument_instance)
                    try:
                        jav.check_and_set_value(arg_value)
                    except ValueError as e:
                        raise BadRequest(e.args[0], 400)
                    jav.save()
            else:
                jav = Job_Argument_Value(
                    job_argument_instance=argument_instance)
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
                start_date = datetime.fromtimestamp(
                    date/1000, tz=timezone.get_current_timezone())
                job_instance.start_date = start_date
            job_instance.periodic = False
            job_instance.save()

        if restart:
            job_instance.required_job_argument_instance_set.all().delete()
            job_instance.optional_job_argument_instance_set.all().delete()

        ClientThread.fill_and_check_args(job_instance, instance_args)
        return date

    def start_job_instance_of(self, scenario_instance_id, agent_ip, job_name,
                              instance_args, ofi, finished_queues, offset=0,
                              origin=None, interval=None):
        scenario_instance = Scenario_Instance.objects.get(
            pk=scenario_instance_id)
        if origin is None:
            origin = int(timezone.now().timestamp()*1000)
        date = origin + int(offset)*1000

        result, _ = self.start_job_instance(agent_ip, job_name,
                                            instance_args, date,
                                            interval, scenario_instance_id)

        job_instance_id = result['job_instance_id']
        job_instance = Job_Instance.objects.get(pk=job_instance_id)
        job_instance.openbach_function_instance = ofi
        job_instance.scenario_instance = scenario_instance
        job_instance.save()

        self.watch_job_instance_action(job_instance_id, interval=2)

        with WaitingQueueManager() as waiting_queues:
            waiting_queues[job_instance_id] = (
                scenario_instance_id, ofi.openbach_function_instance_id,
                finished_queues)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect(('', 2845))
        except socket.error as serr:
            raise BadRequest('Connexion error with the Status Manager')
        message = {'type': 'watch', 'scenario_instance_id':
                   scenario_instance_id, 'job_instance_id': job_instance_id}
        sock.send(json.dumps(message).encode())
        sock.close()

        return []

    def start_job_instance_action(self, agent_ip, job_name, instance_args,
                                  date=None, interval=None,
                                  scenario_instance_id=0):
        return self.start_job_instance(agent_ip, job_name, instance_args, date,
                                       interval, scenario_instance_id, True)

    def start_job_instance(self, agent_ip, job_name, instance_args, date=None,
                           interval=None, scenario_instance_id=0, action=False):
        try:
            agent = Agent.objects.get(pk=agent_ip)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
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
        try:
            scenario_instance = Scenario_Instance.objects.get(
                pk=scenario_instance_id)
        except ObjectDoesNotExist:
            owner_scenario_instance_id = scenario_instance_id
        else:
            owner_scenario_instance_id = scenario_instance.openbach_function_instance_master.scenario_instance.id

        job_instance = Job_Instance(job=installed_job)
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()
        job_instance.start_date = timezone.now()
        job_instance.periodic = False
        job_instance.save(force_insert=True)
        date = self.fill_job_instance(job_instance, instance_args, date,
                                      interval)
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'start_job_instance')
        args = self.format_args(job_instance)
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_start(
                    job.name, job_instance.id,
                    scenario_instance_id,
                    owner_scenario_instance_id,
                    args, date, interval,
                    playbook, extra_vars)
        if action:
            thread = threading.Thread(
                target=self.launch_job_instance,
                args=(agent, job_instance, host_filename, playbook, extra_vars))
            thread.start()
            return {'job_instance_id': job_instance.id}, 202

        self.launch_job_instance(agent, job_instance, host_filename, playbook,
                                 extra_vars)
        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        return {'job_instance_id': job_instance.id}, 200

    def launch_job_instance(self, agent, job_instance, host_filename, playbook,
                            extra_vars):
        try:
            command_result = Job_Instance_Command_Result.objects.get(
                pk=job_instance.id)
        except ObjectDoesNotExist:
            command_result = Job_Instance_Command_Result(pk=job_instance.id)
        if command_result.status_start == None:
            status_start = Command_Result()
            status_start.save()
            command_result.status_start = status_start
            command_result.save()
        else:
            command_result.status_start.reset()
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest as e:
            job_instance.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_start.response = json.dumps(response)
            command_result.status_start.returncode = e.returncode
            command_result.status_start.save()
            raise
        command_result.status_start.response = json.dumps(None)
        command_result.status_start.returncode = 204
        command_result.status_start.save()

    def stop_job_instance_of(self, openbach_function_indexes, scenario_instance,
                             date=None):
        job_instance_ids = []
        for openbach_function_id in openbach_function_indexes:
            try:
                ofi = scenario_instance.openbach_function_instance_set.get(
                    openbach_function_instance_id=openbach_function_id)
            except ObjectDoesNotExist:
                #TODO see how to handle this error
                continue
            for job_instance in ofi.job_instance_set.all():
                job_instance_ids.append(job_instance.id)
        self.stop_job_instance(job_instance_ids, date)

        return []

    def stop_job_instance_action(self, job_instance_ids, date=None):
        thread = threading.Thread(
            target=self.stop_job_instance,
            args=(job_instance_ids, date))
        thread.start()

        return {}, 202

    def stop_job_instance(self, job_instance_ids, date=None):
        job_instances = Job_Instance.objects.filter(pk__in=job_instance_ids)

        no_job_instance = set(job_instance_ids) - set(map(attrgetter('id'), job_instances))

        for job_instance_id in no_job_instance:
            try:
                command_result = Job_Instance_Command_Result.objects.get(
                    job_instance_id=job_instance_id)
            except ObjectDoesNotExist:
                command_result = Job_Instance_Command_Result(
                    job_instance_id=job_instance_id)
            if command_result.status_stop == None:
                status_stop = Command_Result()
                status_stop.save()
                command_result.status_stop = status_stop
                command_result.save()
            else:
                command_result.status_stop.reset()
            response = {'error': 'Job Instance unknown'}
            command_result.status_stop.response = json.dumps(response)
            command_result.status_stop.returncode = 404
            command_result.status_stop.save()

        if not date:
            date = 'now'
            stop_date = timezone.now()
        else:
            stop_date = datetime.fromtimestamp(
                date/1000, tz=timezone.get_current_timezone())

        for job_instance in job_instances:
            try:
                command_result = Job_Instance_Command_Result.objects.get(
                    job_instance_id=job_instance.id)
            except ObjectDoesNotExist:
                command_result = Job_Instance_Command_Result(
                    job_instance_id=job_instance.id)
            if command_result.status_stop == None:
                status_stop = Command_Result()
                status_stop.save()
                command_result.status_stop = status_stop
                command_result.save()
            else:
                command_result.status_stop.reset()
            if job_instance.is_stopped:
                command_result.status_stop.response = json.dumps(
                    {'msg': 'Job Instance already stopped'})
                command_result.status_stop.returncode = 200
                command_result.status_stop.save()
                continue
            job_instance.stop_date = stop_date
            job_instance.save()
            job = job_instance.job.job
            agent = job_instance.job.agent
            host_filename = self.playbook_builder.write_hosts(
                agent.address, 'stop_job_instance')
            with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
                self.playbook_builder.build_stop(
                        job.name, job_instance.id, date,
                        playbook, extra_vars)
            try:
                self.playbook_builder.launch_playbook(
                    'ansible-playbook -i {} -e @{} '
                    '-e ansible_ssh_user="{agent.username}" '
                    '-e ansible_sudo_pass="{agent.password}" '
                    '-e ansible_ssh_pass="{agent.password}" {}'
                    .format(host_filename, extra_vars.name, playbook.name,
                            agent=agent))
            except BadRequest as e:
                response = e.infos
                response['error'] = e.reason
                command_result.status_stop.response = json.dumps(response)
                command_result.status_stop.returncode = e.returncode
                command_result.status_stop.save()
            else:
                if stop_date <= timezone.now():
                    job_instance.is_stopped = True
                    job_instance.save()
                command_result.status_stop.response = json.dumps(None)
                command_result.status_stop.returncode = 204
                command_result.status_stop.save()

    def restart_job_instance_of(self, job_instance_id, scenario_instance_id,
                             instance_args, date=None, interval=None):
        self.restart_job_instance(job_instance_id, instance_args, date,
                                  interval, scenario_instance_id)

        return []

    def restart_job_instance_action(self, job_instance_id, instance_args,
                                    date=None, interval=None,
                                    scenario_instance_id=0):
        thread = threading.Thread(
            target=self.restart_job_instance,
            args=(job_instance_id, instance_args, date, interval,
                  scenario_instance_id))
        thread.start()

        return {}, 202

    def restart_job_instance(self, job_instance_id, instance_args, date=None,
                             interval=None, scenario_instance_id=0):
        try:
            command_result = Job_Instance_Command_Result.objects.get(
                pk=job_instance_id)
        except ObjectDoesNotExist:
            command_result = Job_Instance_Command_Result(address=address)
        if command_result.status_restart == None:
            status_restart = Command_Result()
            status_restart.save()
            command_result.status_restart = status_restart
            command_result.save()
        else:
            command_result.status_restart.reset()
        try:
            job_instance = Job_Instance.objects.get(pk=job_instance_id)
        except ObjectDoesNotExist:
            response = {'job_instance_id': job_instance_id}
            response['error'] = 'This Job Instance isn\'t in the database'
            returncode = 404
            command_result.status_restart.response = json.dumps(response)
            command_result.status_restart.returncode = returncode
            command_result.status_restart.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

        date = self.fill_job_instance(job_instance, instance_args, date,
                                      interval, True)
        job = job_instance.job.job
        agent = job_instance.job.agent
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'restart_job_instance')
        args = self.format_args(job_instance)
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_restart(
                    job.name, job_instance.id, scenario_instance_id,
                    args, date, interval, playbook, extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest as e:
            job_instance.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_restart.response = json.dumps(response)
            command_result.status_restart.returncode = e.returncode
            command_result.status_restart.save()
            raise
        job_instance.is_stopped = False
        job_instance.status = "Restarted"
        job_instance.update_status = timezone.now()
        job_instance.save()
        command_result.status_restart.response = json.dumps(None)
        command_result.status_restart.returncode = 204
        command_result.status_restart.save()

    def watch_job_instance_of(self, job_instance_id, date=None, interval=None,
                           stop=None):
        #TODO est-ce utile ? toutes les job_instance sont lance avec une watch
        #     dans les scenarios
        self.watch_job_instance(job_instance_id, date, interval, stop)

        return []

    def watch_job_instance_action(self, job_instance_id, date=None,
                                  interval=None, stop=None):
        return self.watch_job_instance(job_instance_id, date, interval, stop,
                                       True)

    def watch_job_instance(self, job_instance_id, date=None, interval=None,
                           stop=None, action=False):
        try:
            job_instance = Job_Instance.objects.get(pk=job_instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'job_instance_id': job_instance_id})
        installed_job = job_instance.job

        try:
            watch = Watch.objects.get(pk=job_instance_id)
            if not interval and not stop:
                raise BadRequest('A Watch already exists in the database', 400)
        except ObjectDoesNotExist:
            watch = Watch(job=installed_job, job_instance_id=job_instance_id)

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
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'watch_job_instance')
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_status(
                    job.name, job_instance_id,
                    date, interval, stop,
                    playbook, extra_vars)
        if action:
            thread = threading.Thread(
                target=self.launch_watch,
                args=(agent, watch, host_filename, playbook, extra_vars))
            thread.start()
            return {}, 202

        self.launch_watch(agent, watch, host_filename, playbook, extra_vars)
        if should_delete_watch:
            watch.delete()
        return None, 204

    def launch_watch(self, agent, watch, host_filename, playbook, extra_vars):
        try:
            command_result = Job_Instance_Command_Result.objects.get(
                pk=watch.job_instance_id)
        except ObjectDoesNotExist:
            command_result = Job_Instance_Command_Result(
                job_instance_id=watch.job_instance_id)
        if command_result.status_watch == None:
            status_watch = Command_Result()
            status_watch.save()
            command_result.status_watch = status_watch
            command_result.save()
        else:
            command_result.status_watch.reset()
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest as e:
            watch.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_watch.response = json.dumps(response)
            command_result.status_watch.returncode = e.returncode
            command_result.status_watch.save()
            raise
        command_result.status_watch.response = json.dumps(None)
        command_result.status_watch.returncode = 204
        command_result.status_watch.save()

    @staticmethod
    def update_instance(job_instance_id):
        job_instance = Job_Instance.objects.get(pk=job_instance_id)
        url = ClientThread.UPDATE_INSTANCE_URL.format(
            job_instance.job.job.name, job_instance.id,
            agent=job_instance.job.agent)
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

#    def status_job_instance_of(self, job_instance_id, update=False):
#        self.status_job_instance(job_instance_id, update)
#
#        return []

    def status_job_instance_action(self, job_instance_id, update=False):
        return self.status_job_instance(job_instance_id, update)

    def status_job_instance(self, job_instance_id, update=False):
        error_msg = None
        if update:
            try:
                ClientThread.update_instance(job_instance_id)
            except BadRequest as e:
                error_msg = e.reason
        try:
            job_instance = Job_Instance.objects.get(pk=job_instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Job Instance isn\'t in the database', 404,
                             {'job_instance_id': job_instance_id})
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
        instance_infos['update_status'] = job_instance.update_status.astimezone(
            timezone.get_current_timezone())
        instance_infos['status'] = job_instance.status
        instance_infos['start_date'] = job_instance.start_date.astimezone(
            timezone.get_current_timezone())
        try:
            instance_infos['stop_date'] = job_instance.stop_date.astimezone(
                timezone.get_current_timezone())
        except AttributeError:
            instance_infos['stop_date'] = 'Not programmed yet'
        if error_msg is not None:
            instance_infos['error'] = error_msg
            instance_infos['job_name'] = job_instance.job.__str__()
        return instance_infos, 200

#    def list_job_instances_of(self, addresses, update=False):
#        self.list_job_instances(addresses, update)
#
#        return []

    def list_job_instances_action(self, addresses, update=False):
        return self.list_job_instances(addresses, update)

    def list_job_instances(self, addresses, update=False):
        if not addresses:
            agents = Agent.objects.all()
        else:
            agents = Agent.objects.filter(pk__in=addresses)
        agents = agents.prefetch_related('installed_job_set')

        response = {'instances': []}
        try:
            for agent in agents:
                job_instances_for_agent = {'address': agent.address,
                                           'installed_jobs': []}
                for job in agent.installed_job_set.all():
                    job_instances_for_job = {'job_name': job.__str__(),
                                             'instances': []}
                    for job_instance in job.job_instance_set.filter(is_stopped=False):
                        instance_infos, _ = self.status_job_instance(
                            job_instance.id, update)
                        job_instances_for_job['instances'].append(instance_infos)
                    if job_instances_for_job['instances']:
                        job_instances_for_agent['installed_jobs'].append(
                            job_instances_for_job)
                if job_instances_for_agent['installed_jobs']:
                    response['instances'].append(job_instances_for_agent)
        except DataError:
            raise BadRequest('You must give an ip address for all the Agents')
        return response, 200

    def set_job_log_severity_of(self, address, job_name, severity,
                                scenario_instance_id, date=None,
                                local_severity=None):
        self.set_job_log_severity(address, job_name, severity, date,
                                  local_severity, scenario_instance_id)

        return []

    def set_job_log_severity_action(self, address, job_name, severity,
                                    date=None, local_severity=None,
                                    scenario_instance_id=0):
        return self.set_job_log_severity(address, job_name, severity, date,
                                         local_severity, scenario_instance_id,
                                         True)

    def set_job_log_severity(self, address, job_name, severity, date=None,
                             local_severity=None, scenario_instance_id=0,
                             action=False):
        try:
            command_result = Installed_Job_Command_Result.objects.get(
                agent_ip=address, job_name=job_name)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        except ObjectDoesNotExist:
            command_result = Installed_Job_Command_Result(
                agent_ip=address, job_name=job_name)
        if command_result.status_log_severity == None:
            status_log_severity = Command_Result()
            status_log_severity.save()
            command_result.status_log_severity = status_log_severity
            command_result.save()
        else:
            command_result.status_log_severity.reset()
        try:
            job = Job.objects.get(name=job_name)
        except ObjectDoesNotExist:
            response = {'job_name': job_name}
            response['error'] = 'This Job isn\'t in the database'
            returncode = 404
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = returncode
            command_result.status_log_severity.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            agent = Agent.objects.get(address=address)
        except ObjectDoesNotExist:
            response = {'agent_ip': address}
            response['error'] = 'This Agent isn\'t in the database'
            returncode = 404
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = returncode
            command_result.status_log_severity.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            installed_job = Installed_Job.objects.get(agent=agent, job=job)
        except ObjectDoesNotExist:
            response = {'job_name': installed_job}
            response['error'] = 'This Installed_Job isn\'t in the database'
            returncode = 404
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = returncode
            command_result.status_log_severity.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

        try:
            job = Job.objects.get(name='rsyslog_job')
        except ObjectDoesNotExist:
            response = {'job_name': 'rsyslog_job'}
            response['error'] = 'The Job rsyslog_job isn\'t in the database'
            returncode = 404
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = returncode
            command_result.status_log_severity.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            logs_job = Installed_Job.objects.get(job=job, agent=agent)
        except ObjectDoesNotExist:
            response = {'job_name': 'rsyslog_job on {}'.format(address)}
            response['error'] = 'The Installed_Job rsyslog isn\'t in the database'
            returncode = 404
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = returncode
            command_result.status_log_severity.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

        job_instance = Job_Instance(job=logs_job)
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()
        job_instance.start_date = timezone.now()
        job_instance.periodic = False
        job_instance.save(force_insert=True)

        if action:
            thread = threading.Thread(
                target=self.launch_set_job_log_severity,
                args=(job_instance, job_name, severity, date, local_severity,
                      scenario_instance_id))
            thread.start()
            return {}, 202
        self.launch_set_job_log_severity(job_instance, job_name, severity, date,
                                         local_severity, scenario_instance_id)

    def launch_set_job_log_severity(self, job_instance, job_name, severity,
                                    date, local_severity, scenario_instance_id):
        try:
            scenario_instance = Scenario_Instance.objects.get(
                pk=scenario_instance_id)
        except ObjectDoesNotExist:
            owner_scenario_instance_id = scenario_instance_id
        else:
            owner_scenario_instance_id = scenario_instance.openbach_function_instance_master.scenario_instance.id
        agent = job_instance.job.agent
        job = Job.objects.get(name=job_name)
        installed_job = Installed_Job.objects.get(agent=agent, job=job)
        command_result = Installed_Job_Command_Result.objects.get(
            agent_ip=agent.address, job_name=job_name)
        instance_args = {'job_instance_id': job_instance.id, 'job_name':
                         [job_name]}
        date = self.fill_job_instance(job_instance, instance_args, date)

        logs_job_path = job_instance.job.job.path
        syslogseverity = convert_severity(int(severity))
        if not local_severity:
            local_severity = installed_job.local_severity
        syslogseverity_local = convert_severity(int(local_severity))
        disable = 0
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'set_job_log_severity')
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            if syslogseverity == 8:
                disable += 1
            else:
                print('collector_ip:', agent.collector.address, file=extra_vars)
                print('syslogseverity:', syslogseverity, file=extra_vars)
            if syslogseverity_local == 8:
                disable += 2
            else:
                print('syslogseverity_local:', syslogseverity_local, file=extra_vars)
            print('job:', job_name, file=extra_vars)

            argument_instance = Optional_Job_Argument_Instance(
                argument=job_instance.job.job.optional_job_argument_set.filter(
                    name='disable_code')[0],
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
                    'rsyslog_job', job_instance.id, scenario_instance_id,
                    owner_scenario_instance_id, args, date, None, playbook,
                    extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e @/opt/openbach-controller/configs/all '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest as e:
            job_instance.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_log_severity.response = json.dumps(response)
            command_result.status_log_severity.returncode = e.returncode
            command_result.status_log_severity.save()
            raise
        installed_job.severity = severity
        installed_job.local_severity = local_severity
        installed_job.save()

        result = None
        returncode = 204
        if scenario_instance_id != 0:
            try:
                scenario_instance = Scenario_Instance(pk=scenario_instance_id)
            except ObjectDoesNotExist:
                result = {'warning': 'scenario_instance_id given does not match'
                          ' with any Scenario_Instance'}
                returncode = 200
            else:
                job_instance.scenario_instance = scenario_instance
        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        command_result.status_log_severity.response = json.dumps(result)
        command_result.status_log_severity.returncode = returncode
        command_result.status_log_severity.save()

    def set_job_stat_policy_of(self, address, job_name, scenario_instance_id,
                              stat_name=None, storage=None, broadcast=None,
                              date=None):
        self.set_job_stat_policy(address, job_name, stat_name,
                                 storage, broadcast, date,
                                 scenario_instance_id)

        return []

    def set_job_stat_policy_action(self, address, job_name, stat_name=None,
                                   storage=None, broadcast=None, date=None,
                                   scenario_instance_id=0):
        return self.set_job_stat_policy(address, job_name, stat_name,
                                        storage, broadcast, date,
                                        scenario_instance_id, True)

    def set_job_stat_policy(self, address, job_name, stat_name=None,
                            storage=None, broadcast=None, date=None,
                            scenario_instance_id=0, action=False):
        try:
            command_result = Installed_Job_Command_Result.objects.get(
                agent_ip=address, job_name=job_name)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        except ObjectDoesNotExist:
            command_result = Installed_Job_Command_Result(
                agent_ip=address, job_name=job_name)
        if command_result.status_stat_policy == None:
            status_stat_policy = Command_Result()
            status_stat_policy.save()
            command_result.status_stat_policy = status_stat_policy
            command_result.save()
        else:
            command_result.status_stat_policy.reset()
        try:
            job = Job.objects.get(name=job_name)
        except ObjectDoesNotExist:
            response = {'job_name': job_name}
            response['error'] = 'This Job isn\'t in the database'
            returncode = 404
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = returncode
            command_result.status_stat_policy.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            agent = Agent.objects.get(address=address)
        except ObjectDoesNotExist:
            response = {'agent_ip': address}
            response['error'] = 'This Agent isn\'t in the database'
            returncode = 404
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = returncode
            command_result.status_stat_policy.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            installed_job = Installed_Job.objects.get(agent=agent, job=job)
        except ObjectDoesNotExist:
            response = {'job_name': installed_job}
            response['error'] = 'This Installed_Job isn\'t in the database'
            returncode = 404
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = returncode
            command_result.status_stat_policy.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

        if stat_name != None:
            statistic = installed_job.job.statistic_set.filter(name=stat_name)
            if not statistic:
                response = {'error': 'The statistic \'{}\' isn\'t produce by '
                            'the Job \'{}\''.format(stat_name, job_name)}
                returncode = 400
                command_result.status_stat_policy.response = json.dumps(
                    response)
                command_result.status_stat_policy.returncode = returncode
                command_result.status_stat_policy.save()
                reason = response.pop('error')
                raise BadRequest(reason, returncode, infos=response)
            statistic = statistic[0]
            stat = Statistic_Instance.objects.get(stat=statistic,
                                                  job=installed_job)
            if not stat:
                stat = Statistic_Instance(stat=statistic, job=installed_job)
                stat.save()
            if storage == None and broadcast == None:
                stat.delete()
            else:
                if broadcast != None:
                    stat.broadcast = broadcast
                if storage != None:
                    stat.storage = storage
                stat.save()
        else:
            if broadcast != None:
                installed_job.default_stat_broadcast = broadcast
            if storage != None:
                installed_job.default_stat_storage = storage
        installed_job.save()

        try:
            job = Job.objects.get(name='rstats_job')
        except ObjectDoesNotExist:
            response = {'job_name': 'rstats_job'}
            response['error'] = 'The Job rstats_job isn\'t in the database'
            returncode = 404
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = returncode
            command_result.status_stat_policy.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)
        try:
            rstats_job = Installed_Job.objects.get(job=job, agent=agent)
        except ObjectDoesNotExist:
            response = {'job_name': rstat_job}
            response['error'] = 'The Installed_Job rstats_job isn\'t in the database'
            returncode = 404
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = returncode
            command_result.status_stat_policy.save()
            reason = response.pop('error')
            raise BadRequest(reason, returncode, infos=response)

        job_instance = Job_Instance(job=rstats_job)
        job_instance.status = "Starting ..."
        job_instance.update_status = timezone.now()
        job_instance.start_date = timezone.now()
        job_instance.periodic = False
        job_instance.save(force_insert=True)

        if action:
            thread = threading.Thread(
                target=self.launch_set_job_stat_policy,
                args=(job_instance, job_name, date,
                      scenario_instance_id))
            thread.start()
            return {}, 202
        self.launch_set_job_stat_policy(job_instance, job_name, date,
                                        scenario_instance_id)

    def launch_set_job_stat_policy(self, job_instance, job_name, date,
                                   scenario_instance_id):
        try:
            scenario_instance = Scenario_Instance.objects.get(
                pk=scenario_instance_id)
        except ObjectDoesNotExist:
            owner_scenario_instance_id = scenario_instance_id
        else:
            owner_scenario_instance_id = scenario_instance.openbach_function_instance_master.scenario_instance.id
        agent = job_instance.job.agent
        job = Job.objects.get(name=job_name)
        installed_job = Installed_Job.objects.get(agent=agent, job=job)
        command_result = Installed_Job_Command_Result.objects.get(
            agent_ip=agent.address, job_name=job_name)
        instance_args = {'job_instance_id': job_instance.id, 'job_name':
                         [job_name]}
        date = self.fill_job_instance(job_instance, instance_args, date)

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
        host_filename = self.playbook_builder.write_hosts(
            agent.address, 'set_job_stat_policy')
        remote_path = ('/opt/openbach-jobs/{0}/{0}{1}'
                '_rstats_filter.conf.locked').format(job_name, job_instance.id)
        with self.playbook_builder.playbook_file() as playbook, self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_push_file(
                    rstats_filter.name, remote_path, playbook)
            args = self.format_args(job_instance)
            self.playbook_builder.build_start(
                    'rstats_job', job_instance.id, scenario_instance_id,
                    owner_scenario_instance_id, args, date, None, playbook,
                    extra_vars)
        try:
            self.playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} '
                '-e @/opt/openbach-controller/configs/all '
                '-e ansible_ssh_user="{agent.username}" '
                '-e ansible_sudo_pass="{agent.password}" '
                '-e ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest as e:
            job_instance.delete()
            response = e.infos
            response['error'] = e.reason
            command_result.status_stat_policy.response = json.dumps(response)
            command_result.status_stat_policy.returncode = e.returncode
            command_result.status_stat_policy.save()
            raise
        job_instance.status = "Started"
        job_instance.update_status = timezone.now()
        job_instance.save()
        command_result.status_stat_policy.response = json.dumps(None)
        command_result.status_stat_policy.returncode = 204
        command_result.status_stat_policy.save()

    def if_of(self, condition, openbach_functions_true,
              openbach_functions_false, table, queues, scenario_instance,
              openbach_function_instance_id):
        thread_list = []
        if condition.get_value():
            for id_ in openbach_functions_true:
                entry = table[id_]
                openbach_functions_only_false = [ x for x in
                                                  openbach_functions_false if x
                                                  not in openbach_functions_true
                                                ]
                entry['wait_for_launched'] = set([ x for x in
                                                   entry['wait_for_launched']
                                                   if x not in
                                                   openbach_functions_only_false ])
                entry['wait_for_finished'] = set([ x for x in
                                                   entry['wait_for_finished']
                                                   if x not in
                                                   openbach_functions_only_false ])
                try:
                    entry['wait_if_true'].remove(openbach_function_instance_id)
                    entry['wait_if_false'].remove(openbach_function_instance_id)
                except KeyError:
                    pass
                self.check_programmable(id_, table)
                if entry['programmable']:
                    thread = threading.Thread(
                        target=self.launch_openbach_function_instance,
                        args=(scenario_instance, int(id_), table, queues))
                    thread.do_run = True
                    thread.start()
                    with ThreadManager() as threads:
                        if scenario_instance.id not in threads:
                            threads[scenario_instance.id] = {}
                        threads[scenario_instance.id][id_] = thread
                    thread_list.append(thread)
        else:
            for id_ in openbach_functions_false:
                entry = table[id_]
                openbach_functions_only_true = [ x for x in
                                                 openbach_functions_true if x
                                                 not in openbach_functions_false
                                               ]
                entry['wait_for_launched'] = set([ x for x in
                                                   entry['wait_for_launched']
                                                   if x not in
                                                   openbach_functions_only_true ])
                entry['wait_for_finished'] = set([ x for x in
                                                   entry['wait_for_finished']
                                                   if x not in
                                                   openbach_functions_only_true ])
                entry['wait_if_false'].remove(openbach_function_instance_id)
                try:
                    entry['wait_if_true'].remove(openbach_function_instance_id)
                except KeyError:
                    pass
                self.check_programmable(id_, table)
                if entry['programmable']:
                    thread = threading.Thread(
                        target=self.launch_openbach_function_instance,
                        args=(scenario_instance, int(id_), table, queues))
                    thread.do_run = True
                    thread.start()
                    with ThreadManager() as threads:
                        if scenario_instance.id not in threads:
                            threads[scenario_instance.id] = {}
                        threads[scenario_instance.id][id_] = thread
                    thread_list.append(thread)
        return thread_list

    @staticmethod
    def check_programmable(ofi_id, table):
        entry = table[ofi_id]
        if entry['wait_while']:
            entry['programmable'] = False
        elif entry['wait_while_end']:
            entry['programmable'] = False
        elif entry['wait_if_true']:
            entry['programmable'] = False
        elif entry['wait_if_false']:
            entry['programmable'] = False
        else:
            entry['programmable'] = True

    def while_of(self, condition, openbach_functions_while,
                 openbach_functions_end, table, queues, scenario_instance,
                 openbach_function_instance_id):
        threads = []
        if condition.get_value():
            table[openbach_function_instance_id]['wait_for_launched'].clear()
            for ofi_id in openbach_functions_while:
                table[openbach_function_instance_id]['wait_for_launched'].add(
                    int(ofi_id))
                table[int(ofi_id)]['is_waited_for_launched'].add(
                    openbach_function_instance_id)
                # TODO virer les 2 prochains clear et mettre les id qui gene sur
                # le 1er while
                #table[int(ofi_id)]['wait_for_launched'].clear()
                #table[int(ofi_id)]['wait_for_finished'].clear()
                if table[int(ofi_id)]['if_false']:
                    for id_ in table[int(ofi_id)]['if_false']:
                        table[id_]['wait_if_false'].add(int(ofi_id))
                if table[int(ofi_id)]['if_true']:
                    for id_ in table[int(ofi_id)]['if_true']:
                        table[id_]['wait_if_true'].add(int(ofi_id))
                if table[int(ofi_id)]['while']:
                    for id_ in table[int(ofi_id)]['while']:
                        table[id_]['wait_while'].add(int(ofi_id))
                if table[int(ofi_id)]['while_end']:
                    for id_ in table[int(ofi_id)]['while_end']:
                        table[id_]['wait_while_end'].add(int(ofi_id))
                try:
                    table[int(ofi_id)]['wait_while'].remove(
                        openbach_function_instance_id)
                except KeyError:
                    pass
                self.check_programmable(int(ofi_id), table)
                if table[int(ofi_id)]['programmable']:
                    thread = threading.Thread(
                        target=self.launch_openbach_function_instance,
                        args=(scenario_instance, int(ofi_id), table, queues))
                    thread.do_run = True
                    thread.start()
                    with ThreadManager() as threads:
                        if scenario_instance.id not in threads:
                            threads[scenario_instance.id] = {}
                        threads[scenario_instance.id][ofi_id] = thread
                    threads.append(thread)
            if table[openbach_function_instance_id]['programmable']:
                thread = threading.Thread(
                    target=self.launch_openbach_function_instance,
                    args=(scenario_instance, openbach_function_instance_id,
                          table, queues))
                thread.do_run = True
                thread.start()
                with ThreadManager() as threads:
                    if scenario_instance.id not in threads:
                        threads[scenario_instance.id] = {}
                    threads[scenario_instance.id][ofi_id] = thread
                threads.append(thread)
        else:
            for ofi_id in openbach_functions_end:
                table[int(ofi_id)]['wait_while_end'].remove(
                    openbach_function_instance_id)
                self.check_programmable(int(ofi_id), table)
                if table[int(ofi_id)]['programmable']:
                    thread = threading.Thread(
                        target=self.launch_openbach_function_instance,
                        args=(scenario_instance, int(ofi_id), table, queues))
                    thread.do_run = True
                    thread.start()
                    with ThreadManager() as threads:
                        if scenario_instance.id not in threads:
                            threads[scenario_instance.id] = {}
                        threads[scenario_instance.id][ofi_id] = thread
                    threads.append(thread)
        return threads

    @staticmethod
    def first_check_on_scenario(scenario_json):
        if 'name' not in scenario_json:
            return False
        if not isinstance(scenario_json['name'], str):
            return False
        if 'description' in scenario_json:
            if not isinstance(scenario_json['description'], str):
                return False
        if 'arguments' in scenario_json:
            if not isinstance(scenario_json['arguments'], dict):
                return False
            for argument, description in scenario_json['arguments'].items():
                if not isinstance(argument, str):
                    return False
                if not isinstance(description, str):
                    return False
        if 'constants' in scenario_json:
            if not isinstance(scenario_json['constants'], dict):
                return False
            for constant, _ in scenario_json['constants'].items():
                if not isinstance(constant, str):
                    return False
        if 'openbach_functions' in scenario_json:
            if not isinstance(scenario_json['openbach_functions'], list):
                return False
            known = {'wait'}
            for openbach_function in scenario_json['openbach_functions']:
                if not isinstance(openbach_function, dict):
                    return False
                if 'wait' in openbach_function:
                    if not isinstance(openbach_function['wait'], dict):
                        return False
                    at_least_one = False
                    try:
                        if not isinstance(openbach_function['wait']['time'],
                                          int):
                            return False
                        at_least_one = True
                    except KeyError:
                        pass
                    try:
                        if not isinstance(openbach_function['wait']['finished_indexes'],
                                          list):
                            return False
                        at_least_one = True
                    except KeyError:
                        pass
                    try:
                        if not isinstance(openbach_function['wait']['launched_indexes'],
                                          list):
                            return False
                    except KeyError:
                        if not at_least_one:
                            return False
                other = [k for k in openbach_function if k not in known]
                if len(other) != 1:
                    return False
                if not isinstance(openbach_function[other[0]], dict):
                    return False
        return True

    @staticmethod
    def check_reference(arg_value):
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
                return True, scenario_arg
        else:
            value = arg_value

        return False, value

    @staticmethod
    def check_type_or_get_reference(argument, arg_value):
        expected_type = argument.type
        is_reference, value = ClientThread.check_reference(arg_value)
        if is_reference:
            return value
        av = Argument_Value()
        if expected_type == 'None':
            return False
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
    def register_scenario(scenario_json, name, project=None, scenario=None):
        try:
            description = scenario_json['description']
        except KeyError:
            description = None
        scenario_string = json.dumps(scenario_json)

        scenario = Scenario(name=name, description=description,
                            scenario=scenario_string, project=project)
        try:
            scenario.save(force_insert=True)
        except IntegrityError:
            raise BadRequest('This name of Scenario \'{}\' is already'
                             ' used'.format(name), 409)
        try:
            result = ClientThread.register_scenario_arguments(scenario,
                                                              scenario_json)
        except BadRequest:
            scenario.delete()
            raise
        return result

    @staticmethod
    def check_condition(condition):
        try:
            condition_type = condition.pop('type')
        except KeyError:
            raise BadRequest('This Condition is malformed (no type)')
        if condition_type == '=':
            try:
                operand1 = condition.pop('operand1')
                operand2 = condition.pop('operand2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_operand(operand1)
            ClientThread.check_operand(operand2)
        elif condition_type == '<=':
            try:
                operand1 = condition.pop('operand1')
                operand2 = condition.pop('operand2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_operand(operand1)
            ClientThread.check_operand(operand2)
        elif condition_type == '<':
            try:
                operand1 = condition.pop('operand1')
                operand2 = condition.pop('operand2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_operand(operand1)
            ClientThread.check_operand(operand2)
        elif condition_type == '>=':
            try:
                operand1 = condition.pop('operand1')
                operand2 = condition.pop('operand2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_operand(operand1)
            ClientThread.check_operand(operand2)
        elif condition_type == '>':
            try:
                operand1 = condition.pop('operand1')
                operand2 = condition.pop('operand2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_operand(operand1)
            ClientThread.check_operand(operand2)
        elif condition_type == 'not':
            try:
                new_condition = condition.pop('condition')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_condition(new_condition)
        elif condition_type == 'or':
            try:
                condition1 = condition.pop('condition1')
                condition2 = condition.pop('condition2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_condition(condition1)
            ClientThread.check_condition(condition2)
        elif condition_type == 'and':
            try:
                condition1 = condition.pop('condition1')
                condition2 = condition.pop('condition2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_condition(condition1)
            ClientThread.check_condition(condition2)
        elif condition_type == 'xor':
            try:
                condition1 = condition.pop('condition1')
                condition2 = condition.pop('condition2')
            except KeyError:
                raise BadRequest('This Condition is malformed', 404,
                                 {'condition': condition_type})
            ClientThread.check_condition(condition1)
            ClientThread.check_condition(condition2)
        else:
            raise BadRequest('The type of the Condition is unknown',
                             404, {'name': 'if', 'type': condition_type})

    @staticmethod
    def check_operand(operand):
        try:
            operand_type = operand.pop('type')
        except KeyError:
            raise BadRequest('This Operand is malformed (no type)')
        if operand_type == 'database':
            try:
                operand_name = operand.pop('name')
                key = operand.pop('key')
                attribute = operand.pop('attribute')
            except KeyError:
                raise BadRequest('This Operand is malformed', 404,
                                 {'operand': operand_type})
        elif operand_type == 'value':
            if 'value' not in operand:
                raise BadRequest('This Operand is malformed', 404,
                                 {'operand': operand_type})
        elif operand_type == 'statistic':
            try:
                measurement = operand.pop('measurement')
                field = operand.pop('field')
            except KeyError:
                raise BadRequest('This Operand is malformed', 404,
                                 {'operand': operand_type})
        else:
            raise BadRequest('This Operand is malformed', 404,
                             {'operand': operand_type})

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
            scenario_constants[const_name] = {'value': const_value,
                                              'scenario_constant': sa}
        for openbach_function in scenario_json['openbach_functions']:
            openbach_function.pop('wait', None)
            (name, args), = openbach_function.items()
            try:
                of = Openbach_Function.objects.get(pk=name)
            except ObjectDoesNotExist:
                raise BadRequest('This Openbach_Function doesn\'t exist', 400,
                                 {'name': openbach_function['name']})
            if name == 'start_job_instance':
                try:
                    agent_ip = args.pop('agent_ip')
                    offset = args.pop('offset')
                except KeyError:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 400, {'name':
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
                                     ' are malformed', 400, {'name':
                                                             'start_job_instance'})
                try:
                    job = Job.objects.get(name=job_name)
                except ObjectDoesNotExist:
                    raise BadRequest('This Job does not exist', 400, {'name':
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
                                             400, {'job_name': job_name,
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
            elif name == 'if':
                try:
                    openbach_function_true_indexes = args.pop(
                        'openbach_function_true_indexes')
                    openbach_function_false_indexes = args.pop(
                        'openbach_function_false_indexes')
                    condition = args.pop('condition')
                except KeyError:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 400, {'name': 'if'})
                if args:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 400, {'name': 'if'})
                of_argument = of.openbach_function_argument_set.get(
                    name='openbach_functions_true')
                ClientThread.check_type(of_argument,
                                        openbach_function_true_indexes,
                                        scenario_arguments, scenario_constants)
                of_argument = of.openbach_function_argument_set.get(
                    name='openbach_functions_false')
                ClientThread.check_type(of_argument,
                                        openbach_function_false_indexes,
                                        scenario_arguments, scenario_constants)
                ClientThread.check_condition(condition)
            elif name == 'while':
                try:
                    openbach_function_while_indexes = args.pop(
                        'openbach_function_while_indexes')
                    openbach_function_end_indexes = args.pop(
                        'openbach_function_end_indexes')
                    condition = args.pop('condition')
                except KeyError:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 400, {'name': 'while'})
                if args:
                    raise BadRequest('The arguments of this Openbach_Function'
                                     ' are malformed', 400, {'name': 'while'})
                of_argument = of.openbach_function_argument_set.get(
                    name='openbach_functions_while')
                ClientThread.check_type(of_argument,
                                        openbach_function_while_indexes,
                                        scenario_arguments, scenario_constants)
                of_argument = of.openbach_function_argument_set.get(
                    name='openbach_functions_end')
                ClientThread.check_type(of_argument,
                                        openbach_function_end_indexes,
                                        scenario_arguments, scenario_constants)
                ClientThread.check_condition(condition)
            else:
                for of_arg, of_value in args.items():
                    try:
                        of_argument = Openbach_Function_Argument.objects.get(
                            name=of_arg, openbach_function=of)
                    except ObjectDoesNotExist:
                        raise BadRequest('This Openbach_Function doesn\'t have'
                                         ' this argument', 400, {'name': name,
                                                                 'argument':
                                                                 of_arg})
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
                raise BadRequest('At least two constants have the same name',
                                 409, infos={'name': arg['name']})
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
                raise BadRequest('At least two constants have the same name',
                                 409, infos={'name': arg['name']})

        result['scenario_name'] = scenario.name
        return result, 200

    @staticmethod
    def get_default_value(type_):
        if type_ == 'int':
            return 0
        elif type_ == 'bool':
            return True
        elif type_ == 'str':
            return ''
        elif type_ == 'float':
            return 0.0
        elif type_ == 'ip':
            return '127.0.0.1'
        elif type_ == 'list':
            return []
        elif type_ == 'json':
            return {}
        return None

    @staticmethod
    def is_a_leaf(entry):
        if entry['is_waited_for_finished']:
            return False
        if entry['is_waited_for_launched']:
            return False
        if entry['if_true']:
            return False
        if entry['if_false']:
            return False
        if entry['while']:
            return False
        if entry['while_end']:
            return False
        return True

    def check_scenario(self, scenario):
        args = {}
        for scenario_argument in scenario.scenario_argument_set.all():
            try:
                sai = scenario_argument.scenario_argument_instance_set.get(
                    scenario_instance=None)
            except ObjectDoesNotExist:
                pass
            else:
                continue
            args[scenario_argument.name] = self.get_default_value(
                scenario_argument.type)
        scenario_instance = self.register_scenario_instance(scenario, args)
        table = self.build_table(scenario_instance)
        has_changed = True
        while (table != {} and has_changed):
            has_changed = False
            table_tmp = table.copy()
            for ofi_id, entry in table_tmp.items():
                if self.is_a_leaf(entry):
                    for id_ in entry['wait_if_false']:
                        table[id_]['if_false'].remove(ofi_id)
                    for id_ in entry['wait_if_true']:
                        table[id_]['if_true'].remove(ofi_id)
                    for id_ in entry['wait_while']:
                        table[id_]['while'].remove(ofi_id)
                    for id_ in entry['wait_while_end']:
                        table[id_]['while_end'].remove(ofi_id)
                    for id_ in entry['wait_for_launched']:
                        table[id_]['is_waited_for_launched'].remove(ofi_id)
                    for id_ in entry['wait_for_finished']:
                        table[id_]['is_waited_for_finished'].remove(ofi_id)
                    del table[ofi_id]
                    has_changed = True

        scenario_instance.delete()

        if table != {}:
            raise BadRequest('Your Scenario is malformed: the tree is wrong')

    def create_scenario_action(self, scenario_json, project_name=None):
        result = self.create_scenario(scenario_json, project_name)
        return result

    def create_scenario(self, scenario_json, project_name=None):
        if not self.first_check_on_scenario(scenario_json):
            raise BadRequest('Your Scenario is malformed: the json is malformed')
        name = scenario_json['name']

        if project_name:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None

        result = self.register_scenario(scenario_json, name, project)
        scenario = Scenario.objects.get(name=name, project=project)
        try:
            self.check_scenario(scenario)
        except BadRequest:
            scenario.delete()
            raise

        return result

    def del_scenario_action(self, scenario_name, project_name=None):
        return self.del_scenario(scenario_name, project_name)

    def del_scenario(self, scenario_name, project_name=None):
        if project_name is not None:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None
        try:
            scenario = Scenario.objects.get(name=scenario_name, project=project)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name,
                                    'project_name': project_name})

        scenario.delete()

        return None, 204

    def modify_scenario_action(self, scenario_json, scenario_name,
                               project_name=None):
        return self.modify_scenario(scenario_json, scenario_name, project_name)

    def modify_scenario(self, scenario_json, scenario_name, project_name=None):
        if not self.first_check_on_scenario(scenario_json):
            raise BadRequest('Your Scenario is malformed')
        name = scenario_json['name']
        if name != scenario_name:
            raise BadRequest('The name in the Scenario \'{}\' doesn\'t '
                             'correspond with the name of the route '
                             '\'{}\''.format(name, scenario_name))
        if project_name:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None

        with transaction.atomic():
            try:
                scenario = Scenario.objects.get(name=scenario_name,
                                                project=project)
            except ObjectDoesNotExist:
                raise BadRequest('This Scenario does not exist', 404)
            scenario.delete()
            self.register_scenario(scenario_json, name, project)
            scenario = Scenario.objects.get(name=scenario_name, project=project)
            self.check_scenario(scenario)

        return None, 204

    def get_scenario_action(self, scenario_name, project_name=None):
        return self.get_scenario(scenario_name, project_name)

    def get_scenario(self, scenario_name, project_name=None):
        if project_name:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None
        try:
            scenario = Scenario.objects.get(name=scenario_name, project=project)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name,
                                    'project_name': project_name})

        return scenario.get_json(), 200

    def list_scenarios_action(self, project_name=None):
        return self.list_scenarios(project_name)

    def list_scenarios(self, project_name=None):
        if project_name:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
            scenarios = Scenario.objects.filter(project=project)
        else:
            scenarios = Scenario.objects.all()
        response = []
        for scenario in scenarios:
            response.append(scenario.get_json())

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
        if isinstance(arg_value, list):
            value = []
            for v in arg_value:
                value.append(ClientThread.get_value(v, scenario_instance))
        else:
            value = ClientThread.get_value(arg_value, scenario_instance)
        try:
            ofai.check_and_set_value(value)
        except ValueError as e:
            raise BadRequest(e.args[0], 400)
        ofai.save()

    @staticmethod
    def get_value(value, scenario_instance):
        is_reference, value = ClientThread.check_reference(value)
        if is_reference:
            sa = scenario_instance.scenario.scenario_argument_set.get(
                name=value)
            try:
                spi = scenario_instance.scenario_argument_instance_set.get(
                    argument=sa)
            except ObjectDoesNotExist:
                spi = scenario_instance.scenario.scenario_argument_set.get(
                    name=value).scenario_argument_instance_set.get(
                        scenario_instance=None)
            value = spi.value
        return value

    @staticmethod
    def register_operand(operand_json, scenario_instance):
        operand_type = operand_json.pop('type')
        if operand_type == 'database':
            name = operand_json.pop('name')
            key = operand_json.pop('key')
            attribute = operand_json.pop('attribute')
            key = ClientThread.get_value(key, scenario_instance)
            operand = Operand_Database(name=name, key=key, attribute=attribute)
        elif operand_type == 'value':
            value = operand_json.pop('value')
            value = ClientThread.get_value(value, scenario_instance)
            operand = Operand_Value(value=value)
        elif operand_type == 'statistic':
            measurement = operand_json.pop('measurement')
            field = operand_json.pop('field')
            measurement = ClientThread.get_value(measurement, scenario_instance)
            field = ClientThread.get_value(field, scenario_instance)
            operand = Operand_Statistic(measurement=measurement, field=field)

        operand.save()
        return operand

    @staticmethod
    def register_condition(condition_json, scenario_instance):
        condition_type = condition_json.pop('type')
        if condition_type == 'not':
            new_condition_json = condition_json.pop('condition')
            new_condition = ClientThread.register_condition(new_condition_json,
                                                            scenario_instance)
            condition = Condition_Not(condition=condition)
        elif condition_type == 'or':
            condition1_json = condition_json.pop('condition1')
            condition1 = ClientThread.register_condition(condition1_json,
                                            scenario_instance)
            condition2_json = condition_json.pop('condition2')
            condition2 = ClientThread.register_condition(condition2_json,
                                            scenario_instance)
            condition = Condition_Or(condition1=condition1,
                                     condition2=condition2)
        elif condition_type == 'and':
            condition1_json = condition_json.pop('condition1')
            condition1 = ClientThread.register_condition(condition1_json,
                                            scenario_instance)
            condition2_json = condition_json.pop('condition2')
            condition2 = ClientThread.register_condition(condition2_json,
                                            scenario_instance)
            condition = Condition_And(condition1=condition1,
                                     condition2=condition2)
        elif condition_type == 'xor':
            condition1_json = condition_json.pop('condition1')
            condition1 = ClientThread.register_condition(condition1_json,
                                            scenario_instance)
            condition2_json = condition_json.pop('condition2')
            condition2 = ClientThread.register_condition(condition2_json,
                                            scenario_instance)
            condition = Condition_Xor(condition1=condition1,
                                     condition2=condition2)
        elif condition_type == '=':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Equal(operand1=operand1, operand2=operand2)
        elif condition_type == '!=':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Unequal(operand1=operand1, operand2=operand2)
        elif condition_type == '<=':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Below_Or_Equal(operand1=operand1,
                                                 operand2=operand2)
        elif condition_type == '<':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Below(operand1=operand1, operand2=operand2)
        elif condition_type == '>=':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Upper_Or_Equal(operand1=operand1,
                                                 operand2=operand2)
        elif condition_type == '>':
            operand1_json = condition_json.pop('operand1')
            operand1 = ClientThread.register_operand(operand1_json,
                                        scenario_instance)
            operand2_json = condition_json.pop('operand2')
            operand2 = ClientThread.register_operand(operand2_json,
                                        scenario_instance)
            condition = Condition_Upper(operand1=operand1, operand2=operand2)

        condition.save()
        return condition

    @staticmethod
    def register_openbach_function_instances(scenario_instance):
        scenario_json = json.loads(scenario_instance.scenario.scenario)
        openbach_function_id = 1
        for openbach_function in scenario_json['openbach_functions']:
            wait = openbach_function.pop('wait', None)
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
                            value = ClientThread.get_value(v, scenario_instance)
                            instance_args[job_arg].append(value)
                    else:
                        value = ClientThread.get_value(job_value,
                                                       scenario_instance)
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
            elif name == 'if':
                openbach_function_true_indexes = args.pop(
                    'openbach_function_true_indexes')
                ClientThread.register_openbach_function_argument_instance(
                    'openbach_functions_true',
                    openbach_function_true_indexes, ofi, scenario_instance)
                openbach_function_false_indexes = args.pop(
                    'openbach_function_false_indexes')
                ClientThread.register_openbach_function_argument_instance(
                    'openbach_functions_false',
                    openbach_function_false_indexes, ofi, scenario_instance)
                condition_json = args.pop('condition')
                condition = ClientThread.register_condition(condition_json,
                                                            scenario_instance)
                ofi.condition = condition
            elif name == 'while':
                openbach_function_while_indexes = args.pop(
                    'openbach_function_while_indexes')
                ClientThread.register_openbach_function_argument_instance(
                    'openbach_functions_while',
                    openbach_function_while_indexes, ofi, scenario_instance)
                openbach_function_end_indexes = args.pop(
                    'openbach_function_end_indexes')
                ClientThread.register_openbach_function_argument_instance(
                    'openbach_functions_end',
                    openbach_function_end_indexes, ofi, scenario_instance)
                condition_json = args.pop('condition')
                condition = ClientThread.register_condition(condition_json,
                                                            scenario_instance)
                ofi.condition = condition
            else:
                for arg_name, arg_value in args.items():
                    ClientThread.register_openbach_function_argument_instance(
                        arg_name, arg_value, ofi, scenario_instance)
            if wait is not None:
                ofi.time = wait['time']
                ofi.save()
                for index in wait['launched_indexes']:
                    wfl = Wait_For_Launched(openbach_function_instance=ofi,
                                            openbach_function_instance_id_waited=index)
                    wfl.save()
                for index in wait['finished_indexes']:
                    wff = Wait_For_Finished(openbach_function_instance=ofi,
                                            job_instance_id_waited=index)
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
                scenario_argument.scenario_argument_instance_set.get(
                    scenario_instance=None)
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
    def build_entry(programmable=True):
        return {'wait_for_launched': set(),
                'is_waited_for_launched': set(),
                'wait_for_finished': set(),
                'is_waited_for_finished': set(),
                'if_true': set(),
                'wait_if_true': set(),
                'if_false': set(),
                'wait_if_false': set(),
                'while': set(),
                'wait_while': set(),
                'while_end': set(),
                'wait_while_end': set(),
                'programmable': programmable}

    @staticmethod
    def build_table(scenario_instance):
        table = {}
        for ofi in scenario_instance.openbach_function_instance_set.all():
            ofi_id = ofi.openbach_function_instance_id
            if ofi_id not in table:
                table[ofi_id] = ClientThread.build_entry()
            if ofi.openbach_function.name == 'if':
                of = ofi.openbach_function
                ofa = of.openbach_function_argument_set.get(
                    name='openbach_functions_true')
                ofai = ofi.openbach_function_argument_instance_set.get(
                    argument=ofa)
                for id_ in shlex.split(ofai.value):
                    id_ = int(id_)
                    if id_ not in table:
                        table[id_] = ClientThread.build_entry(False)
                    else:
                        table[id_]['programmable'] = False
                    table[id_]['wait_if_true'].add(ofi_id)
                    table[ofi_id]['if_true'].add(id_)
                ofa = of.openbach_function_argument_set.get(
                    name='openbach_functions_false')
                ofai = ofi.openbach_function_argument_instance_set.get(
                    argument=ofa)
                for id_ in shlex.split(ofai.value):
                    id_ = int(id_)
                    if id_ not in table:
                        table[id_] = ClientThread.build_entry(False)
                    else:
                        table[id_]['programmable'] = False
                    table[id_]['wait_if_false'].add(ofi_id)
                    table[ofi_id]['if_false'].add(id_)
            elif ofi.openbach_function.name == 'while':
                of = ofi.openbach_function
                ofa = of.openbach_function_argument_set.get(
                    name='openbach_functions_while')
                ofai = ofi.openbach_function_argument_instance_set.get(
                    argument=ofa)
                for id_ in shlex.split(ofai.value):
                    id_ = int(id_)
                    if id_ not in table:
                        table[id_] = ClientThread.build_entry(False)
                    else:
                        table[id_]['programmable'] = False
                    table[id_]['wait_while'].add(ofi_id)
                    table[ofi_id]['while'].add(id_)
                ofa = of.openbach_function_argument_set.get(
                    name='openbach_functions_end')
                ofai = ofi.openbach_function_argument_instance_set.get(
                    argument=ofa)
                for id_ in shlex.split(ofai.value):
                    id_ = int(id_)
                    if id_ not in table:
                        table[id_] = ClientThread.build_entry(False)
                    else:
                        table[id_]['programmable'] = False
                    table[id_]['wait_while_end'].add(ofi_id)
                    table[ofi_id]['while_end'].add(id_)
            for wfl in ofi.wait_for_launched_set.all():
                ofi_waited_id = wfl.openbach_function_instance_id_waited
                if ofi_waited_id not in table:
                    table[ofi_waited_id] = ClientThread.build_entry()
                table[ofi_id]['wait_for_launched'].add(ofi_waited_id)
                table[ofi_waited_id]['is_waited_for_launched'].add(ofi_id)
            for wff in ofi.wait_for_finished_set.all():
                ji_waited_id = wff.job_instance_id_waited
                if ji_waited_id not in table:
                    table[ji_waited_id] = ClientThread.build_entry()
                table[ofi_id]['wait_for_finished'].add(ji_waited_id)
                table[ji_waited_id]['is_waited_for_finished'].add(ofi_id)
        has_changed = True
        while has_changed:
            has_changed = False
            for ofi_id, entry in table.items():
                list_id = set()
                list_id.update(entry['is_waited_for_launched'])
                list_id.update(entry['is_waited_for_finished'])
                list_id.update(entry['if_true'])
                list_id.update(entry['if_false'])
                list_id.update(entry['while'])
                list_id.update(entry['while_end'])
                if entry['wait_if_true']:
                    for id_ in list_id:
                        for waited_id in entry['wait_if_true']:
                            if id_ not in table[waited_id]['if_true']:
                                table[waited_id]['if_true'].add(id_)
                                table[id_]['wait_if_true'].add(waited_id)
                                has_changed = True
                            table[id_]['programmable'] = False
                if entry['wait_if_false']:
                    for id_ in list_id:
                        for waited_id in entry['wait_if_false']:
                            if id_ not in table[waited_id]['if_false']:
                                table[waited_id]['if_false'].add(id_)
                                table[id_]['wait_if_false'].add(waited_id)
                                has_changed = True
                            table[id_]['programmable'] = False
                if entry['wait_while']:
                    for id_ in list_id:
                        for waited_id in entry['wait_while']:
                            if id_ not in table[waited_id]['while']:
                                table[waited_id]['while'].add(id_)
                                table[id_]['wait_while'].add(waited_id)
                                has_changed = True
                            table[id_]['programmable'] = False
        return table

    def launch_openbach_function_instance(self, scenario_instance, ofi_id,
                                          table, queues):
        entry = table[ofi_id]
        queue = queues[ofi_id]
        launch_queues = [ queues[id] for id in entry['is_waited_for_launched'] ]
        finished_queues = tuple([ queues[id] for id in
                                 entry['is_waited_for_finished'] ])
        waited_ids = entry['wait_for_launched'].union(
            entry['wait_for_finished'])
        ofi = scenario_instance.openbach_function_instance_set.get(
            openbach_function_instance_id=ofi_id)
        ofi.status = 'Waiting ...'
        ofi.status_date = timezone.now()
        ofi.save()
        t = threading.currentThread()
        while waited_ids:
            try:
                x = queue.get(timeout=0.5)
            except Empty:
                if not t.do_run:
                    ofi.status = 'Stopped'
                    ofi.status_date = timezone.now()
                    ofi.save()
                    return
            else:
                waited_ids.remove(x)
        time.sleep(ofi.time)
        ofi.status = 'Starting ...'
        ofi.status_date = timezone.now()
        ofi.save()
        try:
            name = ofi.openbach_function.name
            name = '{}_of'.format(name)
            function = getattr(self, name)
        except AttributeError:
            self.stop_scenario_instance_of(scenario_instance.id,
                                           state='Scheduling Error')
        arguments = {}
        for arg in ofi.openbach_function_argument_instance_set.all():
            if arg.argument.type == 'json':
                arguments[arg.argument.name] = json.loads(arg.value)
            elif arg.argument.type == 'list':
                arguments[arg.argument.name] = []
                for value in shlex.split(arg.value):
                    arguments[arg.argument.name].append(value)
            else:
                arguments[arg.argument.name] = arg.value
        if ofi.openbach_function.name == 'start_job_instance':
            arguments['scenario_instance_id'] = scenario_instance.id
            arguments['ofi'] = ofi
            arguments['finished_queues'] = finished_queues
        elif ofi.openbach_function.name == 'stop_job_instance':
            arguments['scenario_instance'] = scenario_instance
        elif (ofi.openbach_function.name == 'if' or ofi.openbach_function.name
              == 'while'):
            arguments['condition'] = ofi.condition
            arguments['scenario_instance'] = scenario_instance
            arguments['table'] = table
            arguments['queues'] = queues
            arguments['openbach_function_instance_id'] = ofi_id
        elif ofi.openbach_function.name == 'start_scenario_instance':
            arguments['ofi'] = ofi
        if ofi.openbach_function.name == 'if':
            del arguments['openbach_functions_true']
            del arguments['openbach_functions_false']
            arguments['openbach_functions_true'] = table[ofi_id]['if_true']
            arguments['openbach_functions_false'] = table[ofi_id]['if_false']
        if ofi.openbach_function.name == 'while':
            del arguments['openbach_functions_while']
            arguments['openbach_functions_while'] = table[ofi_id]['while']
        try:
            threads = function(**arguments)
        except BadRequest:
            self.stop_scenario_instance_of(scenario_instance.id,
                                           state='Scheduling Error')
        if not t.do_run:
            ofi.status = 'Stopped'
            ofi.status_date = timezone.now()
            ofi.save()
            return
        ofi.status = 'Finished, warning other openbach_functions ...'
        ofi.status_date = timezone.now()
        ofi.save()
        for queue in launch_queues:
            queue.put(ofi_id)
        ofi.status = 'Finished'
        ofi.status_date = timezone.now()
        ofi.save()
        for thread in threads:
            thread.join()

    @staticmethod
    def wait_threads_to_finish(scenario_instance_id, threads):
        for thread in threads:
            thread.join()
        # TODO trouver un meilleur status
        finished = True
        scenario_instance = Scenario_Instance.objects.get(
            pk=scenario_instance_id)
        for job_instance in scenario_instance.job_instance_set.all():
            if not job_instance.is_stopped:
                finished = False
                break
        if finished:
            scenario_instance.status = "Finished"
            scenario_instance.status_date = timezone.now()
            scenario_instance.is_stopped = True
            scenario_instance.save()
        else:
            scenario_instance.status = "All Openbach Functions launched"
            scenario_instance.status_date = timezone.now()
            scenario_instance.save()

    def start_scenario_instance_of(self, scenario_name, arguments, ofi,
                                   date=None):
        project_name = ofi.scenario_instance.scenario.project.name
        result, _ = self.start_scenario_instance(scenario_name, arguments, date,
                                                 project_name)

        scenario_instance_id = result['scenario_instance_id']
        scenario_instance = Scenario_Instance.objects.get(
            pk=scenario_instance_id)
        scenario_instance.openbach_function_instance_master = ofi
        scenario_instance.save()
        with ThreadManager() as threads:
            return [threads[scenario_instance.id][0]]

    def start_scenario_instance_action(self, scenario_name, arguments,
                                       date=None, project_name=None):
        return self.start_scenario_instance(scenario_name, arguments, date,
                                            project_name)

    def start_scenario_instance(self, scenario_name, arguments, date=None,
                                project_name=None):
        if project_name:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None
        try:
            scenario = Scenario.objects.get(name=scenario_name, project=project)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario is not in the database', 404,
                             infos={'scenario_name': scenario_name,
                                    'project_name': project_name})
        scenario_instance = self.register_scenario_instance(scenario, arguments)
        table = self.build_table(scenario_instance)
        # lance les openbach function possible
        queues = {id: Queue() for id in table}
        thread_list = []
        for ofi_id, entry in table.items():
            if entry['programmable']:
                thread = threading.Thread(
                    target=self.launch_openbach_function_instance,
                    args=(scenario_instance, ofi_id, table, queues))
                thread.do_run = True
                thread.start()
                thread_list.append(thread)
                with ThreadManager() as threads:
                    if scenario_instance.id not in threads:
                        threads[scenario_instance.id] = {}
                    threads[scenario_instance.id][ofi_id] = thread
        thread = threading.Thread(
            target=self.wait_threads_to_finish,
            args=(scenario_instance.id, thread_list))
        thread.do_run = True
        thread.start()
        with ThreadManager() as threads:
            if scenario_instance.id not in threads:
                threads[scenario_instance.id] = {}
            threads[scenario_instance.id][0] = thread

        return {'scenario_instance_id': scenario_instance.id}, 200

    def stop_scenario_instance_of(self, scenario_instance_id, state='Stopped',
                                  date=None, scenario_name=None,
                                  project_name=None):
        self.stop_scenario_instance(scenario_instance_id, date, scenario_name,
                                    project_name)
        scenario_instance = Scenario_Instance.objects.get(
            pk=scenario_instance_id)
        scenario_instance.status = state
        scenario_instance.save()

    def stop_scenario_instance_action(self, scenario_instance_id, date=None,
                                      scenario_name=None, project_name=None):
        return self.stop_scenario_instance(scenario_instance_id, date,
                                           scenario_name, project_name)

    def stop_scenario_instance(self, scenario_instance_id, date=None,
                               scenario_name=None, project_name=None):
        if project_name is not None:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None
        if scenario_name is not None:
            try:
                scenario = Scenario.objects.get(name=scenario_name,
                                                project=project)
            except ObjectDoesNotExist:
                raise BadRequest('This Scenario is not in the database', 404,
                                 infos={'scenario_name': scenario_name,
                                        'project_name': project_name})
        else:
            scenario = None
        scenario_instance_id = int(scenario_instance_id)
        try:
            scenario_instance = Scenario_Instance.objects.get(
                pk=scenario_instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario_Instance does not exist in the '
                             'database', 404, {'scenario_instance_id':
                                               scenario_instance_id})
        if scenario is not None:
            if scenario_instance.scenario.scenario == scenario:
                raise BadRequest('This Scenario_Instance does not match the'
                                 ' specified Scenario', 400,
                                 {'scenario_instance_id': scenario_instance_id,
                                  'scenario_name': scenario_name})
        if scenario_instance.is_stopped:
            return None, 204
        scenario_instance.status = "Stopped"
        with ThreadManager() as threads:
            try:
                scenario_threads = threads[scenario_instance_id]
            except KeyError:
                scenario_instance.status = "Stopped, out of controll"
            else:
                for ofi_id, thread in scenario_threads.items():
                    if not ofi_id:
                        continue
                    thread.do_run = False
        for ofi in scenario_instance.openbach_function_instance_set.all():
            for job_instance in ofi.job_instance_set.all():
                try:
                    result, returncode = self.stop_job_instance_action(
                        [job_instance.id])
                    result, returncode = self.watch_job_instance_action(
                        job_instance.id, stop='now')
                except BadRequest:
                    scenario_instance.status = "Running, out of controll"
        scenario_instance.status_date = timezone.now()
        scenario_instance.is_stopped = True
        scenario_instance.save()

        return None, 204

    def infos_openbach_function_instance(self, openbach_function_instance):
        infos = {}
        infos['name'] = openbach_function_instance.openbach_function.name
        if (openbach_function_instance.openbach_function.name ==
            'start_scenario_instance'):
            try:
                scenario_instance = openbach_function_instance.openbach_function_instance_master.all()[0]
            except IndexError:
                raise BadRequest('Integrity of the Openbach_Function_Instance '
                                 'lost')
            info = self.infos_scenario_instance(scenario_instance)
            infos.update(info)
            return infos
        infos['status'] = openbach_function_instance.status
        infos['status_date'] = openbach_function_instance.status_date
        if infos['name'] == 'start_job_instance':
            try:
                job_instance = openbach_function_instance.job_instance_set.all()[0]
            except IndexError:
                raise BadRequest('Integrity of the Openbach_Function_Instance '
                                 'lost')
            if job_instance:
                info, _ = self.status_job_instance_action(job_instance.id)
                infos[job_instance.job.__str__()] = info
        infos['arguments'] = []
        for ofai in openbach_function_instance.openbach_function_argument_instance_set.all():
            info = {'name': ofai.argument.name, 'type': ofai.argument.type,
                    'value': ofai.value}
            infos['arguments'].append(info)
        infos['wait'] = {'time': openbach_function_instance.time,
                         'launched_indexes': [], 'finished_indexes': []}
        for wfl in openbach_function_instance.wait_for_launched_set.all():
            infos['wait']['launched_indexes'].append(
                wfl.openbach_function_instance_id_waited)
        for wff in openbach_function_instance.wait_for_finished_set.all():
            infos['wait']['finished_indexes'].append(
                wff.job_instance_id_waited)
        return infos

    def infos_scenario_instance(self, scenario_instance):
        infos = {}
        infos['scenario_instance_id'] = scenario_instance.id
        infos['status'] = scenario_instance.status
        infos['status_date'] = scenario_instance.status_date
        infos['arguments'] = []
        for argument in scenario_instance.scenario_argument_instance_set.all():
            info = {'name': argument.argument.name, 'type':
                    argument.argument.type, 'value': argument.value}
            infos['arguments'].append(info)
        infos['openbach_functions'] = []
        for ofi in scenario_instance.openbach_function_instance_set.all():
            try:
                info = self.infos_openbach_function_instance(ofi)
            except BadRequest as e:
                info = {'name': ofi.openbach_function.name, 'error': e.reason}
            infos['openbach_functions'].append(info)
        return infos

    def list_scenario_instances_action(self, scenario_name=None,
                                       project_name=None):
        return self.list_scenario_instances(scenario_name, project_name)

    def list_scenario_instances(self, scenario_name=None, project_name=None):
        if project_name is not None:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
            scenarios = Scenario.objects.filter(project=project)
        else:
            scenarios = Scenario.objects.all()
        if scenario_name is not None:
            scenarios = scenarios.filter(name=scenario_name)

        result = {}
        for scenario in scenarios:
            project_name = getattr(scenario.project, 'name', '')
            scenario_instances = [
                self.infos_scenario_instance(scenario_instance)
                for scenario_instance in scenario.scenario_instance_set.all()
            ]
            if scenario_instances:
                result.setdefault(project_name, {})[scenario.name] = scenario_instances

        return result, 200

    def status_scenario_instance_action(self, scenario_instance_id,
                                        project_name=None):
        return self.status_scenario_instance(scenario_instance_id, project_name)

    def status_scenario_instance(self, scenario_instance_id, scenario_name=None,
                                 project_name=None):
        if project_name is not None:
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404,
                                 {'project_name': project_name})
        else:
            project = None
        if scenario_name is not None:
            try:
                scenario = Scenario.objects.get(name=scenario_name,
                                                project=project)
            except ObjectDoesNotExist:
                raise BadRequest('This Scenario is not in the database', 404,
                                 infos={'scenario_name': scenario_name,
                                        'project_name': project_name})
        else:
            scenario = None
        try:
            scenario_instance = Scenario_Instance.objects.get(
                pk=scenario_instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('This Scenario_Instance does not exist in the '
                             'database', 404, {'scenario_instance_id':
                                               scenario_instance_id})
        if project is not None:
            if scenario_instance.scenario.project != project:
                raise BadRequest('This Scenario_Instance does not match the'
                                 ' specified Scenario', 400,
                                 {'scenario_instance_id': scenario_instance_id,
                                 'scenario_name': scenario_name})
        result = self.infos_scenario_instance(scenario_instance)
        result['scenario_name'] = scenario_instance.scenario.name

        return result, 200

    def kill_all_action(self, date=None):
        return self.kill_all(date)

    def kill_all(self, date=None):
        for scenario_instance in Scenario_Instance.objects.all():
            if not scenario_instance.is_stopped:
                self.stop_scenario_instance_action(scenario_instance.id)
        job_instance_ids = []
        for job_instance in Job_Instance.objects.all():
            if not job_instance.is_stopped:
                job_instance_ids.append(job_instance.id)
        result, returncode = self.stop_job_instance_action(job_instance_ids)
        for watch in Watch.objects.all():
            try:
                result, returncode = self.watch_job_instance_action(
                    watch.job_instance.id, stop='now')
            except BadRequest:
                #TODO mieux gerer les erreurs !
                pass

        return None, 204

    @staticmethod
    def first_check_on_project(project_json):
        required_parameters = ('name', 'description', 'entity', 'network',
                               'scenario')
        try:
            for k in required_parameters:
                project_json[k]
        except KeyError:
            return False
        if not isinstance(project_json['name'], str):
            return False
        if not isinstance(project_json['description'], str):
            return False
        if not isinstance(project_json['entity'], list):
            return False
        if not isinstance(project_json['network'], list):
            return False
        if not isinstance(project_json['scenario'], list):
            return False
        return True

    @staticmethod
    def first_check_on_entity(entity_json):
        required_parameters = ('name', 'description', 'agent', 'networks')
        try:
            for k in required_parameters:
                entity_json[k]
        except KeyError:
            return False
        if not isinstance(entity_json['name'], str):
            return False
        if not isinstance(entity_json['description'], str):
            return False
        if entity_json['agent'] != None:
            if not isinstance(entity_json['agent'], dict):
                return False
            required_parameters = ('address', 'name', 'username', 'collector')
            try:
                for k in required_parameters:
                    entity_json['agent'][k]
            except KeyError:
                return False
            if not isinstance(entity_json['agent']['address'], str):
                return False
            if not isinstance(entity_json['agent']['name'], str):
                return False
            if not isinstance(entity_json['agent']['username'], str):
                return False
            if not isinstance(entity_json['agent']['collector'], str):
                return False
        return ClientThread.first_check_on_network(entity_json['networks'])

    @staticmethod
    def first_check_on_network(network_json):
        if not isinstance(network_json, list):
            return False
        for network in network_json:
            if not isinstance(network, str):
                return False
        return True

    @staticmethod
    def register_entity(entity_json, project_name):
        try:
            project = Project.objects.get(pk=project_name)
        except ObjectDoeNotExist:
            raise BadRequest('This Project is not on the database', 404)
        entity = Entity(
            name=entity_json['name'],
            project=project,
            description=entity_json['description']
        )
        if entity_json['agent'] != None:
            try:
                agent = Agent.objects.get(pk=entity_json['agent']['address'])
            except ObjectDoesNotExist:
                raise BadRequest('This Agent \'{}\' is not in the database'.format(
                    entity_json['agent']['address']), 404)
            entity.agent = agent
        try:
            entity.save()
        except IntegrityError:
            raise BadRequest('A Entity with this name already exists')
        for network_name in entity_json['networks']:
            try:
                network = Network.objects.get(name=network_name,
                                              project=project)
            except ObjectDoesNotExist:
                raise BadRequest('This network \'{}\' does not exist in the'
                                 ' database'.format(network), 404)
            entity.networks.add(network)

    @staticmethod
    def register_network(network_json, project_name):
        try:
            project = Project.objects.get(pk=project_name)
        except ObjectDoeNotExist:
            raise BadRequest('This Project is not on the database', 404)
        try:
            Network(name=network_json, project=project).save()
        except IntegrityError:
            raise BadRequest('This name of Network is already used')

    def register_project(self, project_json):
        name = project_json['name']
        project = Project(name=name,
                          description=project_json['description'])
        try:
            project.save(force_insert=True)
        except IntegrityError:
            raise BadRequest('This name of Project \'{}\' is already'
                             ' used'.format(name), 409)
        networks = project_json['network']
        if not self.first_check_on_network(networks):
            project.delete()
            raise BadRequest('Your Project is malformed: the json is'
                             ' malformed')
        for network in networks:
            try:
                self.register_network(network, name)
            except BadRequest:
                project.delete()
                raise
        entities = project_json['entity']
        for entity in entities:
            if not self.first_check_on_entity(entity):
                project.delete()
                raise BadRequest('Your Project is malformed: the json is'
                                 ' malformed')
            try:
                self.register_entity(entity, name)
            except BadRequest:
                project.delete()
                raise
        scenarios = project_json['scenario']
        for scenario in scenarios:
            try:
                self.create_scenario(scenario, name)
            except BadRequest:
                project.delete()
                raise

    def add_project_action(self, project_json):
        return self.add_project(project_json)

    def add_project(self, project_json):
        if not self.first_check_on_project(project_json):
            raise BadRequest('Your Project is malformed: the json is malformed')
        self.register_project(project_json)
        return None, 204

    def modify_project_action(self, project_name, project_json):
        return self.modify_project(project_name, project_json)

    def modify_project(self, project_name, project_json):
        if not self.first_check_on_project(project_json):
            raise BadRequest('Your Project is malformed: the json is malformed')
        if project_name != project_json['name']:
            raise BadRequest('Your Project is malformed: the name given does '
                             'not correpond to the name in the json')
        with transaction.atomic():
            try:
                project = Project.objects.get(name=project_name)
            except ObjectDoesNotExist:
                raise BadRequest('This Project does not exist', 404)
            project.delete()
            self.register_project(project_json)
        return None, 204

    def del_project_action(self, project_name):
        return self.del_project(project_name)

    def del_project(self, project_name):
        try:
            project = Project.objects.get(pk=project_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Project \'{}\' does not exist in the'
                             ' database'.format(project_name), 404)
        project.delete()
        return None, 204

    def get_project_action(self, project_name):
        return self.get_project(project_name)

    def get_project(self, project_name):
        try:
            project = Project.objects.get(pk=project_name)
        except ObjectDoesNotExist:
            raise BadRequest('This Project \'{}\' does not exist in the'
                             ' database'.format(project_name), 404)
        return project.get_json(), 200

    def list_projects_action(self):
        return self.list_projects()

    def list_projects(self):
        result = []
        for project in Project.objects.all():
            result.append(project.get_json())
        return result, 200

    def state_collector_action(self, address):
        try:
            command_result = Collector_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            raise BadRequest('Action never asked', 404)
        except DataError:
            raise BadRequest('You must give an ip address for the Collector')
        return command_result.get_json(), 200

    def state_agent_action(self, address):
        try:
            command_result = Agent_Command_Result.objects.get(pk=address)
        except ObjectDoesNotExist:
            raise BadRequest('Action never asked', 404)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        return command_result.get_json(), 200

    def state_job_action(self, address, job_name):
        try:
            command_result = Installed_Job_Command_Result.objects.get(
                agent_ip=address, job_name=job_name)
        except ObjectDoesNotExist:
            raise BadRequest('Action never asked', 404)
        except DataError:
            raise BadRequest('You must give an ip address for the Agent')
        return command_result.get_json(), 200

    def state_push_file_action(self, filename, remote_path, address):
        try:
            command_result = File_Command_Result.objects.get(
                filename=filename, remote_path=remote_path, address=address)
        except ObjectDoesNotExist:
            raise BadRequest('Action never asked', 404)
        return command_result.get_json(), 200

    def state_job_instance_action(self, job_instance_id):
        try:
            command_result = Job_Instance_Command_Result.objects.get(
                job_instance_id=job_instance_id)
        except ObjectDoesNotExist:
            raise BadRequest('Action never asked', 404)
        return command_result.get_json(), 200

    def run(self):
        request, fifoname = recv_fifo(self.clientsocket)
        try:
            response, returncode = self.execute_request(request)
        except BadRequest as e:
            result = {'response': {'error': e.reason}, 'returncode':
                      e.returncode}
            if e.infos:
                result['response'].update(e.infos)
        except UnicodeError:
            result = {'response': {'error': 'KO Undecypherable request'},
                      'returncode': 400}
        else:
            result = {'response': response, 'returncode': returncode}
        finally:
            msg = json.dumps(result, cls=DjangoJSONEncoder)
            send_all(fifoname, msg)
            self.clientsocket.close()


def listen_message_from_backend(tcp_socket):
    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()


def handle_message_from_status_manager(clientsocket):
    playbook_builder = PlaybookBuilder('/tmp/')
    request = clientsocket.recv(4096)
    clientsocket.close()
    message = json.loads(request.decode())
    type_ = message['type']
    scenario_instance_id = message['scenario_instance_id']
    job_instance_id = message['job_instance_id']
    if type_ == 'Finished':
        with WaitingQueueManager() as waiting_queues:
            si_id, ofi_id, finished_queues = waiting_queues.pop(job_instance_id)
        for queue in finished_queues:
            queue.put(ofi_id)
        scenario_instance = Scenario_Instance.objects.get(pk=si_id)
        if scenario_instance.job_instance_set.all().count() == 0:
            with ThreadManager() as threads:
                if 0 in threads[scenario_instance.id]:
                    thread = threads[scenario_instance.id][0]
                    if not thread.isActive():
                        scenario_instance.status = "Finished"
                        scenario_instance.status_date = timezone.now()
                        scenario_instance.is_stopped = True
                        scenario_instance.save()
    elif type_ == 'Error':
        # TODO Stop the scenario
        pass
    if type_ in ('Finished', 'Error'):
        watch = Watch.objects.get(pk=job_instance_id)
        job = watch.job.job
        agent = watch.job.agent
        host_filename = playbook_builder.write_hosts(
            agent.address, 'handle_message_from_status_manager')
        with playbook_builder.playbook_file() as playbook, playbook_builder.extra_vars_file() as extra_vars:
            playbook_builder.build_status(
                    job.name, job_instance_id,
                    None, None, 'now',
                    playbook, extra_vars)
        try:
            playbook_builder.launch_playbook(
                'ansible-playbook -i {} -e @{} -e '
                'ansible_ssh_user="{agent.username}" -e '
                'ansible_sudo_pass="{agent.password}" -e '
                'ansible_ssh_pass="{agent.password}" {}'
                .format(host_filename, extra_vars.name, playbook.name,
                        agent=agent))
        except BadRequest:
            # TODO see how to handle this
            pass
        watch.delete()


def listen_message_from_status_manager(tcp_socket):
    while True:
        client_socket, _ = tcp_socket.accept()
        threading.Thread(target=handle_message_from_status_manager,
                         args=(client_socket,)).start()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_term_handler)

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

    # Initialiser le ThreadManager
    ThreadManager(init=True)

    thread1 = threading.Thread(target=listen_message_from_backend,
                               args=(tcp_socket1,))
    thread1.start()
    thread2 = threading.Thread(target=listen_message_from_status_manager,
                               args=(tcp_socket2,))
    thread2.start()

