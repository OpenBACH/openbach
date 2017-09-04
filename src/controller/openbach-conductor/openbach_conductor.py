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


"""OpenBACH's core decision center.

The conductor is responsible to check that requests conveyed by the
backend are complete and well formed. If they do, appropriate actions
are then performed to fulfill them and return meaningful result to
the backend.

Messages are received from and send to the backend by the means of
a FIFO file so any amount of data can easily be transfered.
"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import re
import json
import time
import queue
import shutil
import signal
import syslog
import tarfile
import threading
import itertools
import traceback
import socketserver
from datetime import datetime
from contextlib import suppress
from collections import defaultdict

import yaml
import requests
from fuzzywuzzy import fuzz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError

import errors
from openbach_baton import OpenBachBaton
from playbook_builder import start_playbook, setup_playbook_manager


# We need to use ansible from Python code so we can easily get failure
# messages. But its forking behaviour is causing troubles with Django
# (namely, closing database connections at the end of the forked
# process). So we setup a fork here before any of the Django stuff so
# connections are not shared with ansible workers.
setup_playbook_manager()


from django.core.wsgi import get_wsgi_application
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
application = get_wsgi_application()
from django import db
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder

from openbach_django.models import (
        CommandResult, CollectorCommandResult, Collector,
        AgentCommandResult, Agent, Job, Keyword,
        Statistic, OsCommand, Entity, Network,
        RequiredJobArgument, OptionalJobArgument,
        InstalledJob, InstalledJobCommandResult,
        JobInstance, JobInstanceCommandResult,
        StatisticInstance, ScenarioInstance,
        OpenbachFunction, OpenbachFunctionInstance,
        Watch, Scenario, Project, FileCommandResult,
        ScenarioArgument, ScenarioArgumentValue,
)


syslog.openlog('openbach_conductor', syslog.LOG_PID, syslog.LOG_USER)


DEFAULT_JOBS = '/opt/openbach/controller/ansible/roles/install_job/defaults/main.yml'
_SEVERITY_MAPPING = {
    1: 3,   # Error
    2: 4,   # Warning
    3: 6,   # Informational
    4: 7,   # Debug
}


def convert_severity(severity):
    """Convert the syslog severity to the equivalent openbach severity"""
    return _SEVERITY_MAPPING.get(severity, 8)


def get_master_scenario_id(scenario_id):
    """Get all the way up to the sub-scenario chain to retrieve
    the ID of the root Scenario.

    If `scenario_id` is neither the ID of a Scenario nor the ID
    of a subscenario, returns itself.
    """
    try:
        scenario = ScenarioInstance.objects.get(id=scenario_id)
    except ScenarioInstance.DoesNotExist:
        return scenario_id

    while scenario.openbach_function_instance is not None:
        scenario = scenario.openbach_function_instance.scenario_instance
    return scenario.id


def get_default_jobs(section):
    """Generate the names of default jobs found in the given section.

    If an error occurs (no file, parsing error, missing section...),
    gracefully return without exceptions.
    """
    with suppress(IOError, KeyError, yaml.YAMLError):
        with open(DEFAULT_JOBS) as stream:
            content = yaml.load(stream)
        for job in content[section]:
            yield job['name']


def extract_and_check_name_from_json(json_data, existing_name=None, *, kind):
    """Retrieve the `name` attribute from a JSON data and check that
    it matches the provided name, if any.

    This function is aimed at simplifying the first check on a Project
    or a Scenario creation/modification.
    """
    try:
        name = json_data['name']
    except KeyError:
        if existing_name is None:
            raise errors.BadRequestError(
                    'You must provide a name to create a {}'.format(kind))
        else:
            kwargs = {kind.lower(): existing_name}
            raise errors.BadRequestError(
                    'The {0} data to modify an existing {0} '
                    'does not contain the {0} name.'.format(kind),
                    **kwargs)

    if existing_name is not None and name != existing_name:
        lower_type = kind.lower()
        kwargs = {lower_type: existing_name, 'name': name}
        raise errors.BadRequestError(
                'The name in the {} data does not match '
                'with the name of the {}.'.format(kind, lower_type),
                **kwargs)
    return name


def signal_term_handler(signal, frame):
    """Gracefully terminate the Conductor by setting the state of
    all started Scenarios to 'Stopped'.
    """
    for scenario_instance in ScenarioInstance.objects.all():
        scenario_instance.stop()
    exit(0)


class IDGenerator:
    """Thread safe incremental ID generator"""
    __state = {'id': 0, '_mutex': threading.Lock()}

    def __init__(self):
        """Use the Borg pattern to share the same state
        among every instances.
        """
        self.__dict__ = self.__class__.__state

    def __next__(self):
        with self._mutex:
            self.id += 1
            return self.id


class ConductorAction:
    """Base Template class that correspond to an action supported
    by the conductor.

    Subclasses are usually directly mapped to a route that the
    backend handles and will perform the requested action.
    """

    def __init__(self, **kwargs):
        self.openbach_function_instance = None
        for name, value in kwargs.items():
            setattr(self, name, value)

    def action(self):
        """Public entry point to execute the required action"""
        return self._action()

    def _action(self):
        """Override this in subclasses to implement the desired action"""
        raise NotImplementedError


class OpenbachFunctionMixin:
    """Mixin describing that a specific ConductorAction can also be
    called as an OpenBACH Function.
    """

    def openbach_function(self, openbach_function_instance):
        """Public entry point to execute the required OpenBACH Function"""
        self.openbach_function_instance = openbach_function_instance
        if isinstance(self, ThreadedAction):
            self._threaded_action(self._action)
        else:
            self._action()
        return []


class ThreadedAction(ConductorAction):
    """Specific kind of action that is known to take a long time (usually
    by launching playbooks).

    Such action will immediately return with a 202 (Accepted) status code
    and set the state of the action in the backend database. Clients are
    responsible to check this state regularly to know when the action
    actually terminates.
    """

    def action(self):
        """Public entry point to execute the required action"""
        real_action = super().action
        thread = threading.Thread(target=self._threaded_action, args=(real_action,))
        thread.start()
        return {}, 202

    def _create_command_result(self):
        """Override this in subclasses to create the required CommandResult"""
        raise NotImplementedError

    def _threaded_action(self, real_action):
        command_result = self._create_command_result()
        try:
            real_action()
        except errors.ConductorError as e:
            command_result.update(e.json, e.ERROR_CODE)
            raise
        except Exception as err:
            infos = {
                    'message': 'An unexpected error occured',
                    'error': str(err),
                    'traceback': traceback.format_exc(),
            }
            command_result.update(infos, 500)
            raise
        command_result.update(None, 204)

    @staticmethod
    def set_running(aggregator, field_name):
        """Get a CommandResult from a nullable field of the given
        aggregator and set its inner state to 'Running'.
        """
        command_result = getattr(aggregator, field_name)
        if command_result is None:
            new_result = CommandResult()
            new_result.save()
            setattr(aggregator, field_name, new_result)
            aggregator.save()
            return new_result

        command_result.reset()
        return command_result


#############
# Collector #
#############

class CollectorAction(ConductorAction):
    """Base class that defines helper methods to deal with Collectors"""

    def get_collector_or_not_found_error(self):
        try:
            return Collector.objects.get(address=self.address)
        except Collector.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Collector is not in the database',
                    collector_address=self.address)


class AddCollector(ThreadedAction, CollectorAction):
    """Action responsible for the installation of a Collector"""

    def __init__(self, address, name, username=None,
                 password=None, logs_port=None,
                 logs_query_port=None, cluster_name=None,
                 stats_port=None, stats_query_port=None,
                 database_name=None, database_precision=None,
                 broadcast_mode=None, broadcast_port=None,
                 skip_playbook=False):
        super().__init__(
                address=address, name=name, username=username,
                password=password, logs_port=logs_port,
                stats_port=stats_port, cluster_name=cluster_name,
                logs_query_port=logs_query_port,
                stats_query_port=stats_query_port,
                database_name=database_name,
                database_precision=database_precision,
                broadcast_mode=broadcast_mode,
                broadcast_port=broadcast_port,
                skip_playbook=skip_playbook)

    def _create_command_result(self):
        command_result, _ = CollectorCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_add')

    def _action(self):
        collector, created = Collector.objects.get_or_create(address=self.address)
        collector.update(
                self.logs_port,
                self.logs_query_port,
                self.cluster_name,
                self.stats_port,
                self.stats_query_port,
                self.database_name,
                self.database_precision,
                self.broadcast_mode,
                self.broadcast_port)

        if not self.skip_playbook:
            try:
                # Perform physical installation through a playbook
                start_playbook(
                        'install_collector',
                        collector.json,
                        self.username,
                        self.password)
            except errors.ConductorError:
                collector.delete()
                raise

        # An agent was installed by the playbook so create it in DB
        agent = InstallAgent(
                self.address, self.name,
                self.address, skip_playbook=True)
        with suppress(errors.ConductorWarning):
            agent._threaded_action(agent._action)

        for job_name in get_default_jobs('default_collector_jobs'):
            with suppress(errors.ConductorError):
                job = InstallJob(self.address, job_name, skip_playbook=True)
                job._threaded_action(job._action)

        if not created:
            raise errors.ConductorWarning(
                    'A Collector was already installed, configuration updated',
                    collector_address=self.address)


class ModifyCollector(ThreadedAction, CollectorAction):
    """Action responsible of modifying the configuration of a Collector"""

    def __init__(self, address, logs_port=None,
                 logs_query_port=None, cluster_name=None,
                 stats_port=None, stats_query_port=None,
                 database_name=None, database_precision=None,
                 broadcast_mode=None, broadcast_port=None):
        super().__init__(
                address=address, logs_port=logs_port,
                stats_port=stats_port, cluster_name=cluster_name,
                logs_query_port=logs_query_port,
                stats_query_port=stats_query_port,
                database_name=database_name,
                database_precision=database_precision,
                broadcast_mode=broadcast_mode,
                broadcast_port=broadcast_port)

    def _create_command_result(self):
        command_result, _ = CollectorCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_modify')

    def _action(self):
        collector = self.get_collector_or_not_found_error()
        updated = collector.update(
                self.logs_port,
                self.logs_query_port,
                self.cluster_name,
                self.stats_port,
                self.stats_query_port,
                self.database_name,
                self.database_precision,
                self.broadcast_mode,
                self.broadcast_port)

        if not updated:
            raise errors.ConductorWarning('No modification to do')

        for agent in collector.agents.all():
            start_playbook('assign_collector', agent.address, collector.json)


class DeleteCollector(ThreadedAction, CollectorAction):
    """Action responsible for the uninstallation of a Collector"""

    def __init__(self, address):
        super().__init__(address=address)

    def _create_command_result(self):
        command_result, _ = CollectorCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_del')

    def _action(self):
        collector = self.get_collector_or_not_found_error()
        other_agents = collector.agents.exclude(address=self.address)
        if other_agents:
            raise errors.ConflictError(
                    'The requested Collector is still bound to other Agents',
                    collector_address=self.address,
                    agents_addresses=[agent.address for agent in other_agents])

        # Perform physical uninstallation through a playbook
        start_playbook('uninstall_collector', collector.json)

        # The associated Agent was removed by the playbook, remove it from DB
        try:
            agent = collector.agents.get(address=self.address)
        except Agent.DoesNotExist:
            pass
        else:
            agent.delete()
        finally:
            collector.delete()


class InfosCollector(CollectorAction):
    """Action responsible for information retrieval about a Collector"""

    def __init__(self, address):
        super().__init__(address=address)

    def _action(self):
        collector = self.get_collector_or_not_found_error()
        return collector.json, 200


class ListCollectors(CollectorAction):
    """Action responsible for information retrieval about all Collectors"""

    def __init__(self):
        super().__init__()

    def _action(self):
        infos = [c.json for c in Collector.objects.all()]
        return infos, 200


#########
# Agent #
#########

class AgentAction(ConductorAction):
    """Base class that defines helper methods to deal with Agents"""

    def get_agent_or_not_found_error(self):
        try:
            return Agent.objects.get(address=self.address)
        except Agent.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Agent is not in the database',
                    agent_address=self.address)

    def _update_agent(self):
        """Update the local status of an Agent by trying to connect to it"""
        agent = self.get_agent_or_not_found_error()
        try:
            start_playbook('check_connection', agent.address)
        except errors.ConductorError:
            agent.set_reachable(False)
            agent.set_available(False)
            agent.set_status('Agent unreachable')
            agent.save()
            return

        agent.set_reachable(True)
        try:
            OpenBachBaton(agent.address)
        except errors.UnprocessableError:
            agent.set_available(False)
            agent.set_status('Agent reachable but daemon not available')
        else:
            agent.set_available(True)
            agent.set_status('Available')
        agent.save()


class InstallAgent(OpenbachFunctionMixin, ThreadedAction, AgentAction):
    """Action responsible for the installation of an Agent"""

    def __init__(self, address, name, collector_ip,
                 username=None, password=None, skip_playbook=False):
        super().__init__(address=address, username=username,
                         name=name, password=password,
                         collector_ip=collector_ip,
                         skip_playbook=skip_playbook)

    def _create_command_result(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_install')

    def _action(self):
        collector_info = InfosCollector(self.collector_ip)
        collector = collector_info.get_collector_or_not_found_error()
        agent, created = Agent.objects.get_or_create(
                address=self.address, defaults={
                    'name': self.name,
                    'collector': collector,
                })
        agent.name = self.name
        agent.set_reachable(True)
        agent.set_available(False)
        agent.set_status('Installing...')
        agent.collector = collector
        agent.save()

        if not self.skip_playbook:
            try:
                # Perform physical installation through a playbook
                start_playbook(
                        'install_agent',
                        agent.address,
                        collector.json,
                        self.username,
                        self.password)
            except errors.ConductorError as e:
                agent.delete()
                raise
        agent.set_available(True)
        agent.set_status('Available')
        agent.save()

        for job_name in get_default_jobs('default_jobs'):
            with suppress(errors.ConductorError):
                job = InstallJob(self.address, job_name, skip_playbook=True)
                job._threaded_action(job._action)

        if not created:
            raise errors.ConductorWarning(
                    'An Agent was already installed, configuration updated',
                    agent_address=self.address)


class UninstallAgent(OpenbachFunctionMixin, ThreadedAction, AgentAction):
    """Action responsible for the uninstallation of an Agent"""

    def __init__(self, address):
        super().__init__(address=address)

    def _create_command_result(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_uninstall')

    def _action(self):
        agent = self.get_agent_or_not_found_error()
        installed_jobs = [
                {'name': installed.job.name, 'path': installed.job.path}
                for installed in agent.installed_jobs.all()
        ]
        try:
            # Perform physical uninstallation through a playbook
            start_playbook(
                    'uninstall_agent',
                    agent.address,
                    agent.collector.json,
                    jobs=installed_jobs)
        except errors.ConductorError:
            agent.set_status('Uninstall failed')
            agent.save()
            raise
        else:
            agent.delete()


class InfosAgent(AgentAction):
    """Action responsible for information retrieval about an Agent"""

    def __init__(self, address, update=False):
        super().__init__(address=address, update=update)

    def _action(self):
        if self.update:
            self._update_agent()
        agent = self.get_agent_or_not_found_error()
        return agent.json, 200


class ListAgents(AgentAction):
    """Action responsible for information retrieval about all Agents"""

    def __init__(self, update=False):
        super().__init__(update=update)

    def _action(self):
        infos = [
                InfosAgent(agent.address, self.update)._action()[0]
                for agent in Agent.objects.all()
        ]
        return infos, 200


class RetrieveStatusAgent(OpenbachFunctionMixin, ThreadedAction, AgentAction):
    """Action responsible for status retrieval about an Agent"""

    def __init__(self, address):
        super().__init__(address=address)

    def _create_command_result(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_retrieve_status_agent')

    def _action(self):
        self._update_agent()


class RetrieveStatusAgents(OpenbachFunctionMixin, ConductorAction):
    """Action responsible for status retrieval about several Agents"""

    def __init__(self, addresses):
        super().__init__(addresses=addresses)

    def _action(self):
        for address in self.addresses:
            RetrieveStatusAgent(address).action()
        return {}, 202


class RetrieveStatusJob(ThreadedAction, AgentAction):
    """Action responsible for asking an Agent to send the
    list of its Installed Jobs to its Collector.
    """

    def __init__(self, address):
        super().__init__(address=address)

    def _create_command_result(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_retrieve_status_jobs')

    def _action(self):
        agent = self.get_agent_or_not_found_error()
        OpenBachBaton(agent.address).list_jobs()


class RetrieveStatusJobs(OpenbachFunctionMixin, ConductorAction):
    """Action responsible for asking several Agent to send the
    list of their Installed Jobs to their Collector.
    """

    def __init__(self, addresses):
        super().__init__(addresses=addresses)

    def _action(self):
        for address in self.addresses:
            RetrieveStatusJob(address).action()
        return {}, 202


class AssignCollector(OpenbachFunctionMixin, ThreadedAction, AgentAction):
    """Action responsible for assigning a Collector to an Agent"""

    def __init__(self, address, collector_ip):
        super().__init__(address=address, collector_ip=collector_ip)

    def _create_command_result(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return self.set_running(command_result, 'status_assign')

    def _action(self):
        agent = self.get_agent_or_not_found_error()
        collector_infos = InfosCollector(self.collector_ip)
        collector = collector_infos.get_collector_or_not_found_error()
        start_playbook('assign_collector', self.address, collector.json)
        agent.collector = collector
        agent.save()


########
# Jobs #
########

class JobAction(ConductorAction):
    """Base class that defines helper methods to deal with Jobs"""

    def get_job_or_not_found_error(self):
        try:
            return Job.objects.get(name=self.name)
        except Job.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Job is not in the database',
                    job_name=self.name)


class AddJob(JobAction):
    """Action responsible to add a Job whose files are on the
    Controller's filesystem into the database.
    """

    def __init__(self, name, path):
        super().__init__(name=name, path=path)

    def _action(self):
        config_prefix = os.path.join(self.path, 'files', self.name)
        config_file = '{}.yml'.format(config_prefix)
        config_help = '{}.help'.format(config_prefix)
        try:
            stream = open(config_file)
        except FileNotFoundError:
            raise errors.BadRequestError(
                    'The configuration file of the Job is not present',
                    job_name=self.name,
                    configuration_file=config_file)
        with stream:
            try:
                content = yaml.load(stream)
            except yaml.YAMLError as err:
                raise errors.BadRequestError(
                        'The configuration file of the Job does not '
                        'contain valid YAML data',
                        job_name=self.name, error_message=str(err),
                        configuration_file=config_file)

        # Load the help file
        try:
            with open(config_help) as stream:
                help_content = stream.read()
        except OSError:
            help_content = None

        try:
            with db.transaction.atomic():
                self._update_job(content, help_content)
        except KeyError as err:
            raise errors.BadRequestError(
                    'The configuration file of the Job is missing an entry',
                    entry_name=str(err), job_name=self.name,
                    configuration_file=config_file)
        except (TypeError, db.utils.DataError) as err:
            raise errors.BadRequestError(
                    'The configuration file of the Job contains entries '
                    'whose values are not of the required type',
                    job_name=self.name, error_message=str(err),
                    configuration_file=config_file)
        except db.IntegrityError as err:
            raise errors.BadRequestError(
                    'The configuration file of the Job contains '
                    'duplicated entries',
                    job_name=self.name, error_message=str(err),
                    configuration_file=config_file)

        return InfosJob(self.name).action()

    def _update_job(self, content, help_content):
        """Update the values stored for a job based on its JSON"""

        general_section = content['general']
        general_section['name'] = self.name  # Enforce the two to match
        description = general_section['description']

        job, created = Job.objects.get_or_create(name=self.name)
        job.path = self.path
        job.description = description
        job.help = description if help_content is None else help_content
        job.job_version = general_section['job_version']
        job.persistent = general_section['persistent']
        job.has_uncertain_required_arg = False
        job.save()

        # Associate OSes
        os_commands = content['os']
        for os_name, os_description in os_commands.items():
            requirements = os_description.get('requirements', '')
            command = os_description['command']
            command_stop = os_description.get('command_stop')
            os_command, _ = OsCommand.objects.get_or_create(
                    job=job, name=os_name,
                    defaults={
                        'requirements': requirements,
                        'command': command,
                        'command_stop': command_stop,
                    })
            os_command.requirements = requirements
            os_command.command = command
            os_command.command_stop = command_stop
            os_command.save()
        # Remove OSes associated to the previous version of the job
        job.os.exclude(name__in=os_commands).delete()

        # Associate "new" keywords
        keywords = general_section['keywords']
        for keyword in keywords:
            job_keyword, _ = Keyword.objects.get_or_create(name=keyword)
            job.keywords.add(job_keyword)
        # Remove keywords associated to the previous version of the job
        job.keywords = Keyword.objects.filter(
                jobs__name__exact=self.name,
                name__in=keywords)

        # Associate "new" statistics
        statistics = content.get('statistics')
        # No EAFP here to support entry with empty content
        if statistics is not None:
            for statistic in statistics:
                stat, _ = Statistic.objects.get_or_create(
                        name=statistic['name'], job=job)
                stat.description = statistic['description']
                stat.frequency = statistic['frequency']
                stat.save()
            stats_names = {stat['name'] for stat in statistics}
        else:
            stats_names = set()
        # Remove statistics associated to the previous version of the job
        job.statistics.exclude(name__in=stats_names).delete()

        # Associate "new" required arguments
        job.required_arguments.all().delete()
        arguments = content.get('arguments', {}).get('required')
        if arguments is not None:
            for rank, argument in enumerate(arguments):
                RequiredJobArgument.objects.create(
                        job=job, rank=rank, name=argument['name'],
                        type=argument['type'], count=str(argument['count']),
                        description=argument.get('description', ''))

        # Associate "new" optional arguments
        job.optional_arguments.all().delete()
        arguments = content.get('arguments', {}).get('optional')
        if arguments is not None:
            for argument in arguments:
                OptionalJobArgument.objects.create(
                        job=job, name=argument['name'], flag=argument['flag'],
                        type=argument['type'], count=str(argument['count']),
                        description=argument.get('description', ''))


class AddTarJob(JobAction):
    """Action responsible to add a Job whose files are sent in
    a .tar file into the database.
    """

    def __init__(self, name, path):
        super().__init__(name=name, path=path)

    def _action(self):
        path = '/opt/openbach/controller/src/jobs/private_jobs/{}'.format(self.name)
        try:
            with tarfile.open(self.path) as tar_file:
                tar_file.extractall(path)
        except tarfile.ReadError as err:
            raise errors.ConductorError(
                    'Failed to uncompress the provided tar file',
                    error_message=str(err))
        add_job_action = AddJob(self.name, path)
        return add_job_action.action()


class DeleteJob(JobAction):
    """Action responsible of removing a Job from the filesystem"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        job = self.get_job_or_not_found_error()
        path = job.path
        job.delete()

        shutil.rmtree(path, ignore_errors=True)
        if os.path.exists(path):
            return {
                    'warning': 'Job deleted but some files '
                               'remain on the controller',
                    'job_name': self.name,
            }, 200
        return None, 204


