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


from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.inventory import Inventory
from ansible.parsing.dataloader import DataLoader
from ansible.playbook import Playbook
from ansible.playbook.play import Play
from ansible.plugins.callback import CallbackBase
from ansible.utils.vars import load_options_vars
from ansible.vars import VariableManager

import errors
from playbooks import PREDEFINED_PLAYS


class PlayResult(CallbackBase):
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
            raise errors.UnprocessableError('Ansible playbook execution failed', **self.failure)

    # From here on, Ansible hooks definition

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if not ignore_errors:
            self.failure = {
                    result._host.get_name(): result._result,
            }

    def v2_runner_on_ok(self, result):
        pass

    def v2_runner_on_skipped(self, result):
        pass

    def v2_runner_on_unreachable(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }

    def v2_runner_on_no_hosts(self, task):
        pass

    def v2_runner_on_async_poll(self, result):
        pass

    def v2_runner_on_async_ok(self, result):
        pass

    def v2_runner_on_async_failed(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }

    def v2_runner_on_file_diff(self, result, diff):
        pass

    def v2_playbook_on_start(self, playbook):
        pass

    def v2_playbook_on_notify(self, result, handler):
        pass

    def v2_playbook_on_no_hosts_matched(self):
        self.playbook_on_no_hosts_matched()

    def v2_playbook_on_no_hosts_remaining(self):
        self.playbook_on_no_hosts_remaining()

    def v2_playbook_on_task_start(self, task, is_conditional):
        pass

    def v2_playbook_on_cleanup_task_start(self, task):
        pass

    def v2_playbook_on_handler_task_start(self, task):
        pass

    def v2_playbook_on_vars_prompt(self, varname, private=True, prompt=None, encrypt=None, confirm=False, salt_size=None, salt=None, default=None):
        pass

    def v2_playbook_on_setup(self):
        pass

    def v2_playbook_on_import_for_host(self, result, imported_file):
        host = result._host.get_name()
        self.playbook_on_import_for_host(host, imported_file)

    def v2_playbook_on_not_import_for_host(self, result, missing_file):
        host = result._host.get_name()
        self.playbook_on_not_import_for_host(host, missing_file)

    def v2_playbook_on_play_start(self, play):
        pass

    def v2_playbook_on_stats(self, stats):
        pass

    def v2_on_file_diff(self, result):
        pass

    def v2_playbook_on_include(self, included_file):
        pass

    def v2_runner_item_on_ok(self, result):
        pass

    def v2_runner_item_on_failed(self, result):
        self.failure = {
                result._host.get_name(): result._result,
        }

    def v2_runner_item_on_skipped(self, result):
        pass

    def v2_runner_retry(self, result):
        pass


class Options:
    """Utility class that mimic a namedtuple or an argparse's Namespace
    so that Ansible can extract out whatever option we pass in.
    """
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class PlaybookBuilder():
    """Easy Playbook/Plays configuration and launching"""

    def __init__(self):
        self.variables = VariableManager()
        self.loader = DataLoader()
        self.passwords = {}
        self.options = None
        self.inventory = None
        self.play = None

    @classmethod
    def from_agent(cls, agent):
        """Create an instance of the class where most of the
        configuration is extracted from the provided agent.
        """
        instance = cls()
        instance.host = agent.address
        instance.configure_user(agent.username, agent.password)
        return instance

    @classmethod
    def default(cls, filename, address, username, password):
        """Create an instance of the class using default
        OpenBACH's extra_vars files.
        """
        instance = cls()
        instance.host = address
        instance.load_variables('/opt/openbach-controller/configs/all')
        instance.load_variables('/opt/openbach-controller/configs/ips')
        instance.load_variables('/opt/openbach-controller/configs/proxy')
        instance.configure_user(username, password)
        instance.configure_playbook(filename)
        return instance

    def configure_playbook(self, filename, **kwargs):
        """Plan the execution of the given playbook or a predefined
        Play that can be configured using keyword parameters.
        """
        try:
            # Check if filename is actually a file name or
            # rather the name of a predefined play
            play_builder = PREDEFINED_PLAYS[filename]
        except KeyError:
            self.play = Playbook.load(filename, self.variables, self.loader)
        else:
            play_source = play_builder(**kwargs)
            self.play = Play.load(play_source, variable_manager=self.variables, loader=self.loader)

    def configure_user(self, user, password, sudo_password=None):
        """Configure Ansible's options based on the given user informations"""
        self.passwords['conn_pass'] = password
        self.passwords['become_pass'] = password if sudo_password is None else sudo_password
        self.options = Options(  # Fill in required default values
                connection='smart',
                forks=5,
                module_path=None,
                become=None,
                become_method='sudo',
                become_user='root',
                check=False,
                remote_user=user,
                tags=[],
        )
        self.variables.options_vars = load_options_vars(self.options)

    @property
    def host(self):
        """Manage the name/ip of the agent the playbook will run on"""
        if self.inventory is None:
            return None
        return self.inventory.groups['all'].hosts[0].get_name()

    @host.setter
    def host(self, agent_ip):
        self.inventory = Inventory(loader=self.loader, variable_manager=self.variables, host_list=[agent_ip])
        self.variables.set_inventory(self.inventory)

    @host.deleter
    def host(self):
        self.inventory = None
        self.variables.set_inventory(None)

    def add_variables(self, **kwargs):
        """Add extra_vars for the current playbook execution.

        Equivalent to using multiple -e with key=value pairs
        on the Ansible command line.
        """
        variables = self.variables.extra_vars
        variables.update(kwargs)
        self.variables.extra_vars = variables

    def load_variables(self, filename):
        """Load extra_vars from a file for the current playbook execution.

        Equivalent to using -e @filename on the Ansible command line.
        """
        variables = self.variables.extra_vars
        variables.update(self.loader.load_from_file(filename))
        self.variables.extra_vars = variables

    def launch_playbook(self, *tags):
        """Actually run the configured Playbook/Play.

        Check that the configuration is valid before doing so
        and raise a ConductorError if not.
        """
        if self.options is None:
            raise errors.ConductorError('Programming error: Ansible playbook launched without options')
        if self.inventory is None:
            raise errors.ConductorError('Programming error: Ansible playbook launched with no associated host')
        if self.play is None:
            raise errors.ConductorError('Programming error: Ansible playbook launched without a playbook')

        self.options.tags.extend(tags)
        playbook_results = PlayResult()
        tasks = TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variables,
                loader=self.loader,
                options=self.options,
                passwords=self.passwords,
                stdout_callback=playbook_results,
        )
        try:
            tasks.run(self.play)
        finally:
            tasks.cleanup()
        playbook_results.raise_for_error()
