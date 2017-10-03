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


"""Table descriptions relatives to the OpenBACH's scenarios.

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


from django.db import models, IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError

from .base_models import Argument, ArgumentValue, OpenbachFunctionArgument
from . import openbach_function_models
from .job_models import Job, RequiredJobArgument, OptionalJobArgument
from .condition_models import Condition
from .openbach_function_models import (
        OpenbachFunctionInstance, StartJobInstance,
        StartJobInstanceArgument,
        WaitForLaunched, WaitForFinished
)

from .utils import check_and_get_value


def prepare_arguments(arguments, function_name):
    try:
        preparator = PREPARATORS[function_name]
    except KeyError:
        return arguments

    return preparator(arguments)


def prepare_start_job_instance(arguments):
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

    return {
            'offset': offset,
            'entity_name': entity_name,
            'job_name': job_name,
    }


def prepare_if(arguments):
    condition = Condition.load_from_json(arguments['condition'])
    for name in ('openbach_functions_true_ids', 'openbach_functions_false_ids'):
        functions = arguments[name]
        if not isinstance(functions, list):
            raise TypeError(list, functions, name)
    return {
            'condition': condition,
            'functions_true': arguments['openbach_functions_true_ids'],
            'functions_false': arguments['openbach_functions_false_ids'],
    }


def prepare_while(arguments):
    condition = Condition.load_from_json(arguments['condition'])
    for name in ('openbach_functions_while_ids', 'openbach_functions_end_ids'):
        functions = arguments[name]
        if not isinstance(functions, list):
            raise TypeError(list, functions, name)
    return {
            'condition': condition,
            'functions_while': arguments['openbach_functions_while_ids'],
            'functions_end': arguments['openbach_functions_end_ids'],
    }


PREPARATORS = {
        'start_job_instance': prepare_start_job_instance,
        'if': prepare_if,
        'while': prepare_while,
}


class Scenario(models.Model):
    """Data associated to a Scenario"""

    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)
    project = models.ForeignKey(
            'Project', models.CASCADE,
            null=True, blank=True,
            related_name='scenarios')

    class Meta:
        unique_together = (('name', 'project'))

    class MalformedError(Exception):
        def __init__(self, key, value=None, expected_type=None, override_error=None):
            if value is None:
                message = 'Missing entry \'{}\''.format(key)
                self.error = {
                        'error': 'Missing entry',
                        'offending_entry': key,
                }
            else:
                message = (
                        'Entry \'{}\' has the wrong kind of '
                        'value (expected {} got {})'
                        .format(key, expected_type, value)
                )
                self.error = {
                        'error': 'Type error',
                        'offending_entry': key,
                        'offending_value': value,
                        'expected_type': str(expected_type),
                }
            super().__init__(message)
            if override_error is not None:
                self.error['error'] = override_error

    def __str__(self):
        return self.name

    @property
    def is_valid(self):
        return False

    @property
    def json(self):
        functions = [
                f.get_content_model().json
                for f in self.openbach_functions.all()
        ]
        return {
                'name': self.name,
                'description': self.description,
                'arguments': {arg.name: arg.description
                              for arg in self.arguments.all()},
                'constants': {const.name: const.value
                              for const in self.constants.all()},
                'openbach_functions': functions,
        }

    def load_from_json(self, json_data):
        def extract_value(*keys, expected_type, mandatory=True):
            data = json_data
            for index, key in enumerate(keys, 1):
                try:
                    data = data[key]
                except KeyError:
                    if not mandatory and index == len(keys):
                        return expected_type()
                    raise Scenario.MalformedError(
                            '.'.join(map(str, keys[:index])))
                except TypeError:
                    raise Scenario.MalformedError(
                            '.'.join(map(str, keys[:index - 1])),
                            data, dict)
            if not isinstance(data, expected_type):
                raise Scenario.MalformedError(
                        '.'.join(map(str, keys)),
                        data, expected_type)
            return data

        # Cleanup in case of modifications
        self.arguments.all().delete()
        self.constants.all().delete()
        self.openbach_functions.all().delete()

        # Extract top-level parameters
        arguments = extract_value('arguments', expected_type=dict, mandatory=False)
        for name, description in arguments.items():
            if not isinstance(name, str):
                raise Scenario.MalformedError('arguments', name, str)
            if not isinstance(description, str):
                raise Scenario.MalformedError(
                        'arguments.{}'.format(name), description, str)
            ScenarioArgument.objects.create(
                    scenario=self,
                    name=name,
                    description=description)
        constants = extract_value('constants', expected_type=dict, mandatory=False)
        existing_names = self.arguments.filter(name__in=list(constants))
        if existing_names:
            keys = ', '.join('constants.{}'.format(arg.name) for arg in existing_names)
            raise Scenario.MalformedError(
                    keys, override_error='Some constants are '
                    'named the same than some arguments')
        for name, value in constants.items():
            if not isinstance(name, str):
                raise Scenario.MalformedError('constants', name, str)
            if not isinstance(value, str):
                raise Scenario.MalformedError(
                        'constants.{}'.format(name), value, str)
            ScenarioConstant.objects.create(
                    scenario=self,
                    name=name,
                    value=value)

        # Extract OpenBACH Functions definitions
        openbach_functions = extract_value('openbach_functions', expected_type=list)
        # range(len(...)), I know its bad, but I want to enforce type checking
        for index in range(len(openbach_functions)):
            function = extract_value('openbach_functions', index, expected_type=dict)
            wait = extract_value('openbach_functions', index, 'wait', expected_type=dict, mandatory=False)
            json_data['openbach_functions'][index]['wait'] = wait
            wait_time = extract_value('openbach_functions', index, 'wait', 'time', expected_type=int, mandatory=False)
            id_ = extract_value('openbach_functions', index, 'id', expected_type=int)
            label = extract_value('openbach_functions', index, 'label', expected_type=str, mandatory=False)
            possible_function_name = [key for key in function if key not in {'wait', 'id', 'label'}]
            if len(possible_function_name) < 1:
                raise Scenario.MalformedError(
                        'openbach_functions.{}'.format(index), value=function,
                        override_error='The content of the OpenBACH '
                                       'function to launch is missing')
            if len(possible_function_name) > 1:
                raise Scenario.MalformedError(
                        'openbach_functions.{}'.format(index), value=function,
                        override_error='Too much OpenBACH functions configured')
            function_name, = possible_function_name
            openbach_function_name = ''.join(map(str.title, function_name.split('_')))
            try:
                OpenbachFunction = getattr(openbach_function_models, openbach_function_name)
            except AttributeError:
                raise Scenario.MalformedError(
                        'openbach_functions.{}.{}'.format(index, function_name),
                        override_error='Unknown OpenBACH Function')
            try:
                openbach_function_arguments = prepare_arguments(
                        function[function_name],
                        function_name)
            except KeyError as e:
                raise Scenario.MalformedError(
                        'openbach_functions.{}.{}'.format(index, function_name),
                        override_error='Missing entry \'{}\''.format(e))
            except ValueError as e:
                raise Scenario.MalformedError(
                        'openbach_functions.{}.{}'.format(index, function_name),
                        override_error=str(e))
            except TypeError as e:
                try:
                    expected_type, value, name = e.args
                except ValueError:
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.{}'.format(index, function_name),
                            override_error=str(e))
                else:
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.{}.{}'.format(index, function_name, name),
                            value=value, expected_type=expected_type)

            try:
                openbach_function = OpenbachFunction.objects.create(
                        function_id=id_,
                        label=label,
                        scenario=self,
                        wait_time=wait_time,
                        **openbach_function_arguments)
            except (ValidationError, IntegrityError, TypeError) as err:
                raise Scenario.MalformedError(
                        'openbach_functions.{}.{}'.format(index, function_name),
                        override_error=str(err))

            if function_name == 'start_job_instance':
                job_name = openbach_function.job_name
                try:
                    job = Job.objects.get(name=job_name)
                except Job.DoesNotExist:
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.{}.{}'.format(index, function_name, job_name),
                            override_error='No such job in the database')
                # Register arguments
                arguments = function[function_name][job_name]
                for name, value in arguments.items():
                    try:
                        job_argument = job.required_arguments.get(name=name)
                    except RequiredJobArgument.DoesNotExist:
                        try:
                            job_argument = job.optional_arguments.get(name=name)
                        except OptionalJobArgument.DoesNotExist:
                            raise Scenario.MalformedError(
                                    'openbach_functions.{}.{}.{}.{}'
                                    .format(index, function_name, job_name, name),
                                    override_error='The configured job does '
                                    'not accept the given argument')
                    if not isinstance(value, str) or not OpenbachFunctionArgument.has_placeholders(value):
                        check_and_get_value(value, job_argument.type)
                    StartJobInstanceArgument.objects.create(
                            name=name, value=str(value),
                            start_job_instance=openbach_function)

        # Extract Waits
        # Start again the looping to be sure all referenced
        # indexes have been created
        for index, function in enumerate(openbach_functions):
            wait_launched = extract_value(
                    'openbach_functions', index, 'wait',
                    'launched_ids', expected_type=list, mandatory=False)
            for idx, launched_id in enumerate(wait_launched):
                if not isinstance(launched_id, int):
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.wait.'
                            'launched_ids.{}'.format(index, idx),
                            value=launched_id, expected_type=int)
                try:
                    waited_function = self.openbach_functions.get(function_id=launched_id)
                except OpenbachFunction.DoesNotExist:
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.wait.'
                            'launched_ids.{}'.format(index, idx),
                            value=launched_id, override_error='The '
                            'referenced openbach function does not exist')
                else:
                    waited_function = waited_function.get_content_model()
                openbach_function_instance = self.openbach_functions.get(
                        function_id=function['id']).get_content_model()
                WaitForLaunched.objects.create(
                        openbach_function_waited=waited_function,
                        openbach_function_instance=openbach_function_instance)
            wait_finished = extract_value(
                    'openbach_functions', index, 'wait',
                    'finished_ids', expected_type=list, mandatory=False)
            for idx, launched_id in enumerate(wait_finished):
                if not isinstance(launched_id, int):
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.wait.'
                            'finished_ids.{}'.format(index, idx),
                            value=launched_id, expected_type=int)
                try:
                    waited_function = self.openbach_functions.get(function_id=launched_id)
                except OpenbachFunction.DoesNotExist:
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.wait.'
                            'finished_ids.{}'.format(index, idx),
                            value=launched_id, override_error='The '
                            'referenced openbach function does not exits')
                else:
                    waited_function = waited_function.get_content_model()
                if not isinstance(waited_function, StartJobInstance):
                    raise Scenario.MalformedError(
                            'openbach_functions.{}.wait.'
                            'finished_ids.{}'.format(index, idx),
                            value=launched_id, override_error='The '
                            'referenced openbach function is not a '
                            'start_job_instance.')
                openbach_function_instance = self.openbach_functions.get(
                        function_id=function['id']).get_content_model()
                WaitForFinished.objects.create(
                        openbach_function_waited=waited_function,
                        openbach_function_instance=openbach_function_instance)

        # Check that all arguments are used
        scenario_arguments = {
                argument.name: 0 for argument in self.arguments.all()
        }

        for openbach_function in self.openbach_functions.all():
            try:
                openbach_function.set_arguments_count(scenario_arguments)
            except KeyError as e:
                raise Scenario.MalformedError(
                        'arguments.{}'.format(e),
                        override_error='This argument is used as '
                        'a placeholder value but is not defined')
        for name, count in scenario_arguments.items():
            if not count:
                raise Scenario.MalformedError(
                        'arguments.{}'.format(name),
                        override_error='An argument is unused')

    def save(self, *args, **kwargs):
        if self.project is None:
            # Manually enforce unique_together with null projects
            qs = Scenario.objects.filter(name=self.name, project=None)
            if hasattr(self, 'pk'):
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise IntegrityError(
                        'A Scenario named \'{}\' is already present in '
                        'the database without an associated Project'
                        .format(self.name))
        super().save(*args, **kwargs)


class ScenarioInstance(models.Model):
    """Data associated to a Scenario instance"""

    scenario = models.ForeignKey(
            Scenario, models.CASCADE,
            related_name='instances')
    status = models.CharField(max_length=500, null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    stop_date = models.DateTimeField(null=True, blank=True)
    is_stopped = models.BooleanField(default=False)
    openbach_function_instance = models.OneToOneField(
            OpenbachFunctionInstance,
            null=True, blank=True,
            related_name='started_scenario')

    def __str__(self):
        return 'Scenario Instance {}'.format(self.id)

    def stop(self, *, stop_status=None):
        if not self.is_stopped or stop_status is not None:
            self.status = 'Stopped' if stop_status is None else stop_status
            self.stop_date = timezone.now()
            self.is_stopped = True
            self.save()

    @property
    def parameters(self):
        constants = {
                constant.name: constant.value
                for constant in self.scenario.constants.all()
        }
        constants.update(
                (argument.argument.name, argument.value)
                for argument in self.arguments_values.all()
        )
        return constants

    @property
    def json(self):
        owner_id = None
        ofi = self.openbach_function_instance
        while ofi is not None:
            scenario = ofi.scenario_instance
            ofi = scenario.openbach_function_instance
            owner_id = scenario.id

        sub_scenario_ids = set()
        for openbach_function in self.openbach_functions_instances.all():
            try:
                sub_scenario = openbach_function.started_scenario
            except ScenarioInstance.DoesNotExist:
                pass
            else:
                sub_scenario_ids.add(sub_scenario.id)

        parameters = [
                {'name': key, 'value': value}
                for key, value in self.parameters.items()
        ]

        functions = [
                openbach_function.json for openbach_function in
                self.openbach_functions_instances.order_by('launch_date')
        ]

        project = self.scenario.project
        return {
                'project_name': None if project is None else project.name,
                'scenario_name': self.scenario.name,
                'scenario_instance_id': self.id,
                'owner_scenario_instance_id': owner_id,
                'sub_scenario_instance_ids': sorted(sub_scenario_ids),
                'status': self.status,
                'start_date': self.start_date,
                'stop_date': self.stop_date,
                'arguments': parameters,
                'openbach_functions': functions,
        }


class ScenarioArgument(Argument):
    """Data associated to an Argument for a Scenario"""

    scenario = models.ForeignKey(
            Scenario, models.CASCADE,
            related_name='arguments')

    class Meta:
        unique_together = (('name', 'scenario'))


class ScenarioConstant(Argument):
    """Data associated to a Constant for a Scenario"""

    scenario = models.ForeignKey(
            Scenario, models.CASCADE,
            related_name='constants')
    value = models.CharField(max_length=500)

    class Meta:
        unique_together = ('name', 'scenario')


class ScenarioArgumentValue(ArgumentValue):
    """Data stored as the value of an Argument for a Scenario"""

    argument = models.ForeignKey(
            ScenarioArgument, models.CASCADE,
            related_name='values')
    scenario_instance = models.ForeignKey(
            ScenarioInstance,
            models.CASCADE,
            related_name='arguments_values')

    class Meta:
        unique_together = ('argument', 'scenario_instance')

    def check_and_set_value(self, value):
        self._check_and_set_value(value, self.argument.type)

    def __str__(self):
        return self.value

    def save(self, *args, **kwargs):
        if self.argument.scenario != self.scenario_instance.scenario:
            raise IntegrityError(
                    'Trying to save a ScenarioArgumentValue '
                    'with the associated ScenarioInstance and '
                    'the associated scenario argument not '
                    'referencing the same Scenario')
        super().save(*args, **kwargs)
