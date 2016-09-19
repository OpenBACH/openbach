#!/usr/bin/env python 
# -*- coding: utf-8 -*-

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
   
   
   
   @file     models.py
   @brief    Describs the data the backend uses
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from django.db import models
from django.contrib.auth import hashers
import ipaddress
import json


class Agent(models.Model):
    name = models.CharField(max_length=20, unique=True)
    address = models.GenericIPAddressField(primary_key=True)
    status = models.CharField(max_length=200, null=True, blank=True)
    update_status = models.DateTimeField(null=True, blank=True)
    reachable = models.BooleanField()
    update_reachable = models.DateTimeField(null=True, blank=True)
    username = models.CharField(max_length=200)
    password = models.CharField(max_length=200)
    collector = models.GenericIPAddressField()

    def set_password(self, raw_password):
        # https://docs.djangoproject.com/en/1.9/topics/auth/passwords/
        #self.password = hashers.make_password(raw_password, algo='sha1')
        self.password = raw_password

    def check_password(self, raw_password):
        return hashers.check_password(raw_password, self.password)

    def __str__(self):
        return self.address


class Job_Keyword(models.Model):
    name = models.CharField(max_length=200, primary_key=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    path = models.FilePathField(
            path="/opt/openbach-controller/jobs", recursive=True,
            allow_folders=True, allow_files=False)
    help = models.TextField(null=True, blank=True)
    job_version = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    keywords = models.ManyToManyField(Job_Keyword)

    def __str__(self):
        return self.name


class Statistic(models.Model):
    name = models.CharField(max_length=200)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    frequency = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ('name', 'job')

    def __str__(self):
        return self.name


class Argument(models.Model):
    INTEGER = 'int'
    BOOL = 'bool'
    STRING = 'str'
    FLOAT = 'float'
    IP = 'ip'
    LIST = 'list'
    JSON = 'json'
    NONE = 'None'
    typeCHOICES = (
        (INTEGER, 'Integer'),
        (BOOL, 'Bool'),
        (STRING, 'String'),
        (FLOAT, 'Float'),
        (IP, 'IP'),
        (LIST, 'List'),
        (JSON, 'Json'),
        (NONE, 'None'),
    )
    type = models.CharField(
        max_length=5,
        choices=typeCHOICES,
        default=NONE,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Required_Job_Argument(Argument):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    rank = models.IntegerField()

    class Meta:
        unique_together = (('name', 'job'), ('rank', 'job'))


class Optional_Job_Argument(Argument):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    flag = models.CharField(max_length=200)

    class Meta:
        unique_together = (('name', 'job'), ('flag', 'job'))


class Installed_Job(models.Model):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    update_status = models.DateTimeField(null=True, blank=True)
    severity = models.IntegerField()
    local_severity = models.IntegerField()
    default_stat_storage = models.BooleanField(default=True)
    default_stat_broadcast = models.BooleanField(default=False)

    class Meta:
        unique_together = ('agent', 'job')

    def __str__(self):
        return '{0.job} on {0.agent}'.format(self)


class Statistic_Instance(models.Model):
    stat = models.ForeignKey(Statistic, on_delete=models.CASCADE)
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    storage = models.BooleanField(default=True)
    broadcast = models.BooleanField(default=False)

    class Meta:
        unique_together = ('stat', 'job')

    def __str__(self):
        return self.stat.name


class Job_Instance(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    status = models.CharField(max_length=200)
    update_status = models.DateTimeField()
    start_date = models.DateTimeField()
    stop_date = models.DateTimeField(null=True, blank=True)
    periodic = models.BooleanField()
    is_stopped = models.BooleanField(default=False)

    def __str__(self):
        return 'Job Instance {} of {}'.format(self.id, self.job)


class Job_Argument_Instance(models.Model):
    argument_instance_id = models.AutoField(primary_key=True)


class Required_Job_Argument_Instance(Job_Argument_Instance):
    argument = models.ForeignKey(Required_Job_Argument, on_delete=models.CASCADE)
    job_instance = models.ForeignKey(Job_Instance, on_delete=models.CASCADE)

    def __str__(self):
        values = ''
        for job_argument_value in self.job_argument_value_set.all():
            if values == '':
                values = '\"{}\"'.format(job_argument_value)
            else:
                values = '{},\"{}\"'.format(values, job_argument_value)
        return 'Argument {} of Job Instance {} with values [{}]'.format(self.argument.name, self.job_instance.id, values)


class Optional_Job_Argument_Instance(Job_Argument_Instance):
    argument = models.ForeignKey(Optional_Job_Argument, on_delete=models.CASCADE)
    job_instance = models.ForeignKey(Job_Instance, on_delete=models.CASCADE)

    def __str__(self):
        values = ''
        for job_argument_value in self.job_argument_value_set.all():
            if values == '':
                values = '\"{}\"'.format(job_argument_value)
            else:
                values = '{},\"{}\"'.format(values, job_argument_value)
        return 'Argument {} of Job Instance {} with values [{}]'.format(self.argument.name, self.job_instance.id, values)


class Argument_Value(models.Model):
    argument_value_id = models.AutoField(primary_key=True)
    value = models.CharField(max_length=200)

    ACCEPTED_BOOLS = frozenset({'True', 'true', 'TRUE', 'T', 't', 'False', 'false',
                                'FALSE', 'F', 'f'})

    def _check_type_internal(self, type, value):
        if type == 'int':
            try:
                int(value)
            except ValueError:
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'bool':
            if value not in self.ACCEPTED_BOOLS:
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'str':
            pass
        elif type == 'float':
            try:
                float(value)
            except ValueError:
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'ip':
            try:
                ipaddress.ip_address(value)
            except ValueError:
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'None':
            raise ValueError('When the type is \'{}\', it should not have value'
                             .format(type))
        elif type == 'list':
            if not isinstance(value, list):
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'json':
            if not isinstance(value, dict):
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        else:
            raise ValueError('Argument_Value \'{}\' has not a known type:'
                             ' \'{}\''.format(value, type))

    def __str__(self):
        return self.value


class Job_Argument_Value(Argument_Value):
    job_argument_instance = models.ForeignKey(Job_Argument_Instance, on_delete=models.CASCADE)

    def check_and_set_value(self, value):
        type = self.job_argument_instance.argument.type
        self._check_type_internal(type, value)
        if type == 'json':
            self.value = json.dumps(value)
        else:
            self.value = value


class Watch(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    instance_id = models.IntegerField(primary_key=True)
    interval = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return 'Watch of Job Instance {0.instance_id} of {0.job}'.format(self)


class Openbach_Function(models.Model):
    name = models.CharField(max_length=200, primary_key=True)

    def __str__(self):
        return self.name


class Openbach_Function_Argument(Argument):
    openbach_function = models.ForeignKey(Openbach_Function, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'openbach_function'))


class Scenario(models.Model):
    name = models.CharField(max_length=20, primary_key=True)
    description = models.CharField(max_length=200, null=True, blank=True)
    scenario = models.TextField()

    def __str__(self):
        return self.name


class Scenario_Argument(Argument):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)

    def check_or_set_type(self, type):
        if self.type is 'None':
            self.type = type
        else:
            if self.type != type:
                return False
        return True

    class Meta:
        unique_together = (('name', 'scenario'))


class Scenario_Instance(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)
    status = models.CharField(max_length=200, null=True, blank=True)
    status_date = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return 'Scenario Instance {}'.format(self.id)


class Scenario_Argument_Instance(Argument_Value):
    argument = models.ForeignKey(Scenario_Argument, on_delete=models.CASCADE)
    scenario_instance = models.ForeignKey(Scenario_Instance,
                                          on_delete=models.CASCADE, null=True,
                                          blank=True)

    TRUE = frozenset({'True', 'true', 'TRUE', 'T', 't'})

    def check_and_set_value(self, value):
        type = self.argument.type
        self._check_type_internal(type, value)
        if type == 'json':
            self.value = json.dumps(value)
        else:
            self.value = value

    class Meta:
        unique_together = (('argument', 'scenario_instance'))

    def __str__(self):
        return self.value


class Openbach_Function_Instance(models.Model):
    openbach_function = models.ForeignKey(Openbach_Function, on_delete=models.CASCADE)
    scenario_instance = models.ForeignKey(Scenario_Instance, on_delete=models.CASCADE)
    openbach_function_instance_id = models.IntegerField()
    job_instance = models.ForeignKey(Job_Instance, null=True, blank=True)
    status = models.CharField(max_length=200, null=True, blank=True)
    status_date = models.DateTimeField(null=True, blank=True)
    time = models.IntegerField(default=0)

    def __str__(self):
        return 'Scenario \'{}\' openbach_function \'{}\' (Scenario_Instance \'{}\')'.format(
            self.scenario_instance.scenario.name,
            self.openbach_function_instance_id, self.scenario_instance.id)

    class Meta:
        unique_together = (('openbach_function_instance_id', 'scenario_instance'))


class Wait_For_Launched(models.Model):
    openbach_function_instance_id_waited = models.IntegerField()
    openbach_function_instance = models.ForeignKey(Openbach_Function_Instance, on_delete=models.CASCADE)

    def __str__(self):
        return 'OFI {} waits for OFI {} to be launch (Scenario_Instance \'{}\')'.format(
            self.openbach_function_instance.openbach_function_instance_id,
            self.openbach_function_instance_id_waited,
            self.openbach_function_instance.scenario_instance.id)


class Wait_For_Finished(models.Model):
    job_instance_id_waited = models.IntegerField()
    openbach_function_instance = models.ForeignKey(Openbach_Function_Instance, on_delete=models.CASCADE)

    def __str__(self):
        return 'OFI {} waits for OFI {} to finish (Scenario_Instance \'{}\')'.format(
            self.openbach_function_instance.openbach_function_instance_id,
            self.job_instance_id_waited,
            self.openbach_function_instance.scenario_instance.id)


class Openbach_Function_Argument_Instance(Argument_Value):
    argument = models.ForeignKey(Openbach_Function_Argument, on_delete=models.CASCADE)
    openbach_function_instance = models.ForeignKey(Openbach_Function_Instance,
                                                   on_delete=models.CASCADE)

    def check_and_set_value(self, value):
        type = self.argument.type
        self._check_type_internal(type, value)
        if type == 'json':
            self.value = json.dumps(value)
        else:
            self.value = value

    def __str__(self):
        return self.value