class InfosJob(JobAction):
    """Action responsible for information retrieval about a Job"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        job = self.get_job_or_not_found_error()
        return job.json, 200


class ListJobs(JobAction):
    """Action responsible to search information about Jobs"""

    def __init__(self, string_to_search=None, ratio=60):
        super().__init__(name=string_to_search, ratio=ratio)

    def _action(self):
        if self.name is None:
            return [job.json for job in Job.objects.all()], 200

        return list(self._fuzzy_matching()), 200

    def _fuzzy_matching(self):
        delimiters = re.compile(r'\W|_')
        for job in Job.objects.all():
            search_fields = itertools.chain(
                    delimiters.split(job.name),
                    job.keywords.all())
            if any(fuzz.token_set_ratio(word, self.name) > self.ratio
                   for word in search_fields):
                yield job


class GetKeywordsJob(JobAction):
    """Action responsible for retrieval of the keywords of a Job"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        job = self.get_job_or_not_found_error()
        keywords = [keyword.name for keyword in job.keywords.all()]
        return {'job_name': job.name, 'keywords': keywords}, 200


class GetStatisticsJob(JobAction):
    """Action responsible for retrieval of the statistics of a Job"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        job = self.get_job_or_not_found_error()
        stats = [stat.json for stat in job.statistics.all()]
        return {'job_name': job.name, 'statistics': stats}, 200


class GetHelpJob(JobAction):
    """Action responsible for retrieval of the help on a Job"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        job = self.get_job_or_not_found_error()
        return {'job_name': job.name, 'help': job.help}, 200


