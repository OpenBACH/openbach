#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
models.py - <+description+>
"""

from django.db import models
from django.db.models.fields import GenericIPAddressField, FilePathField
from django.utils.encoding import smart_str
import sys
if sys.version_info >= (2, 5):
    import hashlib
    md5_constructor = hashlib.md5
    md5_hmac = md5_constructor
    sha_constructor = hashlib.sha1
    sha_hmac = sha_constructor
else:
    import md5
    md5_constructor = md5.new
    md5_hmac = md5
    import sha
    sha_constructor = sha.new
    sha_hmac = sha

def get_hexdigest(algorithm, salt, raw_password):
    """
    Returns a string of the hexdigest of the given plaintext password and salt
    using the given algorithm ('md5', 'sha1' or 'crypt').
    """
    raw_password, salt = smart_str(raw_password), smart_str(salt)
    if algorithm == 'crypt':
        try:
            import crypt
        except ImportError:
            raise ValueError('"crypt" password algorithm not supported in this environment')
        return crypt.crypt(raw_password, salt)

    if algorithm == 'md5':
        return md5_constructor(salt + raw_password).hexdigest()
    elif algorithm == 'sha1':
        return sha_constructor(salt + raw_password).hexdigest()
    raise ValueError("Got unknown password algorithm type in password.")

class Agent(models.Model):
    name = models.CharField(max_length=200, blank=True)
    address = GenericIPAddressField(primary_key=True)
    status = models.CharField(max_length=200, blank=True)
    update_status = models.DateTimeField(blank=True)
    username = models.CharField(max_length=200)
    password = models.CharField(max_length=200)
    collector = GenericIPAddressField()
    
    def set_password(self, raw_password):
        # TODO How do we register the password ?
        import random
        algo = 'sha1'
        salt = get_hexdigest(algo, str(random.random()),
                             str(random.random()))[:5]
        hsh = get_hexdigest(algo, salt, raw_password)
        self.password = '%s$%s$%s' % (algo, salt, hsh)
    
    def __str__(self):
        return self.address


class Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    path = FilePathField(path="/opt/openbach/jobs", recursive=True,
                         allow_folders=True, allow_files=False)
    nb_args = models.IntegerField()
    optional_args = models.BooleanField()
    
    def __str__(self):
        return self.name


class Installed_Job(models.Model):
    name = models.CharField(max_length=200, primary_key=True)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE)
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    update_status = models.DateTimeField(blank=True)

    def set_name(self):
        self.name = self.job.name + " on " + self.agent.address

    def __str__(self):
        return self.name


class Instance(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    args = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=200, blank=True)
    update_status = models.DateTimeField(blank=True)

    def check_args(self):
        nb_args = len(self.args.split())
        if nb_args < self.job.job.nb_args:
            return False
        elif nb_args > self.job.job.nb_args:
            return self.job.job.optional_args
        else:
            return True

    def __str__(self):
        return "Instance " + str(self.id) + " of " + str(self.job)

