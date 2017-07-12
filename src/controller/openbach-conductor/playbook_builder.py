#!/usr/bin/env python3

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Utilities around Ansible invocation to help and
simplify playbooks building and launching.
"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import tempfile

from ansible import constants as C
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.inventory import Inventory
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.callback.default import CallbackModule
from ansible.utils.vars import load_options_vars
from ansible.vars import VariableManager

import errors


class PlayResult(CallbackModule):
    """Utility class to hook into the Ansible play process.

    Most of Ansible actions will call one or several methods of
    this class so we can take decision or store error messages
    based on the current execution of a Play.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failure = None

    def raise_for_error(self):
        """Raise an error if something failed during an Ansible Play"""
        if self.failure is not None:
            raise errors.UnprocessableError(
                    'Ansible playbook execution failed',
                    **self.failure)

    # From here on, Ansible hooks definition

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if not ignore_errors:
            self.failure = {
                    result._host.get_name(): result._result,
            }
        super().v2_runner_on_failed(result, ignore_errors)

    def v2_runner_on_unreachable(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }
        super().v2_runner_on_unreachable(result)

    def v2_runner_on_async_failed(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }
        super().v2_runner_on_async_failed(result)

    def v2_runner_item_on_failed(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }
        super().v2_runner_item_on_failed(result)


class Options:
    """Utility class that mimic a namedtuple or an argparse's Namespace
    so that Ansible can extract out whatever option we pass in.
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class PlaybookBuilder():
    """Easy Playbook configuration and launching"""

    def __init__(self, agent_address, group_name='agent', username=None, password=None):
        self.inventory_filename = None
        with tempfile.NamedTemporaryFile('w', delete=False) as inventory:
            print('[{}]'.format(group_name), file=inventory)
            print(agent_address, file=inventory)
            self.inventory_filename = inventory.name

        self.variables = VariableManager()
        self.loader = DataLoader()
        self.passwords = {
                'conn_pass': password,
                'become_pass': password,
        }
        self.options = Options(  # Fill in required default values
                connection='smart',
                forks=5,
                module_path=None,
                become=None,
                become_method='sudo',
                become_user='root',
                check=False,
                listhosts=False,
                listtasks=False,
                listtags=False,
                syntax=False,
                tags=[],
        )
        if username is None:
            self.options.remote_user = 'openbach-admin'
            self.options.private_key_file = '/home/openbach/.ssh/id_rsa'
        else:
            self.options.remote_user = username
        self.variables.options_vars = load_options_vars(self.options)
        self.inventory = Inventory(
                loader=self.loader,
                variable_manager=self.variables,
                host_list=self.inventory_filename)
        self.variables.set_inventory(self.inventory)

    def __del__(self):
        """Remove the Inventory file when this object is garbage collected"""
        if self.inventory_filename is not None:
            os.remove(self.inventory_filename)

    def add_variables(self, **kwargs):
        """Add extra_vars for the current playbook execution.

        Equivalent to using multiple -e with key=value pairs
        on the Ansible command line.
        """
        variables = self.variables.extra_vars
        variables.update(kwargs)
        self.variables.extra_vars = variables

    def launch_playbook(self, *tags):
        """Actually run the configured Playbook.

        Check that the configuration is valid before doing so
        and raise a ConductorError if not.
        """
        self.options.tags[:] = tags
        playbook_results = PlayResult()
        C.DEFAULT_STDOUT_CALLBACK = playbook_results

        tasks = PlaybookExecutor(
                playbooks=['/opt/openbach/controller/ansible/conductor.yml'],
                inventory=self.inventory, variable_manager=self.variables,
                loader=self.loader, options=self.options,
                passwords=self.passwords)
        tasks.run()
        playbook_results.raise_for_error()

    def install_collector(self, collector):
        self.add_variables(
                openbach_collector=collector.address,
                logstash_logs_port=collector.logs_port,
                logstash_stats_port=collector.stats_port,
                elasticsearch_port=collector.logs_query_port,
                elasticsearch_cluster_name=collector.logs_database_name,
                influxdb_port=collector.stats_query_port,
                influxdb_database_name=collector.stats_database_name,
                influxdb_database_precision=collector.stats_database_precision,
                broadcast_mode=collector.logstash_broadcast_mode,
                auditorium_broadcast_port=collector.logstash_broadcast_port)
        self.launch_playbook('install_collector')

    @classmethod
    def uninstall_collector(cls, collector):
        self = cls(collector.address, group_name='collector')
        self.add_variables(
                openbach_collector=collector.address,
                logstash_logs_port=collector.logs_port,
                logstash_stats_port=collector.stats_port,
                elasticsearch_port=collector.logs_query_port,
                elasticsearch_cluster_name=collector.logs_database_name,
                influxdb_port=collector.stats_query_port,
                influxdb_database_name=collector.stats_database_name,
                influxdb_database_precision=collector.stats_database_precision,
                broadcast_mode=collector.logstash_broadcast_mode,
                auditorium_broadcast_port=collector.logstash_broadcast_port)
        self.launch_playbook('uninstall_collector')

    def install_agent(self, agent):
        collector = agent.collector
        self.add_variables(
                openbach_collector=collector.address,
                logstash_logs_port=collector.logs_port,
                logstash_stats_port=collector.stats_port,
                elasticsearch_port=collector.logs_query_port,
                elasticsearch_cluster_name=collector.logs_database_name,
                influxdb_port=collector.stats_query_port,
                influxdb_database_name=collector.stats_database_name,
                influxdb_database_precision=collector.stats_database_precision,
                broadcast_mode=collector.logstash_broadcast_mode)
        self.launch_playbook('install_agent')

    @classmethod
    def uninstall_agent(cls, agent):
        self = cls(agent.address)
        collector = agent.collector
        self.add_variables(
                openbach_collector=collector.address,
                logstash_logs_port=collector.logs_port,
                logstash_stats_port=collector.stats_port,
                elasticsearch_port=collector.logs_query_port,
                elasticsearch_cluster_name=collector.logs_database_name,
                influxdb_port=collector.stats_query_port,
                influxdb_database_name=collector.stats_database_name,
                influxdb_database_precision=collector.stats_database_precision,
                broadcast_mode=collector.logstash_broadcast_mode)
        self.launch_playbook('uninstall_agent')

    @classmethod
    def check_connection(cls, address):
        self = cls(address)
        self.launch_playbook('check_connection')

    @classmethod
    def assign_collector(cls, address, collector):
        self = cls(address)
        self.add_variables(
                collector_ip=collector.address,
                logstash_logs_port=collector.logs_port,
                elasticsearch_port=collector.logs_query_port,
                logstash_stats_port=collector.stats_port,
                influxdb_port=collector.stats_query_port,
                influxdb_database_name=collector.stats_database_name,
                influxdb_database_precision=collector.stats_database_precision)
        self.launch_playbook('assign_collector')

    @classmethod
    def install_job(cls, agent, job):
        self = cls(agent.address)
        job_name = job.name
        job_path = job.path
        self.add_variables(
                openbach_collector=agent.collector.address,
                jobs=[{'name': job_name, 'path': job_path}])
        self.launch_playbook('install_a_job')

    @classmethod
    def uninstall_job(cls, agent, job):
        self = cls(agent.address)
        job_name = job.name
        job_path = job.path
        self.add_variables(
                openbach_collector=agent.collector.address,
                jobs=[{'name': job_name, 'path': job_path}])
        self.launch_playbook('uninstall_a_job')

    @classmethod
    def enable_logs(cls, address, job, transfer_id, severity, local_severity):
        self = cls(address)
        self.add_variables(job=job, transfer_id=transfer_id)
        if severity != 8:
            self.add_variables(syslogseverity=severity)
        if local_severity != 8:
            self.add_variables(syslogseverity_local=local_severity)
        self.launch_playbook('enable_logs')

    @classmethod
    def push_file(cls, address, local_path, remote_path):
        self = cls(address)
        self.add_variables(local_path=local_path, remote_path=remote_path)
        self.launch_playbook('push_file')