##################
# Installed Jobs #
##################

class InstalledJobAction(ConductorAction):
    """Base class that defines helper methods to deal with InstalledJobs"""

    def get_installed_job_or_not_found_error(self):
        job = InfosJob(self.name).get_job_or_not_found_error()
        agent = InfosAgent(self.address).get_agent_or_not_found_error()
        try:
            return InstalledJob.objects.get(agent=agent, job=job)
        except InstalledJob.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Installed Job is not in the database',
                    agent_address=self.address, job_name=self.name)


class InstallJob(ThreadedAction, InstalledJobAction):
    """Action responsible for installing a Job on an Agent"""

    def __init__(self, address, name, severity=1, local_severity=1, skip_playbook=False):
        super().__init__(address=address, name=name, skip_playbook=skip_playbook,
                         severity=severity, local_severity=local_severity)

    def _create_command_result(self):
        command_result, _ = InstalledJobCommandResult.objects.get_or_create(
                agent_ip=self.address,
                job_name=self.name)
        return self.set_running(command_result, 'status_install')

    def _action(self):
        agent = InfosAgent(self.address).get_agent_or_not_found_error()
        job = InfosJob(self.name).get_job_or_not_found_error()

        if not self.skip_playbook:
            # Physically install the job on the agent
            start_playbook(
                    'install_job',
                    agent.address,
                    agent.collector.address,
                    job.name, job.path)
        OpenBachBaton(self.address).add_job(self.name)

        installed_job, created = InstalledJob.objects.get_or_create(agent=agent, job=job)
        installed_job.severity = self.severity
        installed_job.local_severity = self.local_severity
        installed_job.update_status = timezone.now()
        installed_job.save()

        with suppress(errors.ConductorError):
            severity_setter = SetLogSeverityJob(
                    self.address, self.name,
                    self.severity, self.local_severity)
            severity_setter._threaded_action(severity_setter._action)

        if not created:
            raise errors.ConductorWarning(
                    'A Job was already installed on an '
                    'Agent, configuration updated',
                    agent_address=self.address, job_name=self.name)


class InstallJobs(InstalledJobAction):
    """Action responsible for installing several Jobs on several Agents"""

    def __init__(self, addresses, names, severity=1, local_severity=1):
        super().__init__(addresses=addresses, names=names,
                         severity=severity, local_severity=local_severity)

    def _action(self):
        for name, address in itertools.product(self.names, self.addresses):
            InstallJob(address, name, self.severity, self.local_severity).action()
        return {}, 202


class UninstallJob(ThreadedAction, InstalledJobAction):
    """Action responsible for uninstalling a Job on an Agent"""

    def __init__(self, address, name):
        super().__init__(address=address, name=name)

    def _create_command_result(self):
        command_result, _ = InstalledJobCommandResult.objects.get_or_create(
                agent_ip=self.address,
                job_name=self.name)
        return self.set_running(command_result, 'status_uninstall')

    def _action(self):
        installed_job = self.get_installed_job_or_not_found_error()
        agent = installed_job.agent
        job = installed_job.job
        installed_job.delete()
        OpenBachBaton(agent.address).remove_job(job.name)
        start_playbook(
                'uninstall_job',
                agent.address,
                agent.collector.address,
                job.name, job.path)


class UninstallJobs(InstalledJobAction):
    """Action responsible for uninstalling several Jobs on several Agents"""

    def __init__(self, addresses, names):
        super().__init__(addresses=addresses, names=names)

    def _action(self):
        for name, address in itertools.product(self.names, self.addresses):
            UninstallJob(address, name).action()
        return {}, 202


class InfosInstalledJob(InstalledJobAction):
    """Action responsible for information retrieval about an Installed Job"""

    def __init__(self, address, name):
        super().__init__(address=address, name=name)

    def _action(self):
        installed_job = self.get_installed_job_or_not_found_error()
        return installed_job.json, 200


class ListInstalledJobs(InstalledJobAction):
    """Action responsible for information retrieval about
    all Installed Job on an Agent.
    """
    UPDATE_JOB_URL = (
            'http://{agent.collector.address}:{agent.collector.stats_query_port}/query?'
            'db={agent.collector.stats_database_name}&'
            'epoch={agent.collector.stats_database_precision}&'
            'q=SELECT+*+FROM+"openbach_agent"+'
            'WHERE+"@agent_name"+=+\'{agent.name}\'+'
            'AND+_type+=\'job_list\'+GROUP+BY+*+ORDER+BY+DESC+LIMIT+1')

    def __init__(self, address, update=False):
        super().__init__(address=address, update=update)

    def _action(self):
        agent = InfosAgent(self.address).get_agent_or_not_found_error()
        update_errors = []

        # TODO better update
        if self.update:
            url = self.UPDATE_JOB_URL.format(agent=agent)
            result = requests.get(url).json()
            try:
                serie = result['results'][0]['series'][0]
                columns = serie['columns']
                values = serie['values'][0]
            except LookupError:
                raise errors.ConductorError(
                        'Cannot retrieve the jobs status in the Collector',
                        collector_response=result)

            jobs = {
                    value for column, value in zip(columns, values)
                    if column not in ('time', 'nb', '_type')
            }
            tz = timezone.get_current_timezone()
            date_value = values[columns.index('time')]
            date = datetime.fromtimestamp(date_value / 1000, tz)
            for job in agent.installed_jobs.all():
                name = job.job.name
                if name not in jobs:
                    job.delete()  # Not installed anymore
                else:
                    job.update_status = date
                    job.save()
                    jobs.remove(name)

            # Store remaining installed jobs in the database
            for job_name in jobs:
                try:
                    job = Job.objects.get(name=job_name)
                except Job.DoesNotExist:
                    update_errors.append({
                        'message': 'A Job on the Agent is not found in the database',
                        'job_name': job_name,
                    })
                else:
                    InstalledJob.objects.create(
                            agent=agent, job=job,
                            update_status=date,
                            severity=4,
                            local_severity=4)

        infos = [job.json for job in agent.installed_jobs.all()]
        result = {
                'agent': self.address,
                'installed_jobs': infos,
        }
        if update_errors:
            result['errors'] = update_errors
        return result, 200


