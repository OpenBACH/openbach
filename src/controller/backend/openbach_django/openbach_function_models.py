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


from contextlib import suppress

from django.db import models, IntegrityError
from django.utils import timezone

from .base_models import ContentTyped, OpenbachFunctionArgument
from .condition_models import Condition
from .project_models import Agent, Collector, Entity

import errors


class OpenbachFunction(ContentTyped):
    """Data associated to an Openbach Function"""

    function_id = models.IntegerField()
    label = models.CharField(max_length=500, null=True, blank=True)
    scenario_version = models.ForeignKey(
            'ScenarioVersion',
            models.CASCADE,
            related_name='openbach_functions')
    wait_time = models.IntegerField(default=0)

    class Meta:
        unique_together = ('scenario_version', 'function_id')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Override the standard Django's save operation to
        make sure we store which concrete implementation was
        used to build the associated object.
        """
        self.set_content_model()
        super().save(*args, **kwargs)

    @classmethod
    def build_from_arguments(cls, function_id, label, scenario, wait_time, arguments):
        return cls.objects.create(
                function_id=function_id,
                label=label,
                scenario_version=scenario,
                wait_time=wait_time,
                **arguments)

    @property
    def scenario(self):
        return self.scenario_version.scenario

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
            wait['finished_ids'] = [
                    waited.openbach_function_waited.function_id
                    for waited in self.finished_waiters.all()
            ]
        if wait:
            json_data['wait'] = wait

        if self.label is not None:
            json_data['label'] = self.label
        return json_data

    def set_arguments_count(self, arguments):
        this = self.get_content_model()
        for value in this._openbach_function_argument_values():
            for placeholder in OpenbachFunctionArgument.placeholders(value):
                arguments[placeholder] += 1

    def _openbach_function_argument_values(self):
        for field in self._meta.fields:
            if isinstance(field, OpenbachFunctionArgument):
                yield getattr(self, field.name)

    def instance_value(self, field_name, parameters):
        value = getattr(self, field_name)
        field = self._meta.get_field(field_name)
        if isinstance(field, OpenbachFunctionArgument):
            value = field.validate_openbach_value(value, parameters)
        return value

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
                self.id, self.scenario_instance.id))

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
        from .scenario_models import ScenarioInstance
        from .job_models import JobInstance

        json_data = self.openbach_function.json
        json_data['status'] = self.status
        json_data['launch_date'] = self.launch_date

        with suppress(ScenarioInstance.DoesNotExist):
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

class AssignCollector(OpenbachFunction):
    address = OpenbachFunctionArgument(type=str)
    collector = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'assign_collector': {
            'address': self.address,
            'collector': self.collector,
        }}

    def _get_arguments(self, parameters):
        return {
                'address': self.instance_value('address', parameters),
                'collector': self.instance_value('collector', parameters),
        }


class InstallAgent(OpenbachFunction):
    address = OpenbachFunctionArgument(type=str)
    collector = OpenbachFunctionArgument(type=str)
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

    def _get_arguments(self, parameters):
        return {
                'name': self.instance_value('name', parameters),
                'address': self.instance_value('address', parameters),
                'collector': self.instance_value('collector', parameters),
                'username': self.instance_value('username', parameters),
                'password': self.instance_value('password', parameters),
        }


class UninstallAgent(OpenbachFunction):
    address = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'uninstall_agent': {
            'address': self.address,
        }}

    def _get_arguments(self, parameters):
        return {
                'address': self.instance_value('address', parameters),
        }


class PushFile(OpenbachFunction):
    local_path = OpenbachFunctionArgument(type=str)
    remote_path = OpenbachFunctionArgument(type=str)
    address = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'push_file': {
            'address': self.address,
            'local_path': self.local_path,
            'remote_path': self.remote_path,
        }}

    def _get_arguments(self, parameters):
        return {
                'address': self.instance_value('address', parameters),
                'local_path': self.instance_value('local_path', parameters),
                'remote_path': self.instance_value('remote_path', parameters),
        }


class StartJobInstance(OpenbachFunction):
    entity_name = OpenbachFunctionArgument(type=str)
    job_name = OpenbachFunctionArgument(type=str)
    offset = OpenbachFunctionArgument(type=int)

    def _openbach_function_argument_values(self):
        yield from super()._openbach_function_argument_values()
        for argument in self.arguments.all():
            yield argument.value

    @classmethod
    def build_from_arguments(cls, function_id, label, scenario, wait_time, arguments):
        offset = arguments.pop('offset', 0)
        if not isinstance(offset, int):
            raise TypeError(int, offset, 'offset')
        entity_name = arguments.pop('entity_name')
        if len(arguments) > 1:
            raise ValueError('Too much job names to start')
        if len(arguments) < 1:
            raise ValueError('The name of the job to start is missing')
        job_name, = arguments
        if not isinstance(arguments[job_name], dict):
            raise TypeError(dict, arguments[job_name], job_name)

        return cls.objects.create(
                function_id=function_id,
                label=label,
                scenario_version=scenario,
                wait_time=wait_time,
                offset=offset,
                job_name=job_name,
                entity_name=entity_name)

    def _prepare_arguments(self, parameters=None):
        arguments = {}
        for argument in self.arguments.all():
            value = argument.get_value(parameters) if parameters is not None else argument.value
            try:
                old_value = arguments[argument.name]
            except KeyError:
                arguments[argument.name] = value
            else:
                if isinstance(old_value, list):
                    old_value.append(value)
                else:
                    arguments[argument.name] = [old_value, value]
        return arguments

    @property
    def _json(self):
        return {'start_job_instance': {
            self.job_name: self._prepare_arguments(),
            'offset': self.offset,
            'entity_name': self.entity_name,
        }}

    def _get_arguments(self, parameters):
        entity_name = self.instance_value('entity_name', parameters)
        project = self.scenario.project
        project_name = None if project is None else project.name

        try:
            entity = Entity.objects.get(name=entity_name, project=project)
        except Entity.DoesNotExist:
            raise errors.ConductorError(
                    'Entity does not exist in the project',
                    entity_name=entity_name, project_name=project_name)
        if entity.agent is None:
            raise errors.ConductorError(
                    'Entity does not have an associated agent',
                    entity_name=entity_name, project_name=project_name)

        return {
                'name': self.instance_value('job_name', parameters),
                'offset': self.instance_value('offset', parameters),
                'address': entity.agent.address,
                'arguments': self._prepare_arguments(parameters),
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
        field = self._meta.get_field('value')
        return field.validate_openbach_value(value, parameters)


class StopJobInstance(OpenbachFunction):
    openbach_function_id = OpenbachFunctionArgument(type=int)

    @property
    def _json(self):
        return {'stop_job_instance': {
            'openbach_function_id': self.openbach_function_id,
        }}

    def _get_arguments(self, parameters):
        return {
                'openbach_function_id': self.instance_value('openbach_function_id', parameters),
        }


class StopJobInstances(OpenbachFunction):
    openbach_function_ids = OpenbachFunctionArgument(type=list)

    @property
    def _json(self):
        return {'stop_job_instances': {
            'openbach_function_ids': [int(id) for id in self.openbach_function_ids],
        }}

    def _get_arguments(self, parameters):
        field_name = 'openbach_function_ids'
        stop_ids = self.instance_value(field_name, parameters)
        return {
                field_name: [int(id) for id in stop_ids],
        }


class RestartJobInstance(OpenbachFunction):
    instance_id = OpenbachFunctionArgument(type=int)
    instance_args = OpenbachFunctionArgument(type=dict)
    date = OpenbachFunctionArgument(type=str)
    interval = OpenbachFunctionArgument(type=int)

    @classmethod
    def build_from_arguments(cls, function_id, label, scenario, wait_time, arguments):
        instance_id = arguments.pop('instance_id')
        args = arguments.pop('arguments')
        if not isinstance(args, dict):
            raise TypeError(dict, args, instance_id)

        return cls.objects.create(
                function_id=function_id,
                label=label,
                scenario_version=scenario,
                wait_time=wait_time,
                instance_id=instance_id,
                instance_args=args,
                **arguments)

    @property
    def _json(self):
        return {'restart_job_instance': {
            'instance_id': self.instance_id,
            'arguments': self.instance_args,
            'date': self.date,
            'interval': self.interval,
        }}

    def _get_arguments(self, parameters):
        return {
                'instance_id': self.instance_value('instance_id', parameters),
                'arguments': self.instance_value('instance_args', parameters),
                'date': self.instance_value('date', parameters),
                'interval': self.instance_value('interval', parameters),
        }


class StatusJobInstance(OpenbachFunction):
    instance_id = OpenbachFunctionArgument(type=int)
    update = OpenbachFunctionArgument(type=bool)

    @property
    def _json(self):
        return {'status_job_instance': {
            'instance_id': self.instance_id,
            'update': self.update,
        }}

    def _get_arguments(self, parameters):
        return {
                'instance_id': self.instance_value('instance_id', parameters),
                'update': self.instance_value('update', parameters),
        }


class ListJobInstances(OpenbachFunction):
    addresses = OpenbachFunctionArgument(type=list)
    update = OpenbachFunctionArgument(type=bool)

    @property
    def _json(self):
        return {'status_job_instance': {
            'addresses': self.addresses,
            'update': self.update,
        }}

    def _get_arguments(self, parameters):
        return {
                'addresses': self.instance_value('addresses', parameters),
                'update': self.instance_value('update', parameters),
        }


class SetLogSeverityJob(OpenbachFunction):
    address = OpenbachFunctionArgument(type=str)
    job_name = OpenbachFunctionArgument(type=str)
    severity = OpenbachFunctionArgument(type=int)
    local_severity = OpenbachFunctionArgument(type=int)
    date = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'set_log_severity_job': {
            'address': self.address,
            'job_name': self.job_name,
            'severity': self.severity,
            'local_severity': self.local_severity,
            'date': self.date,
        }}

    def _get_arguments(self, parameters):
        return {
                'address': self.instance_value('address', parameters),
                'name': self.instance_value('job_name', parameters),
                'severity': self.instance_value('severity', parameters),
                'local_severity': self.instance_value('local_severity', parameters),
                'date': self.instance_value('date', parameters),
        }


class SetStatisticsPolicyJob(OpenbachFunction):
    address = OpenbachFunctionArgument(type=str)
    job_name = OpenbachFunctionArgument(type=str)
    stat_name = OpenbachFunctionArgument(type=str)
    storage = OpenbachFunctionArgument(type=bool)
    broadcast = OpenbachFunctionArgument(type=bool)
    date = OpenbachFunctionArgument(type=str)

    @property
    def _json(self):
        return {'set_log_severity_job': {
            'address': self.address,
            'job_name': self.job_name,
            'stat_name': self.stat_name,
            'storage': self.storage,
            'broadcast': self.broadcast,
            'date': self.date,
        }}

    def _get_arguments(self, parameters):
        return {
                'address': self.instance_value('address', parameters),
                'name': self.instance_value('job_name', parameters),
                'stat_name': self.instance_value('stat_name', parameters),
                'storage': self.instance_value('storage', parameters),
                'broadcast': self.instance_value('broadcast', parameters),
                'date': self.instance_value('date', parameters),
        }


class If(OpenbachFunction):
    condition = models.OneToOneField(
            Condition,
            models.CASCADE,
            related_name='if_function')
    functions_true = OpenbachFunctionArgument(type=list)
    functions_false = OpenbachFunctionArgument(type=list)

    @classmethod
    def build_from_arguments(cls, function_id, label, scenario, wait_time, arguments):
        condition = Condition.load_from_json(arguments['condition'])
        for name in ('openbach_functions_true_ids', 'openbach_functions_false_ids'):
            functions = arguments[name]
            if not isinstance(functions, list):
                raise TypeError(list, functions, name)

        return cls.objects.create(
                function_id=function_id,
                label=label,
                scenario_version=scenario,
                wait_time=wait_time,
                condition=condition,
                functions_true=arguments['openbach_functions_true_ids'],
                functions_false=arguments['openbach_functions_false_ids'])

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

    @classmethod
    def build_from_arguments(cls, function_id, label, scenario, wait_time, arguments):
        condition = Condition.load_from_json(arguments['condition'])
        for name in ('openbach_functions_while_ids', 'openbach_functions_end_ids'):
            functions = arguments[name]
            if not isinstance(functions, list):
                raise TypeError(list, functions, name)

        return cls.objects.create(
                function_id=function_id,
                label=label,
                scenario_version=scenario,
                wait_time=wait_time,
                condition=condition,
                functions_while=arguments['openbach_functions_while_ids'],
                functions_end=arguments['openbach_functions_end_ids'])

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
        arguments = {
                field_name: self.instance_value(field_name, parameters)
                for field_name in ('scenario_name', 'arguments')
        }
        project = self.scenario.project
        arguments['project'] = project.name if project else None
        return arguments


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
