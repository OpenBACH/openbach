#!/usr/bin/env python

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


"""Table descriptions relatives to the OpenBACH's functions.

Each class in this module describe a table with its associated
columns in the backend's database. These classes are used by
the Django's ORM to convert results from databases queries into
Python objects.
"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import ipaddress
from contextlib import suppress

from django.db import models, IntegrityError
from django.utils import timezone

from .base_models import ContentTyped, OpenbachFunctionArgument
from .condition_models import Condition


class OpenbachFunction(ContentTyped):
    """Data associated to an Openbach Function"""

    function_id = models.IntegerField()
    label = models.CharField(max_length=500, null=True, blank=True)
    scenario = models.ForeignKey(
            'Scenario',
            models.CASCADE,
            related_name='openbach_functions')
    wait_time = models.IntegerField(default=0)

    class Meta:
        unique_together = ('scenario', 'function_id')

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.get_content_model()._meta.verbose_name

    @property
    def json(self):
        json_data = self.get_content_model()._json
        json_data['id'] = self.function_id

        wait = {}
        if self.wait_time != 0:
            wait['time'] = self.wait_time
        if self.launched_waiters.count():
            wait['launched_ids'] = [
                    waited.openbach_function_waited.function_id
                    for waited in self.launched_waiters.all()
            ]
        if self.finished_waiters.count():
            wait['launched_ids'] = [
                    waited.job_instance_waited.function_id
                    for waited in self.finished_waiters.all()
            ]
        if wait:
            json_data['wait'] = wait

        if self.label is not None:
            json_data['label'] = self.label
        return json_data

    def instance_value(self, field_name, parameters):
        value = getattr(self, field_name)
        field = self._meta._forward_fields_map[field_name]
        if isinstance(field, OpenbachFunctionArgument):
            value = field.validate_openbach_value(value, parameters)
        return value

    def check_arguments_type(self, parameters):
        self.get_content_model().check_arguments_type(parameters)

    def get_arguments(self, parameters):
        return self.get_content_model()._get_arguments(parameters)


class OpenbachFunctionInstance(models.Model):
    """Data associated to an Openbach Function instance"""

    openbach_function = models.ForeignKey(
            OpenbachFunction,
            models.CASCADE,
            related_name='instances')
    scenario_instance = models.ForeignKey(
            'ScenarioInstance', models.CASCADE,
            related_name='openbach_functions_instances')
    status = models.CharField(max_length=500, null=True, blank=True)
    launch_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return (
            'Openbach Function \'{}\' of Scenario \'{}\' '
            '(instance {} of scenario {})'.format(
                self.openbach_function.name,
                self.scenario_instance.scenario.name,
                self.instance_id,
                self.scenario_instance.id))

    def check_arguments_type(self):
        parameters = self.scenario_instance.parameters
        self.openbach_function.check_arguments_type(parameters)

    def start(self):
        self.status = 'Running'
        self.launch_date = timezone.now()
        self.save()

    def set_status(self, status):
        self.status = status
        self.save()

    def save(self, *args, **kwargs):
        if self.scenario_instance.scenario != self.openbach_function.scenario:
            raise IntegrityError(
                    'Trying to save an OpenbachFunctionInstance with the '
                    'associated ScenarioInstance and the associated '
                    'OpenbachFunction not referencing the same Scenario')
        super().save(*args, **kwargs)

    @property
    def json(self):
        # Late imports to avoid circular dependencies
        from .scenario_models import Scenario
        from .job_models import JobInstance

        json_data = self.openbach_function.json
        json_data['status'] = self.status
        json_data['launch_date'] = self.launch_date

        with suppress(Scenario.DoesNotExist):
            scenario = self.started_scenario
            json_data['scenario'] = scenario.json

        with suppress(JobInstance.DoesNotExist):
            job_instance = self.started_job
            json_data['job'] = job_instance.json

        return json_data

    @property
    def arguments(self):
        parameters = self.scenario_instance.parameters
        return self.openbach_function.get_arguments(parameters)


class WaitForLaunched(models.Model):
    """Waiting condition that will prevent an OpenBACH Function
    to start before an other one is already started.
    """

    openbach_function_waited = models.ForeignKey(
            OpenbachFunction,
            on_delete=models.CASCADE,
            related_name='+')
    openbach_function_instance = models.ForeignKey(
            OpenbachFunction,
            on_delete=models.CASCADE,
            related_name='launched_waiters')

    def __str__(self):
        return ('{0.openbach_function_instance} waits for '
                '{0.openbach_function_waited} to be launched'.format(self))

    def save(self, *args, **kwargs):
        own_scenario = self.openbach_function_instance.scenario
        waited_scenario = self.openbach_function_waited.scenario
        if waited_scenario != own_scenario:
            raise IntegrityError(
                    'Trying to save a WaitForLaunched instance '
                    'with the associated OpenbachFunction and '
                    'the waited OpenbachFunction not '
                    'referencing the same Scenario')
        super().save(*args, **kwargs)


class WaitForFinished(models.Model):
    """Waiting condition that will prevent an OpenBACH Function
    to start before an other one is completely finished.
    """

    openbach_function_waited = models.ForeignKey(
            OpenbachFunction,
            models.CASCADE,
            related_name='+')
    openbach_function_instance = models.ForeignKey(
            OpenbachFunction,
            on_delete=models.CASCADE,
            related_name='finished_waiters')

    def __str__(self):
        return ('{0.openbach_function_instance} waits for '
                '{0.openbach_function_waited} to finish'.format(self))

    def save(self, *args, **kwargs):
        own_scenario = self.openbach_function_instance.scenario
        waited_scenario = self.openbach_function_waited.scenario
        if waited_scenario != own_scenario:
            raise IntegrityError(
                    'Trying to save a WaitForFinished instance '
                    'with the associated OpenbachFunction and '
                    'the waited OpenbachFunction not '
                    'referencing the same Scenario')
        super().save(*args, **kwargs)


# From here on, definition of supported OpenBACH functions

class InstallAgent(OpenbachFunction):
    address = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    collector = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    username = OpenbachFunctionArgument(type=str)
    password = OpenbachFunctionArgument(type=str)
    name = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'install_agent': {
            'address': self.address,
            'collector': self.collector,
            'username': self.username,
            'password': self.password,
            'name': self.name,
        }}


class UninstallAgent(OpenbachFunction):
    address = OpenbachFunctionArgument(type=ipaddress._BaseAddress)

    @property
    def _json(self):
        return {'uninstall_agent': {
            'address': self.address,
        }}


class ListAgent(OpenbachFunction):
    update = OpenbachFunctionArgument(type=bool)

    @property
    def _json(self):
        return {'list_agent': {
            'update': self.update,
        }}


class RetrieveStatusAgents(OpenbachFunction):
    addresses = OpenbachFunctionArgument(type=list)
    update = OpenbachFunctionArgument(type=bool)

    @property
    def _json(self):
        return {'retrieve_status_agent': {
            'addresses': self.addresses,
            'update': self.update,
        }}


class AddJob(OpenbachFunction):
    name = OpenbachFunctionArgument(type=str)
    path = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'add_job': {
            'name': self.name,
            'path': self.path,
        }}


class DeleteJob(OpenbachFunction):
    name = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'del_job': {
            'name': self.name,
        }}


class ListJobs(OpenbachFunction):
    verbosity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {'list_jobs': {
            'verbosity': self.verbosity,
        }}


class GetStatisticsJob(OpenbachFunction):
    name = OpenbachFunctionArgument(type=str)
    verbosity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class GetHelpJob(OpenbachFunction):
    name = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {}


class InstallJobs(OpenbachFunction):
    addresses = OpenbachFunctionArgument(type=list)
    names = OpenbachFunctionArgument(type=list)
    severity = OpenbachFunctionArgument(type=int)
    local_severity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class ListInstalledJobs(OpenbachFunction):
    address = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    update = OpenbachFunctionArgument(type=bool)
    verbosity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class RetrieveStatusJobs(OpenbachFunction):
    addresses = OpenbachFunctionArgument(type=list)

    @property
    def _json(self):
        return {}


class PushFile(OpenbachFunction):
    local_path = OpenbachFunctionArgument(type=str)
    remote_path = OpenbachFunctionArgument(type=str)
    agent_ip = OpenbachFunctionArgument(type=ipaddress._BaseAddress)

    @property
    def _json(self):
        return {}


class StartJobInstance(OpenbachFunction):
    agent_ip = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    job_name = OpenbachFunctionArgument(type=str)
    offset = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        arguments = {}
        for argument in self.arguments.all():
            try:
                old_value = arguments[argument.name]
            except KeyError:
                arguments[argument.name] = argument.value
            else:
                if isinstance(old_value, list):
                    old_value.append(argument.value)
                else:
                    arguments[argument.name] = [old_value, argument.value]

        return {'start_job_instance': {
            self.job_name: arguments,
            'offset': self.offset,
            'agent_ip': self.agent_ip,
        }}

    def _get_arguments(self, parameters):
        arguments = {}
        for argument in self.arguments.all():
            value = argument.get_value(parameters)
            try:
                old_value = arguments[argument.name]
            except KeyError:
                arguments[argument.name] = value
            else:
                if isinstance(old_value, list):
                    old_value.append(value)
                else:
                    arguments[argument.name] = [old_value, value]

        return {
                'address': self.instance_value('agent_ip', parameters),
                'name': self.instance_value('job_name', parameters),
                'offset': self.instance_value('offset', parameters),
                'arguments': arguments,
        }


class StartJobInstanceArgument(models.Model):
    """Storage of arguments of a Job Instance as defined by a
    Scenario. Possible usage of placeholder values make it
    impossible to create the arguments up-front.
    """

    name = models.CharField(max_length=500)
    value = OpenbachFunctionArgument(type=str)
    start_job_instance = models.ForeignKey(
            StartJobInstance,
            models.CASCADE,
            related_name='arguments')

    def get_value(self, parameters):
        value = self.value
        field = self._meta._forward_fields_map['value']
        return field.validate_openbach_value(value, parameters)


class StopJobInstance(OpenbachFunction):
    openbach_function_ids = OpenbachFunctionArgument(type=list)

    @property
    def _json(self):
        return {'stop_job_instance': {
            'openbach_function_ids': self.openbach_function_ids,
        }}

    def _get_arguments(self, parameters):
        field_name = 'openbach_functions_ids'
        return {
                field_name: self.instance_value(field_name, parameters),
        }


class RestartJobInstance(OpenbachFunction):
    instance_id = OpenbachFunctionArgument(type=int)
    instance_args = OpenbachFunctionArgument(type=dict)
    date = OpenbachFunctionArgument(type=str)
    interval = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class WatchJobInstance(OpenbachFunction):
    instance_id = OpenbachFunctionArgument(type=int)
    date = OpenbachFunctionArgument(type=str)
    interval = OpenbachFunctionArgument(type=int)
    stop = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {}


class StatusJobInstance(OpenbachFunction):
    instance_id = OpenbachFunctionArgument(type=int)
    verbosity = OpenbachFunctionArgument(type=int)
    update = OpenbachFunctionArgument(type=bool)

    @property
    def _json(self):
        return {}


class ListJobInstances(OpenbachFunction):
    addresses = OpenbachFunctionArgument(type=list)
    update = OpenbachFunctionArgument(type=bool)
    verbosity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class SetLogSeverityJob(OpenbachFunction):
    address = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    job_name = OpenbachFunctionArgument(type=str)
    severity = OpenbachFunctionArgument(type=int)
    date = OpenbachFunctionArgument(type=str)
    local_severity = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {}


class SetStatisticsPolicyJob(OpenbachFunction):
    address = OpenbachFunctionArgument(type=ipaddress._BaseAddress)
    job_name = OpenbachFunctionArgument(type=str)
    stat_name = OpenbachFunctionArgument(type=str)
    storage = OpenbachFunctionArgument(type=bool)
    broadcast = OpenbachFunctionArgument(type=bool)
    date = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {}


class If(OpenbachFunction):
    condition = models.OneToOneField(
            Condition,
            models.CASCADE,
            related_name='if_function')
    functions_true = OpenbachFunctionArgument(type=list)
    functions_false = OpenbachFunctionArgument(type=list)

    @property
    def _json(self):
        return {'if': {
            'condition': self.condition.json,
            'openbach_function_true_ids': self.functions_true,
            'openbach_function_false_ids': self.functions_false,
        }}

    def _get_arguments(self, parameters):
        return {
                'condition': self.condition,
                'on_true': self.instance_value('functions_true', parameters),
                'on_false': self.instance_value('functions_false', parameters),
        }


class While(OpenbachFunction):
    condition = models.OneToOneField(
            Condition,
            models.CASCADE,
            related_name='while_function')
    functions_while = OpenbachFunctionArgument(type=list)
    functions_end = OpenbachFunctionArgument(type=list)

    @property
    def _json(self):
        return {'while': {
            'condition': self.condition.json,
            'openbach_function_while_ids': self.functions_while,
            'openbach_function_end_ids': self.functions_end,
        }}

    def _get_arguments(self, parameters):
        return {
                'condition': self.condition,
                'on_true': self.instance_value('functions_while', parameters),
                'on_false': self.instance_value('functions_end', parameters),
        }


class StartScenarioInstance(OpenbachFunction):
    scenario_name = OpenbachFunctionArgument(type=str)
    arguments = OpenbachFunctionArgument(type=dict)

    @property
    def _json(self):
        return {'start_scenario_instance': {
            'scenario_name': self.scenario_name,
            'arguments': self.arguments,
        }}

    def _get_arguments(self, parameters):
        return {
                field_name: self.instance_value(field_name, parameters)
                for field_name in ('scenario_name', 'arguments')
        }


class StopScenarioInstance(OpenbachFunction):
    openbach_function_id = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {'stop_scenario_instance': {
            'openbach_function_id': self.openbach_function_id,
        }}

    def _get_arguments(self, parameters):
        field_name = 'openbach_function_id'
        return {
                field_name: self.instance_value(field_name, parameters)
        }