class SetLogSeverityJob(OpenbachFunctionMixin, ThreadedAction, InstalledJobAction):
    """Action responsible for changing the log severity of an Installed Job"""

    def __init__(self, address, name, severity, local_severity=None, date=None):
        super().__init__(address=address, name=name, severity=severity,
                         local_severity=local_severity, date=date)

    def _create_command_result(self):
        command_result, _ = InstalledJobCommandResult.objects.get_or_create(
                agent_ip=self.address, job_name=self.name)
        return self.set_running(command_result, 'status_log_severity')

    def _action(self):
        installed_job = self.get_installed_job_or_not_found_error()
        local_severity = self.local_severity
        if self.local_severity is None:
            local_severity = installed_job.local_severity
        self._physical_set_severity(self.severity, local_severity)

        installed_job.severity = self.severity
        installed_job.local_severity = local_severity
        installed_job.save()

    def _physical_set_severity(self, severity, local_severity):
        job_name = 'rsyslog_job'
        rsyslog = InfosInstalledJob(self.address, job_name)
        rsyslog_installed = rsyslog.get_installed_job_or_not_found_error()

        # Configure the playbook
        transfer_id = next(IDGenerator())
        agent = rsyslog_installed.agent
        syslogseverity = convert_severity(int(severity))
        syslogseverity_local = convert_severity(int(local_severity))

        # Prepare the start_job_instance associated action
        arguments = {
                'disable_code': sum(
                    (severity == 8) << i for i, severity in
                    enumerate((syslogseverity, syslogseverity_local))),
                'transfered_file_id': transfer_id,
                'job_name': self.name,
        }

        # Launch the playbook and the associated job
        start_playbook(
                'enable_logs',
                agent.address,
                agent.collector.json,
                job=self.name,
                transfer_id=transfer_id,
                severity=syslogseverity,
                local_severity=syslogseverity_local)
        rsyslog_instance = StartJobInstance(self.address, job_name, arguments, self.date)
        rsyslog_instance.openbach_function_instance = self.openbach_function_instance
        rsyslog_instance._build_job_instance()
        rsyslog_instance._threaded_action(rsyslog_instance._action)


class SetStatisticsPolicyJob(OpenbachFunctionMixin, ThreadedAction, InstalledJobAction):
    """Action responsible for changing the log severity of an Installed Job"""

    def __init__(self, address, name, storage=None,
                 broadcast=None, stat_name=None, date=None):
        super().__init__(address=address, name=name, storage=storage,
                         broadcast=broadcast, statistic=stat_name, date=date)

    def _create_command_result(self):
        command_result, _ = InstalledJobCommandResult.objects.get_or_create(
                agent_ip=self.address, job_name=self.name)
        return self.set_running(command_result, 'status_stat_policy')

    def _action(self):
        installed_job = self.get_installed_job_or_not_found_error()
        storage = self.storage
        broadcast = self.broadcast

        if self.statistic is None:
            if broadcast is not None:
                installed_job.default_stat_broadcast = broadcast
            if storage is not None:
                installed_job.default_stat_storage = storage
            installed_job.save()
        else:
            try:
                statistic = installed_job.job.statistics.get(name=self.statistic)
            except Statistic.DoesNotExist:
                raise errors.NotFoundError(
                        'The statistic is not generated by the Job',
                        statistic_name=self.statistic,
                        job_name=self.name)
            statistic_instance, _ = StatisticInstance.objects.get_or_create(
                    job=installed_job, stat=statistic)
            if storage is None and broadcast is None:
                statistic_instance.delete()
            else:
                if broadcast is not None:
                    statistic_instance.broadcast = broadcast
                if storage is not None:
                    statistic_instance.storage = storage
                statistic_instance.save()

        self._physical_set_policy(storage, broadcast, installed_job)

    def _physical_set_policy(self, storage, broadcast, installed_job):
        job_name = 'rstats_job'
        rstats = InfosInstalledJob(self.address, 'rstats_job')
        rstats_installed = rstats.get_installed_job_or_not_found_error()
        # Create the new stats policy file
        with open('/tmp/openbach_rstats_filter', 'w') as rstats_filter:
            print('[default]', file=rstats_filter)
            print('storage =', installed_job.default_stat_storage, file=rstats_filter)
            print('broadcast =', installed_job.default_stat_broadcast, file=rstats_filter)
            for stat in installed_job.statistics.all():
                print('[{}]'.format(stat.stat.name), file=rstats_filter)
                print('storage =', stat.storage, file=rstats_filter)
                print('broadcast =', stat.broadcast, file=rstats_filter)

        # Prepare the start_job_instance associated action
        transfer_id = next(IDGenerator())
        arguments = {
            'transfered_file_id': transfer_id,
            'job_name': self.name,
        }

        # Launch the playbook and the associated job
        start_playbook(
                'push_file',
                rstats_installed.agent.address,
                rstats_filter.name,
                '/opt/openbach/agent/jobs/{0}/{0}'
                '{1}_rstats_filter.conf.locked'
                .format(self.name, transfer_id))
        rstats_instance = StartJobInstance(self.address, job_name, arguments, self.date)
        rstats_instance.openbach_function_instance = self.openbach_function_instance
        rstats_instance._build_job_instance()
        rstats_instance._threaded_action(rstats_instance._action)


###############
# JobInstance #
###############

class JobInstanceAction(ConductorAction):
    """Base class that defines helper methods to deal with JobInstances"""

    def get_job_instance_or_not_found_error(self):
        try:
            job_instance_id = self.instance_id
        except AttributeError:
            raise errors.ConductorError(
                    'The JobInstance handler did not store the required '
                    'job instance id for the required job',
                    job_name=self.name, agent_address=self.address)
        try:
            return JobInstance.objects.get(id=job_instance_id)
        except JobInstance.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Job Instance is not in the database',
                    job_instance_id=self.instance_id)


class StartJobInstance(OpenbachFunctionMixin, ThreadedAction, JobInstanceAction):
    """Action responsible for launching a Job on an Agent"""

    def __init__(self, address, name, arguments, date=None, interval=None, offset=0):
        super().__init__(address=address, name=name, arguments=arguments,
                         date=date, interval=interval, offset=offset)

    def _create_command_result(self):
        command_result, _ = JobInstanceCommandResult.objects.get_or_create(job_instance_id=self.instance_id)
        return self.set_running(command_result, 'status_start')

    def openbach_function(self, openbach_function_instance, waiters):
        date = self.offset * 1000
        if self.date is None:
            date += int(timezone.now().timestamp() * 1000)
        else:
            date += self.date

        self.openbach_function_instance = openbach_function_instance
        self._build_job_instance(date)

        scenario = openbach_function_instance.scenario_instance
        WatchJobInstance(self.instance_id, interval=2).action()
        WaitingQueueManager().add_job(
                self.instance_id,
                scenario.id,
                openbach_function_instance.instance_id,
                waiters)
        StatusManager().add(scenario.id, self.instance_id)
        return []

    def action(self):
        """Override the base threaded action handler to build the JobInstance
        first and store its ID in this object instance before launching it.
        """
        self._build_job_instance()
        super().action()
        return {'job_instance_id': self.instance_id}, 202

    def _build_job_instance(self, date=None):
        """Construct the JobInstance in the database and store its ID
        in this object instance. The Job Instance will be retrieved and
        started latter in regular action handling.
        """
        if date is None:
            date = self.date

        installed_infos = InfosInstalledJob(self.address, self.name)
        installed_job = installed_infos.get_installed_job_or_not_found_error()

        now = timezone.now()
        job_instance = JobInstance.objects.create(
                job=installed_job,
                status='Scheduled',
                update_status=now,
                start_date=now,
                periodic=False)
        ofi = self.openbach_function_instance
        if ofi is not None:
            job_instance.openbach_function_instance = ofi
        try:
            job_instance.configure(self.arguments, date, self.interval)
        except (KeyError, ValueError) as err:
            job_instance.delete()
            raise errors.BadRequestError(
                    'An error occured when configuring the JobInstance',
                    job_name=self.name, agent_address=self.address,
                    arguments=self.arguments, error_message=str(err))
        else:
            job_instance.save()
        self.instance_id = job_instance.id

    def _action(self):
        job_instance = self.get_job_instance_or_not_found_error()
        scenario_id = job_instance.scenario_id
        owner_id = get_master_scenario_id(scenario_id)
        date = job_instance.start_timestamp if self.interval is None else None
        arguments = job_instance.arguments

        try:
            OpenBachBaton(self.address).start_job_instance(
                    self.name, job_instance.id,
                    scenario_id, owner_id,
                    arguments, date, self.interval)
        except errors.ConductorError:
            job_instance.delete()
            raise

        job_instance.set_status('Running')
        job_instance.save()


