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


class Agent(models.Model):
    name = models.CharField(max_length=200, null=True, blank=True, unique=True)
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


class Job_Argument(models.Model):
    INTEGER = 'int'
    BOOL = 'bool'
    STRING = 'str'
    FLOAT = 'float'
    IP = 'ip'
    NONE = 'None'
    TYPE_CHOICES = (
        (INTEGER, 'Integer'),
        (BOOL, 'Bool'),
        (STRING, 'String'),
        (FLOAT, 'Float'),
        (IP, 'IP'),
        (NONE, 'None'),
    )
    type = models.CharField(
        max_length=5,
        choices=TYPE_CHOICES,
        default=NONE,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Required_Job_Argument(Job_Argument):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    rank = models.IntegerField()

    class Meta:
        unique_together = (('name', 'job'), ('rank', 'job'))


class Optional_Job_Argument(Job_Argument):
    flag = models.CharField(max_length=200)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'job'),('flag', 'job'))


class Installed_Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    update_status = models.DateTimeField(null=True, blank=True)
    severity = models.IntegerField()
    local_severity = models.IntegerField()
    default_stat_storage = models.BooleanField(default=True)
    default_stat_broadcast = models.BooleanField(default=False)

    def set_name(self):
        self.name = '{0.job} on {0.agent}'.format(self)

    def __str__(self):
        return self.name


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

    def check_args(self):
        nb_required_args = self.job.job.required_job_argument_set.count()
        nb_required_job_argument_instances = self.required_job_argument_instance_set.count()
        if nb_required_job_argument_instances != nb_required_args:
            raise ValueError('Not enough arguments')
        for required_job_argument_instance in self.required_job_argument_instance_set.all():
            required_job_argument_instance.check_values()
        for optional_job_argument_instance in self.optional_job_argument_instance_set.all():
            optional_job_argument_instance.check_values()

    def __str__(self):
        return 'Job Instance {} of {}'.format(self.id, self.job)


class Job_Argument_Instance(models.Model):
    pass


class Required_Job_Argument_Instance(Job_Argument_Instance):
    argument = models.ForeignKey(Required_Job_Argument, on_delete=models.CASCADE)
    job_instance = models.ForeignKey(Job_Instance, on_delete=models.CASCADE)

    def check_values(self):
        for value in self.job_argument_value_set.all():
            value.check_type()

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

    def check_values(self):
        for value in self.job_argument_value_set.all():
            value.check_type()

    def __str__(self):
        values = ''
        for job_argument_value in self.job_argument_value_set.all():
            if values == '':
                values = '\"{}\"'.format(job_argument_value)
            else:
                values = '{},\"{}\"'.format(values, job_argument_value)
        return 'Argument {} of Job Instance {} with values [{}]'.format(self.argument.name, self.job_instance.id, values)


class Job_Argument_Value(models.Model):
    value = models.CharField(max_length=200)
    argument_instance = models.ForeignKey(Job_Argument_Instance, on_delete=models.CASCADE)

    def check_type(self):
        type = self.argument_instance.argument.type
        if type == 'int':
            try:
                int(self.value)
            except ValueError:
                raise ValueError('Job_Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(self.value, type))
        elif type == 'bool':
            accepted_bool = ['True', 'true', 'TRUE', 'T', 't', 'False', 'false',
                             'FALSE', 'F', 'f']
            if self.value not in accepted_bool:
                raise ValueError('Job_Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(self.value, type))
        elif type == 'str':
            pass
        elif type == 'float':
            try:
                float(self.value)
            except ValueError:
                raise ValueError('Job_Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(self.value, type))
        elif type == 'ip':
            try:
                ipaddress.ip_address(self.value)
            except ValueError:
                raise ValueError('Job_Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(self.value, type))
        elif type =='None':
            raise ValueError('When the type is \'{}\', it should not have value'
                             .format(type))
        else:
            raise ValueError('Job_Argument_Value \'{}\' has not a known type:'
                             ' \'{}\''.format(self.value, type))

    def __str__(self):
        return self.value


class Watch(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    instance_id = models.IntegerField(primary_key=True)
    interval = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return 'Watch of Job Instance {0.instance_id} of {0.job}'.format(self)

