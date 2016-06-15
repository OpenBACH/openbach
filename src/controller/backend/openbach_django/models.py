#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
models.py - <+description+>
"""

from django.db import models
from django.contrib.auth import hashers


class Agent(models.Model):
    name = models.CharField(max_length=200, blank=True, unique=True)
    address = models.GenericIPAddressField(primary_key=True)
    status = models.CharField(max_length=200, blank=True)
    update_status = models.DateTimeField(blank=True)
    reachable = models.BooleanField()
    update_reachable = models.DateTimeField(blank=True)
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


class Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    path = models.FilePathField(
            path="/opt/openbach/jobs", recursive=True,
            allow_folders=True, allow_files=False)
    help = models.TextField(blank=True)
    nb_args = models.IntegerField()
    optional_args = models.BooleanField()
    
    def __str__(self):
        return self.name


class Installed_Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    update_status = models.DateTimeField(blank=True)
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
    args = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=200, blank=True)
    update_status = models.DateTimeField(blank=True)

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
    interval = models.IntegerField(blank=True)

    def __str__(self):
        return 'Watch of Job Instance {0.instance_id} of {0.job}'.format(self)