class StopJobInstance(OpenbachFunctionMixin, ThreadedAction, JobInstanceAction):
    """Action responsible for stopping a launched Job"""

    def __init__(self, instance_id=None, date=None, openbach_function_id=None):
        super().__init__(instance_id=instance_id, date=date,
                         openbach_function_id=openbach_function_id)

    def openbach_function(self, openbach_function_instance):
        """Retrieve the job instance id launched by the provided
        openbach function id and store it in the instance.
        """
        scenario = openbach_function_instance.scenario_instance
        try:
            openbach_function_to_stop = scenario.instances.get(id=self.openbach_function_id)
        except OpenbachFunctionInstance.DoesNotExist:
            raise errors.NotFoundError(
                    'The provided Openbach Function Instance is '
                    'not found in the database for the given Scenario',
                    openbach_function_id=self.openbach_function_id,
                    scenario_name=scenario.scenario.name)

        start_job_instance = openbach_function_to_stop.get_content_type()
        try:
            self.instance_id = start_job_instance.started_job.id
        except JobInstance.DoesNotExist:
            raise errors.NotFoundError(
                    'The provided Openbach Function Instance is '
                    'not associated to a launched job',
                    openbach_function_id=self.openbach_function_id,
                    openbach_function_name=openbach_function_to_stop.name)
        return super().openbach_function(openbach_function_instance)

    def _create_command_result(self):
        command_result, _ = JobInstanceCommandResult.objects.get_or_create(job_instance_id=self.instance_id)
        return self.set_running(command_result, 'status_stop')

    def _action(self):
        job_instance = self.get_job_instance_or_not_found_error()
        if job_instance.is_stopped:
            raise errors.ConductorWarning(
                    'The required JobInstance is already stopped',
                    job_instance_id=self.instance_id,
                    job_name=job_instance.job.job.name)

        if self.date is None:
            date = 'now'
            stop_date = timezone.now()
        else:
            date = self.date
            tz = timezone.get_current_timezone()
            stop_date = datetime.fromtimestamp(date / 1000, tz=tz)
        job = job_instance.job.job
        agent = job_instance.job.agent

        OpenBachBaton(agent.address).stop_job_instance(job.name, self.instance_id, date)
        job_instance.stop_date = stop_date
        job_instance.save()


class StopJobInstances(OpenbachFunctionMixin, ConductorAction):
    """Action responsible for stopping several launched Job"""

    def __init__(self, instance_ids=None, date=None, openbach_function_ids=None):
        super().__init__(instance_ids=instance_ids, date=date,
                         openbach_function_ids=openbach_function_ids)

    def openbach_function(self, openbach_function_instance):
        issues = []
        has_error = False
        for stop_id in self.openbach_function_ids:
            try:
                stop_job = StopJobInstance(date=self.date, openbach_function_id=stop_id)
                stop_job.openbach_function(openbach_function_instance)
            except errors.ConductorWarning as e:
                issues.append(e.json)
            except errors.ConductorError as e:
                issues.append(e.json)
                has_error = True
        if has_error:
            raise errors.ConductorError(
                    'Stopping one or more JobInstance produced an error',
                    errors=issues)
        elif issues:
            raise errors.ConductorWarning(
                    'Stopping one or more JobInstance produced an error',
                    warnings=issues)
        return []

    def _action(self):
        for instance_id in self.instance_ids:
            StopJobInstance(instance_id, self.date).action()
        return {}, 202


class RestartJobInstance(OpenbachFunctionMixin, ThreadedAction, JobInstanceAction):
    """Action responsible for restarting a launched Job"""

    def __init__(self, instance_id, arguments, date=None, interval=None):
        super().__init__(instance_id=instance_id, arguments=arguments,
                         date=date, interval=interval)

    def _create_command_result(self):
        command_result, _ = JobInstanceCommandResult.objects.get_or_create(job_instance_id=self.instance_id)
        return self.set_running(command_result, 'status_restart')

    def _action(self):
        job_instance = self.get_job_instance_or_not_found_error()
        with db.transaction.atomic():
            try:
                job_instance.configure(self.arguments, self.date, self.interval)
            except (KeyError, ValueError) as err:
                raise errors.BadRequestError(
                        'An error occured when reconfiguring the JobInstance',
                        job_name=self.name, agent_address=self.address,
                        job_instance_id=self.instance_id,
                        arguments=self.arguments, error_message=str(err))
            ofi = self.openbach_function_instance
            if ofi is not None:
                job_instance.openbach_function_instance = ofi
            job_instance.save()

        job = job_instance.job.job
        agent = job_instance.job.agent
        try:
            OpenBachBaton(agent.address).restart_job_instance(
                    job.name, self.instance_id,
                    job_instance.scenario_id,
                    job_instance.arguments,
                    self.date, self.interval)
        except errors.ConductorError:
            job_instance.delete()
            raise
        job_instance.set_status('Running')
        job_instance.is_stopped = False
        job_instance.save()


class WatchJobInstance(OpenbachFunctionMixin, ThreadedAction, JobInstanceAction):
    """Action responsible for managing Watches on a JobInstance"""

    def __init__(self, instance_id, date=None, interval=None, stop=None):
        super().__init__(instance_id=instance_id, date=date, interval=interval, stop=stop)

    def _create_command_result(self):
        command_result, _ = JobInstanceCommandResult.objects.get_or_create(job_instance_id=self.instance_id)
        return self.set_running(command_result, 'status_watch')

    def _action(self):
        job_instance = self.get_job_instance_or_not_found_error()
        watch, created = Watch.objects.get_or_create(job_instance=job_instance)
        if not created and self.interval is None and self.stop is None:
            raise errors.BadRequestError(
                    'A Watch already exists in the database',
                    job_instance_id=self.instance_id,
                    job_name=job_instance.job.job.name,
                    agent_address=job_instance.job.agent.address)

        if self.interval is not None:
            watch.interval = self.interval
            watch.save()
        date = self.date
        if date is None and self.interval is None and self.stop is None:
            date = 'now'

        # Configure the playbook
        job = job_instance.job.job
        agent = job_instance.job.agent
        try:
            OpenBachBaton(agent.address).status_job_instance(
                    job.name, self.instance_id,
                    date, self.interval, self.stop)
        except errors.ConductorError:
            watch.delete()
            raise

        if self.interval is None:
            # Do not keep one-shot or stopped watches
            watch.delete()


class StatusJobInstance(OpenbachFunctionMixin, JobInstanceAction):
    """Action responsible for retrieving the status of a JobInstance"""
    UPDATE_INSTANCE_URL = (
            'http://{agent.collector.address}:{agent.collector.stats_query_port}/query?'
            'db={agent.collector.stats_database_name}&'
            'epoch={agent.collector.stats_database_precision}&'
            'q=SELECT+last("status")+FROM+"openbach_agent"+'
            'WHERE+"@agent_name"+=+\'{agent.name}\'+'
            'AND+job_name+=+\'{}\'+AND+job_instance_id+=+{}')

    def __init__(self, instance_id, update=False):
        super().__init__(instance_id=instance_id, update=update)

    def _action(self):
        job_instance = self.get_job_instance_or_not_found_error()

        status = {}
        # TODO better update
        if self.update:
            url = self.UPDATE_INSTANCE_URL.format(
                    job_instance.job.job.name,
                    self.instance_id,
                    agent=job_instance.job.agent)
            result = requests.get(url).json()
            try:
                serie = result['results'][0]['series'][0]
                columns = serie['columns']
                values = serie['values'][0]
            except LookupError:
                status['error'] = {
                        'message': 'Cannot retrieve the job '
                        'instance status in the Collector',
                        'collector_response': result,
                }
            else:
                tz = timezone.get_current_timezone()
                for column, value in zip(columns, values):
                    if column == 'time':
                        date = datetime.fromtimestamp(value / 1000, tz=tz)
                    elif column == 'last':
                        status = value
                job_instance.update_status = date
                job_instance.status = status
                job_instance.save()

        status.update(job_instance.json)
        return status, 200


class ListJobInstance(JobInstanceAction):
    """Action responsible for listing the JobInstances running on an Agent"""

    def __init__(self, address, update=False):
        super().__init__(address=address, update=update)

    def _action(self):
        agent = InfosAgent(self.address).get_agent_or_not_found_error()
        jobs = [
                self._status_instances(installed_job)
                for installed_job in agent.installed_jobs.all()
        ]
        return {
                'address': self.address,
                'installed_jobs': jobs,
        }, 200

    def _status_instances(self, installed_job):
        status_instances = [
                StatusJobInstance(job_instance.id, self.update).action()[0]
                for job_instance in installed_job.instances.filter(is_stopped=False)
        ]
        return {
                'job_name': installed_job.job.name,
                'instances': status_instances,
        }


class ListJobInstances(OpenbachFunctionMixin, ConductorAction):
    """Action responsible for listing the JobInstances running on several Agents"""

    def __init__(self, addresses, update=False):
        super().__init__(addresses=addresses, update=update)

    def _action(self):
        instances = [
                ListJobInstance(address, self.update).action()[0]
                for address in self.addresses
        ]
        return {'instances': instances}, 202


############
# Scenario #
############

class ScenarioAction(ConductorAction):
    """Base class that defines helper methods to deal with Scenarios"""

    def get_scenario_or_not_found_error(self):
        project = InfosProject(self.project).get_project_or_not_found_error()

        try:
            return Scenario.objects.get(name=self.name, project=project)
        except Scenario.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Scenario is not in the database',
                    scenario_name=self.name,
                    project_name=self.project)

    def _register_scenario(self):
        description = self.json_data.get('description')
        project = InfosProject(self.project).get_project_or_not_found_error()
        scenario, _ = Scenario.objects.get_or_create(
                name=self.name, project=project,
                defaults={'description': description})
        scenario.description = description
        scenario.save()
        try:
            scenario.load_from_json(self.json_data)
        except Scenario.MalformedError as e:
            scenario.delete()
            raise errors.BadRequestError(
                    'Data of the Scenario are malformed',
                    scenario_name=self.name,
                    error_message=e.error,
                    scenario_data=self.json_data)
        else:
            scenario.save()


