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


"""Table descriptions relatives to the OpenBACH's jobs.

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


from datetime import datetime

from django.db import models, IntegrityError
from django.utils import timezone

from .base_models import Argument, ArgumentValue


class Keyword(models.Model):
    """Keyword associated to a Job"""
    name = models.CharField(max_length=500, primary_key=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    """Data associated to a Job"""

    name = models.CharField(max_length=500, primary_key=True)
    path = models.FilePathField(
            path="/opt/openbach-controller/jobs", recursive=True,
            allow_folders=True, allow_files=False)
    help = models.TextField(null=True, blank=True)
    job_version = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    keywords = models.ManyToManyField(Keyword, related_name='jobs')
    has_uncertain_required_arg = models.BooleanField(default=False)
    persistent = models.BooleanField(default=False)

    def __str__(self):
        return self.name

    @property
    def json(self):
        os = {}
        for system in self.os.all():
            os.update(system.json)

        return {
                'general': {
                    'name': self.name,
                    'description': self.description,
                    'job_version': self.job_version,
                    'keywords': [keyword.name for keyword in self.keywords.all()],
                    'persistent': self.persistent,
                },
                'os': os,
                'arguments': {
                    'required': [arg.json for arg in self.required_arguments.order_by('rank')],
                    'optional': [arg.json for arg in self.optional_arguments.all()],
                },
                'statistics': [stat.json for stat in self.statistics.all()],
        }


class OsCommand(models.Model):
    """Data relative to how a job should be launched/cleaned-up on a given OS"""

    job = models.ForeignKey(Job, models.CASCADE, related_name='os')
    name = models.CharField(max_length=500)
    requirements = models.CharField(max_length=500)
    command = models.CharField(max_length=1000)
    command_stop = models.CharField(max_length=1000, null=True, blank=True)

    class Meta:
        unique_together = ('name', 'job')

    def __str__(self):
        return '{} commands for Job {}'.format(self.name, self.job)

    @property
    def json(self):
        return {
                self.name: {
                    'requirements': self.requirements,
                    'command': self.command,
                    'command_stop': self.command_stop,
                },
        }


class Statistic(models.Model):
    """Data associated to a Statistic generated by a Job"""

    name = models.CharField(max_length=500)
    job = models.ForeignKey(Job, models.CASCADE, related_name='statistics')
    description = models.TextField(null=True, blank=True)
    frequency = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('name', 'job')

    def __str__(self):
        return self.name

    @property
    def json(self):
        return {
                'name': self.name,
                'description': self.description,
                'frequency': self.frequency,
        }


class InstalledJob(models.Model):
    """Data associated to a Job installed on an Agent"""

    agent = models.ForeignKey(
            'Agent', models.CASCADE,
            related_name='installed_jobs')
    job = models.ForeignKey(
            Job, models.CASCADE,
            related_name='installations')
    update_status = models.DateTimeField(null=True, blank=True)
    severity = models.IntegerField(default=1)
    local_severity = models.IntegerField(default=1)
    default_stat_storage = models.BooleanField(default=True)
    default_stat_broadcast = models.BooleanField(default=False)

    class Meta:
        unique_together = ('agent', 'job')

    def __str__(self):
        return '{0.job} installed on {0.agent}'.format(self)

    @property
    def json(self):
        return {
                'name': self.job.name,
                'update_status': self.update_status.astimezone(
                    timezone.get_current_timezone()),
                'severity': self.severity,
                'local_severity': self.local_severity,
                'default_stat_policy': {
                    'storage': self.default_stat_storage,
                    'broadcast': self.default_stat_broadcast,
                },
                'statistic_instances': [stat.json for stat in self.statistics.all()],
        }


class StatisticInstance(models.Model):
    """State of a given Statistic for a specific Installed_Job"""

    stat = models.ForeignKey(
            Statistic, models.CASCADE,
            related_name='instances')
    job = models.ForeignKey(
            InstalledJob, models.CASCADE,
            related_name='statistics')
    storage = models.BooleanField(default=True)
    broadcast = models.BooleanField(default=False)

    class Meta:
        unique_together = ('stat', 'job')

    def __str__(self):
        return self.stat.name

    def save(self, *args, **kwargs):
        if self.job.job != self.stat.job:
            raise IntegrityError(
                    'Trying to save a StatisticInstance with the '
                    'associated InstalledJob and the associated '
                    'Statistic not referencing the same Job')
        super().save(*args, **kwargs)

    @property
    def json(self):
        return {
                'name': self.stat.name,
                'storage': self.storage,
                'broadcast': self.broadcast,
        }


class JobInstance(models.Model):
    """Data associated to a Job instance"""

    job = models.ForeignKey(
            InstalledJob, models.CASCADE,
            related_name='instances')
    status = models.CharField(max_length=500)
    update_status = models.DateTimeField()
    start_date = models.DateTimeField()
    stop_date = models.DateTimeField(null=True, blank=True)
    periodic = models.BooleanField()
    is_stopped = models.BooleanField(default=False)
    openbach_function_instance = models.OneToOneField(
            'OpenbachFunctionInstance',
            models.SET_NULL,
            null=True, blank=True,
            related_name='started_job')

    def set_status(self, status):
        self.status = status
        self.update_status = timezone.now()

    @property
    def scenario_id(self):
        if self.openbach_function_instance is None:
            return 0
        return self.openbach_function_instance.scenario_instance.id

    @property
    def start_timestamp(self):
        date = self.start_date
        if date < timezone.now():
            return 'now'
        return int(date.timestamp() * 1000)

    @property
    def arguments(self):
        required_args = self.job.job.required_arguments.order_by('rank')
        optional_flags_only = self.optional_arguments_values.filter(
                argument__type='None',
                value='True')
        optional_arguments = self.job.job.optional_arguments.exclude(type='None')

        quote = '"{}"'.format
        required = ' '.join(
                quote(value) for argument in required_args
                for value in argument.values.filter(job_instance=self))
        optional = ' '.join('{} {}'.format(
                    argument.flag,
                    ' '.join(quote(value) for value in argument.values.filter(job_instance=self)))
                for argument in optional_arguments)
        flags = ' '.join(value.argument.flag for value in optional_flags_only)

        return '{} {} {}'.format(required, flags, optional)

    def configure(self, arguments, date=None, interval=None):
        """Build the hierarchy of values for this Job Instance arguments"""
        self.start_date = timezone.now()
        if interval is None:
            self.periodic = False
            if date not in (None, 'now'):
                tz = timezone.get_current_timezone()
                self.start_date = datetime.fromtimestamp(date / 1000, tz=tz)
        else:
            self.periodic = True

        # Remove old arguments in case of a restart
        self.required_arguments_values.all().delete()
        self.optional_arguments_values.all().delete()

        job = self.job.job
        for arg_name, arg_values in arguments.items():
            try:
                argument_instance = RequiredJobArgument.objects.get(job=job, name=arg_name)
                JobArgumentValue = RequiredJobArgumentValue
            except RequiredJobArgument.DoesNotExist:
                try:
                    argument_instance = OptionalJobArgument.objects.get(job=job, name=arg_name)
                    JobArgumentValue = OptionalJobArgumentValue
                except OptionalJobArgument.DoesNotExist:
                    raise KeyError(
                            '\'{}\' argument is not part of the job '
                            '\'{}\''.format(arg_name, job.name))

            if not isinstance(arg_values, list):
                arg_values = [arg_values]
            count = len(arg_values)
            if not argument_instance.check_count(count):
                raise ValueError(
                        'Provided number of arguments ({}) does not '
                        'match with their expected number ({})'
                        .format(count, argument_instance.count))
            for arg_value in arg_values:
                job_argument = JobArgumentValue(
                        argument=argument_instance,
                        job_instance=self)
                job_argument.check_and_set_value(arg_value)
                job_argument.save()

    def __str__(self):
        return 'Job Instance {} of {}'.format(self.id, self.job)

    @property
    def json(self):
        arguments = {}
        for argument in self.required_arguments_values.all():
            arguments.setdefault(argument.argument.name, []).append(argument.value)
        for argument in self.optional_arguments_values.all():
            arguments.setdefault(argument.argument.name, []).append(argument.value)

        tz = timezone.get_current_timezone()
        stop_date = 'Not programmed yet'
        if self.stop_date is not None:
            stop_date = self.stop_date.astimezone(tz)

        return {
                'name': self.job.job.name,
                'agent': self.job.agent.address,
                'id': self.id,
                'arguments': arguments,
                'update_status': self.update_status.astimezone(tz),
                'status': self.status,
                'start_date': self.start_date.astimezone(tz),
                'stop_date': stop_date,
        }


class Watch(models.Model):
    """Data associated to a Watch of a Job instance"""

    job_instance = models.OneToOneField(
            JobInstance, models.CASCADE,
            related_name='watch')
    interval = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return 'Watch of {}'.format(self.job_instance)


class RequiredJobArgument(Argument):
    """Data associated to an Argument that is required for a Job"""

    job = models.ForeignKey(
            Job, models.CASCADE,
            related_name='required_arguments')
    rank = models.IntegerField()

    class Meta:
        unique_together = (('name', 'job'), ('rank', 'job'))

    def save(self, *args, **kwargs):
        count = self.count

        if count is None:
            raise TypeError(
                    'You must specify a count value for the '
                    'required argument \'{}\''.format(self.name))

        if count == '*' or count == '+' or len(count.split('-')) > 1:
            if self.job.has_uncertain_required_arg:
                raise TypeError(
                        'A Job can only have one required argument with '
                        'a variable amount of values')
            self.job.has_uncertain_required_arg = True

        super().save(*args, **kwargs)
        self.job.save()

    @property
    def json(self):
        return {
                'name': self.name,
                'type': self.type,
                'count': self.count,
                'description': self.description,
        }


class OptionalJobArgument(Argument):
    """Data associated to an Argument that is optional for a Job"""

    job = models.ForeignKey(
            Job, models.CASCADE,
            related_name='optional_arguments')
    flag = models.CharField(max_length=500)

    class Meta:
        unique_together = (('name', 'job'), ('flag', 'job'))

    def save(self, *args, **kwargs):
        if self.count is None:
            raise TypeError(
                    'You must specify a count value for the '
                    'optional argument \'{}\''.format(self.name))

        super().save(*args, **kwargs)

    @property
    def json(self):
        return {
                'name': self.name,
                'type': self.type,
                'count': self.count,
                'flag': self.flag,
                'description': self.description,
        }


class RequiredJobArgumentValue(ArgumentValue):
    """Data stored as the value of a Required Argument for a Job"""

    argument = models.ForeignKey(
            RequiredJobArgument,
            models.CASCADE,
            related_name='values')
    job_instance = models.ForeignKey(
            JobInstance, models.CASCADE,
            related_name='required_arguments_values')

    def check_and_set_value(self, value):
        self._check_and_set_value(value, self.argument.type)

    def save(self, *args, **kwargs):
        if self.argument.job != self.job_instance.job.job:
            raise IntegrityError(
                    'Trying to save a RequiredJobArgumentValue '
                    'with the associated JobInstance and the '
                    'associated job argument not referencing the same Job')
        super().save(*args, **kwargs)


class OptionalJobArgumentValue(ArgumentValue):
    """Data stored as the value of an Optional Argument for a Job"""

    argument = models.ForeignKey(
            OptionalJobArgument,
            models.CASCADE,
            related_name='values')
    job_instance = models.ForeignKey(
            JobInstance, models.CASCADE,
            related_name='optional_arguments_values')

    def check_and_set_value(self, value):
        self._check_and_set_value(value, self.argument.type)

    def save(self, *args, **kwargs):
        if self.argument.job != self.job_instance.job.job:
            raise IntegrityError(
                    'Trying to save an OptionalJobArgumentValue '
                    'with the associated JobInstance and the '
                    'associated job argument not referencing the same Job')
        super().save(*args, **kwargs)
