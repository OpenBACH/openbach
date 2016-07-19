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
    nb_args = models.IntegerField()
    optional_args = models.BooleanField()
    job_version = models.CharField(max_length=200, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    keywords = models.ManyToManyField(Job_Keyword)

    def __str__(self):
        return self.name


class Available_Statistic(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    frequency = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name


class Installed_Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    update_status = models.DateTimeField(null=True, blank=True)
    severity = models.IntegerField()
    local_severity = models.IntegerField()
    stats_default_policy = models.BooleanField()
    accept_stats = models.CharField(max_length=200)
    deny_stats = models.CharField(max_length=200)

    def set_name(self):
        self.name = '{0.job} on {0.agent}'.format(self)

    def __str__(self):
        return self.name


class Job_Instance(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    args = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=200)
    update_status = models.DateTimeField()
    start_date = models.DateTimeField()
    stop_date = models.DateTimeField(null=True, blank=True)
    periodic = models.BooleanField()
    is_stopped = models.BooleanField(default=False)

    def validate_args_len(self):
        args_count = len(self.args.split())
        if args_count < self.job.job.nb_args:
            raise ValueError('not enough arguments')

        return min(args_count, self.job.job.nb_args)

    def __str__(self):
        return 'Job Instance {} of {}'.format(self.id, self.job)


class Watch(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    instance_id = models.IntegerField(primary_key=True)
    interval = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return 'Watch of Job Instance {0.instance_id} of {0.job}'.format(self)