class CreateScenario(ScenarioAction):
    """Action responsible for creating a new Scenario"""

    def __init__(self, json_data, project=None):
        name = extract_and_check_name_from_json(json_data, kind='Scenario')
        super().__init__(json_data=json_data, name=name, project=project)

    def _action(self):
        self._register_scenario()
        scenario = self.get_scenario_or_not_found_error()
        return scenario.json, 200


class DeleteScenario(ScenarioAction):
    """Action responsible for deleting an existing Scenario"""

    def __init__(self, name, project=None):
        super().__init__(name=name, project=project)

    def _action(self):
        scenario = self.get_scenario_or_not_found_error()
        scenario.delete()
        return None, 204


class ModifyScenario(ScenarioAction):
    """Action responsible for modifying an existing Scenario"""

    def __init__(self, json_data, name, project=None):
        super().__init__(json_data=json_data, name=name, project=project)

    def _action(self):
        extract_and_check_name_from_json(self.json_data, self.name, kind='Scenario')
        with db.transaction.atomic():
            self._register_scenario()
        scenario = self.get_scenario_or_not_found_error()
        return scenario.json, 200


class InfosScenario(ScenarioAction):
    """Action responsible for information retrieval about a Scenario"""

    def __init__(self, name, project=None):
        super().__init__(name=name, project=project)

    def _action(self):
        scenario = self.get_scenario_or_not_found_error()
        return scenario.json, 200


class ListScenarios(ScenarioAction):
    """Action responsible for information retrieval about all Scenarios"""

    def __init__(self, project=None):
        super().__init__(project=project)

    def _action(self):
        project = InfosProject(self.project).get_project_or_not_found_error()
        scenarios = Scenario.objects.filter(project=project)
        return [scenario.json for scenario in scenarios], 200


####################
# ScenarioInstance #
####################

class ScenarioInstanceAction(ConductorAction):
    """Base class that defines helper methods to deal with ScenarioInstances"""

    def get_scenario_instance_or_not_found_errror(self):
        try:
            scenario_instance_id = self.instance_id
        except AttributeError:
            raise errors.ConductorError(
                    'The ScenarioInstance handler did not store the required '
                    'scenario instance id for the required scenario',
                    scenario_name=self.name, project_name=self.project)
        try:
            return ScenarioInstance.objects.get(id=scenario_instance_id)
        except ScenarioInstance.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Scenario Instance is not in the database',
                    scenario_instance_id=self.instance_id)


class StartScenarioInstance(OpenbachFunctionMixin, ScenarioInstanceAction):
    """Action responsible of launching new Scenario Instances"""

    def __init__(self, name, project=None, arguments=None, date=None):
        super().__init__(name=name, project=project, arguments=arguments, date=date)

    def openbach_function(self, openbach_function_instance):
        launching_project = openbach_function_instance.scenario_instance.scenario.project
        project = None if launching_project is None else launching_project.name
        if project != self.project and self.project is not None:
            raise errors.BadRequestError(
                    'Trying to start a ScenarioInstance using '
                    'an OpenbachFunction of an other Project.',
                    scenario_name=self.name,
                    project_name=self.project,
                    used_project_name=project)
        else:
            self.project = project
        super().openbach_function(openbach_function_instance)
        scenario_id = self.openbach_function_instance.started_scenario.id
        return [ThreadManager().get_status_thread(scenario_id)]

    def _action(self):
        scenario = InfosScenario(self.name, self.project).get_scenario_or_not_found_error()
        scenario_instance = ScenarioInstance.objects.create(
                scenario=scenario,
                status='Scheduling',
                start_date=timezone.now(),
                openbach_function_instance=self.openbach_function_instance)
        self.instance_id = scenario_instance.id

        # Populate values for ScenarioArguments
        for argument, value in self.arguments:
            try:
                argument_instance = ScenarioArgument.objects.get(name=argument, scenario=scenario)
            except ScenarioArgument.DoesNotExist:
                raise errors.BadRequestError(
                        'A value was provided for an Argument that '
                        'is not defined for this Scenario.',
                        scenario_name=self.name,
                        project_name=self.project,
                        argument_name=argument)
            ScenarioArgumentValue.objects.create(
                    value=value, argument=argument_instance,
                    scenario_instance=scenario_instance)

        # Create instances for each OpenbachFunction of this Scenario
        # and check that the values of the arguments fit
        for openbach_function in scenario.openbach_functions.all():
            openbach_function_instance = OpenbachFunctionInstance.objects.create(
                    openbach_function=openbach_function,
                    scenario_instance=scenario_instance)
            try:
                openbach_function_instance.check_arguments.type()
            except ValidationError as e:
                raise errors.BadRequestError(
                        'Arguments of an OpenbachFunction have '
                        'the wrong type of arguments.',
                        openbach_function_name=openbach_function.name,
                        error_message=str(e))

        # Build a table of communication queues and wait IDs
        functions_table = {}
        openbach_functions_instances = scenario_instance.openbach_functions_instances.all()
        for openbach_function in openbach_functions_instances:
            functions_table[openbach_function.id] = {
                    'queue': queue.Queue(),
                    'is_waited_for_launch': set(get_waited(
                        openbach_function.openbach_function.launched_waiters.all(),
                        scenario_instance)),
                    'is_waited_for_finish': set(get_waited(
                        openbach_function.openbach_function.finished_waiters.all(),
                        scenario_instance)),
                    'is_waited_true_condition': set(),
                    'is_waited_false_condition': set(),
            }

        # Populate wait IDs for If and While OpenbachFunctions
        parameters = scenario_instance.parameters
        for openbach_function in openbach_functions_instances:
            function = openbach_function.openbach_function.get_content_model()
            true_ids, false_ids = [], []
            with suppress(AttributeError):
                # Test If OpenbachFunction
                true_ids.extend(function.instance_value('function_true', parameters))
                false_ids.extend(function.instance_value('function_false', parameters))
            with suppress(AttributeError):
                # Test While OpenbachFunction
                true_ids.extend(function.instance_value('function_while', parameters))
                false_ids.extend(function.instance_value('function_end', parameters))
            id_ = openbach_function.id
            for waiting_id in true_ids:
                functions_table[waiting_id]['is_waited_true_condition'].add(id_)
            for waiting_id in false_ids:
                functions_table[waiting_id]['is_waited_false_condition'].add(id_)

        # Start all OpenbachFunctions threads
        threads = [
                create_thread(openbach_function, functions_table)
                for openbach_function in openbach_functions_instances
        ]
        for thread in threads:
            ThreadManager().add_and_launch(thread, self.instance_id, thread.instance_id)

        # Start the scenario's status thread
        thread = WaitScenarioToFinish(self.instance_id, threads)
        ThreadManager().add_and_launch(thread, self.instance_id, 0)
        return {'scenario_instance_id': self.instance_id}, 200


class StopScenarioInstance(OpenbachFunctionMixin, ScenarioInstanceAction):
    """Action responsible of stopping an existing Scenario Instance"""

    def __init__(self, instance_id, date=None):
        super().__init__(instance_id=instance_id, date=date)

    def _action(self):
        scenario_instance = self.get_scenario_instance_or_not_found_errror()
        if not scenario_instance.is_stopped:
            scenario_instance.stop()
            try:
                ThreadManager().stop(self.instance_id)
            except KeyError:
                scenario_instance.status = 'Stopped, out of controll'
                scenario_instance.save()
            for openbach_function in scenario_instance.openbach_functions_instances.all():
                with suppress(JobInstance.DoesNotExist):
                    job_instance = openbach_function.started_job
                    StopJobInstance(job_instance.id).action()
                with suppress(ScenarioInstance.DoesNotExist):
                    subscenario_instance = openbach_function.started_scenario
                    StopScenarioInstance(subscenario_instance.id).action()
        return None, 204


class InfosScenarioInstance(ScenarioInstanceAction):
    """Action responsible for information retrieval about a ScenarioInstance"""

    def __init__(self, instance_id):
        super().__init__(instance_id=instance_id)

    def _action(self):
        scenario_instance = self.get_scenario_instance_or_not_found_errror()
        return scenario_instance.json, 200


class ListScenarioInstances(ScenarioInstanceAction):
    """Action responsible for information retrieval about all
    ScenarioInstances of a given Scenario.
    """

    def __init__(self, name=None, project=None):
        super().__init__(name=name, project=project)

    def _action(self):
        if self.name is not None:
            scenario_info = InfosScenario(self.name, self.project)
            scenario = scenario_info.get_scenario_or_not_found_error()
            instances = [
                    instance.json for instance in
                    scenario.instances.order_by('-start_date')
            ]
            return instances, 200
        project = InfosProject(self.project).get_project_or_not_found_error()
        scenarios = Scenario.objects.prefetch_related('instances').filter(project=project)
        instances = [
                instance.json for scenario in scenarios
                for instance in scenario.instances.order_by('-start_date')
        ]
        return instances, 200


############################
# OpenbachFunctionInstance #
############################

def get_waited(waiters, scenario_instance):
    for waiter in waiters:
        waited = waiter.openbach_function_waited
        try:
            openbach_function_instance = OpenbachFunctionInstance.objects.get(
                openbach_function=waited,
                scenario_instance=scenario_instance)
        except OpenbachFunctionInstance.DoesNotExist:
            raise errors.BadRequestError(
                    'An OpenbachFunction of this Scenario is waited '
                    'but no instance of this OpenbachFunction is '
                    'planned for this ScenarioInstance.',
                    scenario_name=scenario_instance.scenario.name,
                    scenario_instance_id=scenario_instance.id,
                    openbach_function_name=waited.name)
        yield openbach_function_instance.id


def create_thread(openbach_function, functions_table):
    openbach_function_model = openbach_function.openbach_function.get_content_model()
    openbach_function_name = openbach_function_model.__class__.__name__
    if openbach_function_name == 'If':
        return IfThread(openbach_function, functions_table)
    if openbach_function_name == 'While':
        return WhileThread(openbach_function, functions_table)
    return OpenbachFunctionThread(openbach_function, functions_table)


class WaitScenarioToFinish(threading.Thread):
    def __init__(self, instance_id, openbach_function_threads):
        super().__init__()
        self.instance_id = instance_id
        self.threads = openbach_function_threads

    def run(self):
        for thread in self.threads:
            thread.join()

        scenario = InfosScenarioInstance(self.instance_id)
        if scenario.is_stopped:
            return

        # Check that all sub-scenarios and all launched job instances
        # are stopped as well
        for openbach_function in scenario.openbach_functions_instances.all():
            with suppress(JobInstance.DoesNotExist):
                job_instance = openbach_function.started_job
                if not job_instance.is_stopped:
                    break
            with suppress(ScenarioInstance.DoesNotExist):
                subscenario_instance = openbach_function.started_scenario
                if not subscenario_instance.is_stopped:
                    break
        else:  # No break
            scenario.stop()
            scenario.status = 'Finished OK'
            scenario.save()
            return

        scenario.status = 'Running'
        scenario.save()


class OpenbachFunctionThread(threading.Thread):
    def __init__(self, openbach_function_instance, table):
        super().__init__()
        self._table = table
        self._stop = threading.Event()

        openbach_function = openbach_function_instance.openbach_function
        action_name = openbach_function.get_content_model().__class__.__name__
        try:
            self.action = globals()[action_name]
        except KeyError:
            raise errors.ConductorError(
                    'An OpenbachFunction is not implemented',
                    openbach_function_name=openbach_function.name)
        if not hasattr(self.action, 'openbach_function'):
            raise errors.ConductorError(
                    'An Action is not available as OpenbachFunction',
                    action_name=openbach_function.name)
        self.instance_id = openbach_function_instance.id
        self.openbach_function = openbach_function_instance
        own_table = table[self.instance_id]
        self.queue = own_table['queue']
        self.waited_ids = (
                own_table['is_waited_for_launch'] |
                own_table['is_waited_for_finish'] |
                own_table['is_waited_true_condition'] |
                own_table['is_waited_false_condition'])
        self.wait_for_launch_queues = [
                table[id]['queue'] for id, data in table.items()
                if self.instance_id in data['is_waited_for_launch']
        ]
        self.wait_for_finished_queues = [
                table[id]['queue'] for id, data in table.items()
                if self.instance_id in data['is_waited_for_finished']
        ]

    def run(self):
        while self.waited_ids:
            try:
                id_ = self.queue.get(timeout=.5)
            except queue.Empty:
                if self._stopped.is_set():
                    self.openbach_function.set_status('Stopped')
                    return
            else:
                if id_ is None:
                    # We were waiting on a condition
                    # and the path is not taken
                    return
                self.waited_ids.remove(id_)
        time.sleep(self.openbach_function.wait_time)
        try:
            threads = self._run_openbach_function()
        except errors.ConductorWarning:
            pass
        except errors.ConductorError as error:
            scenario_id = self.openbach_function.scenario_instance.id
            StopScenarioInstance(scenario_id).action()
            self.openbach_function.scenario_instance.stop(stop_status='Finished KO')
            self.openbach_function.set_status('Error: {}'.format(error))
            return

        if self._stopped.is_set():
            self.openbach_function.set_status('Stopped')
            return

        self.openbach_function.set_status('Finished')
        for waiter_queue in self.wait_for_launch_queues:
            waiter_queue.put(self.instance_id)

        for thread in threads:
            thread.join()

    def _run_openbach_function(self):
        self.openbach_function.start()
        arguments = self.openbach_function.arguments
        # try:
        action = self.action(**arguments)
        if self.action == StartJobInstance:
            return action.openbach_function(
                    self.openbach_function,
                    self.wait_for_finished_queues)
        else:
            return action.openbach_function(self.openbach_function)
        # except TypeError:
        #     ??? TODO

    def stop(self):
        self._stopped.set()


class IfThread(OpenbachFunctionThread):
    def _run_openbach_function(self):
        instance_id = self.instance_id
        scenario = self.openbach_function.scenario_instance
        arguments = self.openbach_function.arguments
        condition = arguments['condition']
        condition_value = condition.get_value(scenario.id, scenario.parameters)
        id_queue, none_queue = sorted(('on_false', 'on_true'), reverse=condition_value)
        for id in arguments[id_queue]:
            self._table[id]['queue'].put(instance_id)
        for id in arguments[none_queue]:
            self._table[id]['queue'].put(None)
        return []


class WhileThread(OpenbachFunctionThread):
    def _run_openbach_function(self):
        instance_id = self.instance_id
        scenario = self.openbach_function.scenario_instance
        arguments = self.openbach_function.arguments
        condition = arguments['condition']
        on_true_ids = arguments['on_true']
        on_true = [self._table[id]['queue'] for id in on_true_ids]
        while condition.get_value(scenario.id, scenario.parameters):
            for waiting_queue in on_true:
                waiting_queue.put(instance_id)
            for thread in ThreadManager().get_threads(scenario.id, on_true_ids):
                thread.join()
                # TODO wait for JobInstances to stop
                table = {
                        thread.instance_id: {
                            'queue': thread.queue,
                            'is_waited_for_launch': set(),
                            'is_waited_for_finish': set(),
                            'is_waited_true_condition': {instance_id},
                            'is_waited_false_condition': set(),
                        },
                }
                new_thread = create_thread(thread.openbach_function, table)
                ThreadManager().add_and_launch(new_thread, scenario.id, new_thread.instance_id)
        for waiting_queue in on_true:
            waiting_queue.put(None)
        for id in arguments['on_false']:
            self._table[id]['queue'].put(instance_id)
        return ThreadManager().get_threads(scenario.id, on_true_ids)


###########
# Project #
###########

class ProjectAction(ConductorAction):
    """Base class that defines helper methods to deal with Projects"""

    def get_project_or_not_found_error(self):
        try:
            return Project.objects.get(name=self.name)
        except Project.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Project is not in the database',
                    project_name=self.name)

    def _register_project(self):
        description = self.json_data.get('description')
        project, _ = Project.objects.get_or_create(name=self.name)
        project.description = description
        project.save()
        try:
            project.load_from_json(self.json_data)
        except Project.MalformedError as e:
            project.delete()
            raise errors.BadRequestError(
                    'Data of the Project are malformed',
                    project_name=self.name,
                    error_message=e.error,
                    project_data=self.json_data)
        else:
            project.save()


class CreateProject(ProjectAction):
    """Action responsible for creating a new Project"""

    def __init__(self, json_data):
        name = extract_and_check_name_from_json(json_data, kind='Project')
        super().__init__(name=name, json_data=json_data)

    def _action(self):
        self._register_project()
        project = self.get_project_or_not_found_error()
        return project.json, 200


class DeleteProject(ProjectAction):
    """Action responsible for deleting an existing Project"""

    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        project = self.get_project_or_not_found_error()
        project.delete()
        return None, 204


class ModifyProject(ProjectAction):
    """Action responsible for modifying an existing Project"""

    def __init__(self, name, json_data):
        super().__init__(name=name, json_data=json_data)

    def _action(self):
        extract_and_check_name_from_json(self.json_data, self.name, kind='Project')
        with db.transaction.atomic():
            self._register_project()
        project = self.get_project_or_not_found_error()
        return project.json, 200


class InfosProject(ProjectAction):
    """Action responsible for information retrieval about a Project"""

    def __init__(self, name):
        super().__init__(name=name)

    def get_project_or_not_found_error(self):
        if self.name is None:
            return None
        return super().get_project_or_not_found_error()

    def _action(self):
        project = self.get_project_or_not_found_error()
        return project.json, 200


class ListProjects(ProjectAction):
    """Action responsible for information retrieval about all Projects"""

    def __init__(self):
        super().__init__()

    def _action(self):
        return [project.json for project in Project.objects.all()], 200


##########
# Entity #
##########

class EntityAction(ConductorAction):
    """Base class that defines helper methods to deal with Entities"""

    def get_entity_or_not_found_error(self):
        project = InfosProject(self.project).get_project_or_not_found_error()
        try:
            return Entity.objects.get(name=self.name, project=project)
        except Entity.DoesNotExist:
            raise errors.NotFoundError(
                    'The requested Entity is not in the database',
                    project_name=self.project, entity_name=self.entity)

    def _register_entity(self):
        project = InfosProject(self.project).get_project_or_not_found_error()
        description = self.json_data.get('description')
        agent = self.json_data.get('agent', {})
        if agent:
            address = agent.get('address')
            agent = InfosAgent(address).get_agent_or_not_found_error()
        networks = self.json_data.get('networks', [])
        if not isinstance(networks, list):
            raise errors.BadRequestError(
                    'The networks of an entity should be a list of network names')

        entity, _ = Entity.objects.get_or_create(name=self.name, project=project)
        entity.description = description
        entity.agent = agent
        entity.save()

        entity.networks.clear()
        for network in networks:
            try:
                entity_network = Network.objects.get(name=network, project=project)
            except Network.DoesNotExist:
                raise errors.NotFoundError(
                        'The requested Network is not in the database',
                        project_name=self.project, network_name=network)
            else:
                entity.networks.add(entity_network)


class AddEntity(EntityAction):
    """Action responsible for creating a new Entity"""

    def __init__(self, project, json_data):
        name = extract_and_check_name_from_json(json_data, kind='Entity')
        super().__init__(
                name=name, project=project,
                json_data=json_data)

    def _action(self):
        self._register_entity()
        entity = self.get_entity_or_not_found_error()
        return entity.json, 200


class ModifyEntity(EntityAction):
    """Action responsible for modifying an existing Entity"""

    def __init__(self, name, project, json_data):
        super().__init__(
                name=name, project=project,
                json_data=json_data)

    def _action(self):
        extract_and_check_name_from_json(self.json_data, self.name, kind='Entity')
        with db.transaction.atomic():
            self._register_entity()
        entity = self.get_entity_or_not_found_error()
        return entity.json, 200


class DeleteEntity(EntityAction):
    """Action responsible for deleting an existing Entity"""

    def __init__(self, name, project):
        super().__init__(name=name, project=project)

    def _action(self):
        entity = self.get_entity_or_not_found_error()
        entity.delete()
        return None, 204


class InfosEntity(EntityAction):
    """Action responsible for information retrieval about an Entity"""

    def __init__(self, name, project):
        super().__init__(name=name, project=project)

    def _action(self):
        entity = self.get_entity_or_not_found_error()
        return entity.json, 200


class ListEntities(EntityAction):
    """Action responsible for information retrieval about all Entities"""

    def __init__(self, project):
        super().__init__(project=project)

    def _action(self):
        project = InfosProject(self.project).get_project_or_not_found_error()
        entities = Entity.objects.filter(project=project)
        return [entity.json for entity in entities], 200


#########
# State #
#########

class StateCollector(ConductorAction):
    """Action that retrieve the last action done on a Collector"""

    def __init__(self, address):
        super().__init__(address=address)

    def _action(self):
        command_result, _ = CollectorCommandResult.objects.get_or_create(address=self.address)
        return command_result.json, 200


class StateAgent(ConductorAction):
    """Action that retrieve the last action done on a Agent"""

    def __init__(self, address):
        super().__init__(address=address)

    def _action(self):
        command_result, _ = AgentCommandResult.objects.get_or_create(address=self.address)
        return command_result.json, 200


class StateJob(ConductorAction):
    """Action that retrieve the last action done on an Installed Job"""

    def __init__(self, address, name):
        super().__init__(address=address, name=name)

    def _action(self):
        command_result, _ = InstalledJobCommandResult.objects.get_or_create(
                agent_ip=self.address,
                job_name=self.name)
        return command_result.json, 200


class StatePushFile(ConductorAction):
    """Action that retrieve the last action done on a Pushed File"""

    def __init__(self, name, path, address):
        super().__init__(name=name, path=path, address=address)

    def _action(self):
        command_result, _ = FileCommandResult.objects.get_or_create(
                filename=self.name,
                remote_path=self.path,
                address=self.address)
        return command_result.json, 200


class StateJobInstance(ConductorAction):
    """Action that retrieve the last action done on a JobInstance"""

    def __init__(self, instance_id):
        super().__init__(instance_id=instance_id)

    def _action(self):
        command_result, _ = JobInstanceCommandResult.objects.get_or_create(job_instance_id=self.instance_id)
        return command_result.json, 200


################
# Miscelaneous #
################

class PushFile(OpenbachFunctionMixin, ThreadedAction):
    """Action that send a file from the Controller to an Agent"""

    def __init__(self, local_path, remote_path, address):
        super().__init__(local_path=local_path, remote_path=remote_path, address=address)

    def _create_command_result(self):
        command_result, _ = FileCommandResult.objects.get_or_create(
                filename=self.local_path,
                remote_path=self.remote_path,
                address=self.address)
        return command_result

    def _action(self):
        agent = InfosAgent(self.address).get_agent_or_not_found_error()
        start_playbook(
                'push_file',
                agent.address,
                self.local_path,
                self.remote_path)


class KillAll(ConductorAction):
    """Action that kills all instances: Scenarios, Jobs and Watches"""

    def __init__(self, date=None):
        super().__init__(date=date)

    def _action(self):
        for scenario in ScenarioInstance.objects.filter(is_stopped=False):
            StopScenarioInstance(scenario.id).action()

        for job in JobInstance.objects.filter(is_stopped=False):
            StopJobInstance(job.id).action()

        for watch in Watch.objects.all():
            WatchJobInstance(watch.job_instance.id, stop='now').action()

        return None, 204


########
# Main #
########

class ThreadManager:
    """Manage threads in which OpenBACH functions are being run"""
    __shared_state = {'_threads': defaultdict(dict), 'mutex': threading.Lock()}

    def __init__(self):
        """Implement the Borg pattern so any instance share the same state"""
        self.__dict__ = self.__class__.__shared_state

    def add_and_launch(self, thread, scenario_id, openbach_function_id):
        thread.do_run = True
        thread.start()
        with self.mutex:
            self._threads[scenario_id][openbach_function_id] = thread

    def get_status_thread(self, scenario_id):
        with self.mutex:
            return self._threads[scenario_id][0]

    def get_threads(self, scenario_id, threads_ids):
        with self.mutex:
            scenario_threads = self._threads[scenario_id]
            return [scenario_threads[id_] for id_ in threads_ids]

    def is_scenario_stopped(self, scenario_id):
        with self.mutex:
            try:
                thread = self._threads[scenario_id][0]
            except KeyError:
                return False

            if thread.is_alive():
                return False
            del self._threads[scenario_id]
            return True

    def stop(self, scenario_id):
        with self.mutex:
            threads = self._threads.pop(scenario_id)
            # Put back the status thread so we can check
            # later that it exited properly
            self._threads[scenario_id][0] = threads.pop(0)
        for openbach_function_id, thread in threads.items():
            thread.stop()


class WaitingQueueManager:
    """Manage communication between OpenBACH functions that are
    being run so any function can wait for any other to be
    launched or finished executing.
    """
    __shared_state = {'_waiting_queues': {}, 'mutex': threading.Lock()}

    def __init__(self):
        """Implement the Borg pattern so any instance share the same state"""
        self.__dict__ = self.__class__.__shared_state

    def add_job(self, job_id, scenario_id, function_id, queues):
        with self.mutex:
            self._waiting_queues[job_id] = (scenario_id, function_id, queues)

    def remove_job(self, job_id):
        with self.mutex:
            scenario_id, function_id, queues = self._waiting_queues.pop(job_id)
            for waited_queue in queues:
                # Alert other functions that this one is being finished
                waited_queue.put(function_id)
        return scenario_id


class StatusManager:
    __state = {
            'scenarios': {},
            '_mutex': threading.Lock(),
            'scheduler': None,
    }

    def __init__(self):
        """Implement the Borg pattern so any instance share the same state"""
        self.__dict__ = self.__class__.__state
        with self._mutex:
            if self.scheduler is None:
                self.scheduler = BackgroundScheduler()
                self.scheduler.start()

    def _stop_watch(self, job_id):
        with suppress(JobLookupError):
            self.scheduler.remove_job('watch_{}'.format(job_id))

    def remove(self, scenario_id, job_id):
        with self._mutex:
            jobs = self.scenarios.get(scenario_id, set())
            jobs.remove(job_id)
            self._stop_watch(job_id)

    def cancel(self, scenario_id):
        with self._mutex:
            jobs = self.scenarios.pop(scenario_id, set())
            for job_id in jobs:
                self._stop_watch(job_id)

    def add(self, scenario_id, job_id):
        with self._mutex:
            self.scenarios.setdefault(scenario_id, set()).add(job_id)
            self.scheduler.add_job(
                    status_manager, 'interval', seconds=2,
                    args=(job_id, scenario_id),
                    id='watch_{}'.format(job_id))


def status_manager(job_instance_id, scenario_instance_id):
    job_status_manager = StatusJobInstance(job_instance_id, update=True)
    job_status_manager.action()
    job_instance = job_status_manager.get_job_instance_or_not_found_error()
    if job_instance.status in ('Error', 'Finished', 'Not Running'):
        job_instance.is_stopped = True
        job_instance.save()
        StatusManager().remove(scenario_instance_id, job_instance_id)
        WatchJobInstance(job_instance_id, stop='now').action()
        if job_instance.status == 'Error':
            # TODO: stop the scenario
            pass
        else:
            si_id = WaitingQueueManager().remove_job(job_instance_id)
            assert scenario_instance_id == si_id
            scenario_instance = ScenarioInstance.objects.get(id=si_id)
            if not scenario_instance.is_stopped:
                ofis = scenario_instance.openbach_function_instances
                # Check if all JobInstance and all ScenarioInstance
                # launched by the ScenarioInstance are finished
                if (all(
                        job_instance.is_stopped for job_instance in
                        JobInstance.objects.filter(openbach_function_instance__in=ofis))
                    and all(
                        sub_scenario.is_stopped for sub_scenario in
                        ScenarioInstance.objects.filter(openbach_function_instance__in=ofis))):
                    # Update the status of the Scenario Instance if it is finished
                    if ThreadManager().is_scenario_stopped(scenario_instance.id):
                        scenario_instance.stop('Finished OK')


class ConductorServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Choose the underlying technology for our sockets servers"""
    allow_reuse_address = True


class BackendHandler(socketserver.BaseRequestHandler):
    def finish(self):
        """Close the connection after handling a request"""
        self.request.close()

    def handle(self):
        """Handle message comming from the backend"""

        fifo_infos = self.request.recv(4096).decode()
        fifoname = json.loads(fifo_infos)['fifoname']
        with open(fifoname) as fifo:
            request = json.loads(fifo.read())

        try:
            response, returncode = self.execute_request(request)
        except errors.ConductorError as e:
            result = {
                    'response': e.json,
                    'returncode': e.ERROR_CODE,
            }
            syslog.syslog(syslog.LOG_ERR, '{}'.format(result))
        except Exception as e:
            result = {
                    'response': {
                        'message': 'Unexpected exception appeared',
                        'error': str(e),
                        'traceback': traceback.format_exc(),
                    },
                    'returncode': 500,
            }
            syslog.syslog(syslog.LOG_ALERT, '{}'.format(result))
        else:
            result = {'response': response, 'returncode': returncode}
            syslog.syslog(syslog.LOG_INFO, '{}'.format(result))
        finally:
            self.request.sendall(b'Done')
            with open(fifoname, 'w') as fifo:
                json.dump(result, fifo, cls=DjangoJSONEncoder)

    def execute_request(self, request):
        """Analyze the data received to execute the right action"""
        request_name = request.pop('command')
        action_name = ''.join(map(str.title, request_name.split('_')))
        print('\n#', '-' * 76, '#')
        print('Executing the action', action_name, 'with parameters', request)
        try:
            action = globals()[action_name]
        except KeyError:
            raise errors.ConductorError(
                    'A Function is not implemented',
                    function_name=action_name)
        return action(**request).action()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_term_handler)

    backend_server = ConductorServer(('', 1113), BackendHandler)
    try:
        backend_server.serve_forever()
    finally:
        backend_server.server_close()
