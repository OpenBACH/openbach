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
import requests
from .utils import BadRequest
from django.utils import timezone


class ContentTyped(models.Model):
    content_model = models.CharField(editable=False, max_length=50, null=True)

    class Meta:
        abstract = True

    def concrete(self):
        klass = self.__class__
        for kls in reversed(klass.__mro__):
            if issubclass(kls, ContentTyped) and not kls._meta.abstract:
                return kls
        return klass  # Mimic `or model.__class__`

    def set_content_model(self):
        """
        Set content_model to the child class's related name, or None if this is
        the base class.
        """
        is_base_class = (
            self.concrete() == self.__class__)
        self.content_model = (
            None if is_base_class else self._meta.object_name.lower())

    def get_content_model(self):
        """
        Return content model, or if this is the base class return it.
        """
        return (getattr(self, self.content_model) if self.content_model
else self)


class Command_Result(models.Model):
    response = models.TextField(default='{"state": "Running"}')
    returncode = models.IntegerField(default=202)
    date = models.DateTimeField(default=timezone.now)

    def reset(self):
        self.response = '{"state": "Running"}'
        self.returncode = 202
        self.save()

    def get_json(self):
        return {'response': json.loads(self.response), 'returncode':
                self.returncode, 'date': self.date}


class Collector(models.Model):
    address = models.GenericIPAddressField(primary_key=True)
    logs_port = models.IntegerField(default=10514)
    stats_port = models.IntegerField(default=2222)

    def __str__(self):
        return self.address


class Collector_Command_Result(models.Model):
    address = models.GenericIPAddressField(primary_key=True)
    status_add = models.ForeignKey(Command_Result, null=True, blank=True,
                                   related_name='status_add')
    status_modify = models.ForeignKey(Command_Result, null=True, blank=True,
                                      related_name='status_mofidy')
    status_del = models.ForeignKey(Command_Result, null=True, blank=True,
                                   related_name='status_del')

    def get_json(self):
        result_json = {}
        if self.status_add:
            result_json['add'] = self.status_add.get_json()
        else:
            result_json['add'] = {'error': 'Action never asked', 'returncode':
                                  404}
        if self.status_modify:
            result_json['modify'] = self.status_modify.get_json()
        else:
            result_json['modify'] = {'error': 'Action never asked',
                                     'returncode': 404}
        if self.status_del:
            result_json['del'] = self.status_del.get_json()
        else:
            result_json['del'] = {'error': 'Action never asked', 'returncode':
                                  404}
        return result_json


class Agent(models.Model):
    name = models.CharField(max_length=500, unique=True)
    address = models.GenericIPAddressField(primary_key=True)
    status = models.CharField(max_length=500, null=True, blank=True)
    update_status = models.DateTimeField(null=True, blank=True)
    reachable = models.BooleanField()
    update_reachable = models.DateTimeField(null=True, blank=True)
    username = models.CharField(max_length=500)
    password = models.CharField(max_length=500)
    collector = models.ForeignKey(Collector)
    networks = models.ManyToManyField('Network')

    def set_password(self, raw_password):
        # https://docs.djangoproject.com/en/1.9/topics/auth/passwords/
        #self.password = hashers.make_password(raw_password, algo='sha1')
        self.password = raw_password

    def check_password(self, raw_password):
        return hashers.check_password(raw_password, self.password)

    def __str__(self):
        return '{} ({})'.format(self.name, self.address)

    def get_json(self):
        return {
            'address': self.address,
            'name': self.name,
            'username': self.username,
            'collector': self.collector.address
        }


class Agent_Command_Result(models.Model):
    address = models.GenericIPAddressField(primary_key=True)
    status_install = models.ForeignKey(Command_Result, null=True, blank=True,
                                       related_name='status_install')
    status_uninstall = models.ForeignKey(Command_Result, null=True, blank=True,
                                         related_name='status_uninstall')
    status_retrieve_status_agent = models.ForeignKey(
        Command_Result, null=True, blank=True,
        related_name='status_retrieve_status_agent')
    status_assign = models.ForeignKey(Command_Result, null=True, blank=True,
                                      related_name='status_assign_collector')
    status_retrieve_status_jobs = models.ForeignKey(
        Command_Result, null=True, blank=True,
        related_name='status_retrieve_status_jobs')

    def get_json(self):
        result_json = {}
        if self.status_install:
            result_json['install'] = self.status_install.get_json()
        else:
            result_json['install'] = {'error': 'Action never asked',
                                      'returncode': 404}
        if self.status_uninstall:
            result_json['uninstall'] = self.status_uninstall.get_json()
        else:
            result_json['uninstall'] = {'error': 'Action never asked',
                                        'returncode': 404}
        if self.status_retrieve_status_agent:
            result_json['retrieve_status_agent'] = self.status_retrieve_status_agent.get_json()
        else:
            result_json['retrieve_status_agent'] = {'error': 'Action never '
                                                    'asked', 'returncode': 404}
        if self.status_assign:
            result_json['assign'] = self.status_assign.get_json()
        else:
            result_json['assign'] = {'error': 'Action never '
                                     'asked', 'returncode': 404}
        if self.status_retrieve_status_jobs:
            result_json['retrieve_status_jobs'] = self.status_retrieve_status_jobs.get_json()
        else:
            result_json['retrieve_status_jobs'] = {'error': 'Action never '
                                                   'asked', 'returncode': 404}
        return result_json


class File_Command_Result(Command_Result):
    filename = models.CharField(max_length=500)
    remote_path = models.CharField(max_length=500)
    address = models.GenericIPAddressField()

    class Meta:
        unique_together = ('filename', 'address', 'remote_path')


class Job_Keyword(models.Model):
    name = models.CharField(max_length=500, primary_key=True)

    def __str__(self):
        return self.name


class Job(models.Model):
    name = models.CharField(max_length=500, primary_key=True)
    path = models.FilePathField(
            path="/opt/openbach-controller/jobs", recursive=True,
            allow_folders=True, allow_files=False)
    help = models.TextField(null=True, blank=True)
    job_version = models.CharField(max_length=500, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    keywords = models.ManyToManyField(Job_Keyword)
    has_uncertain_required_arg = models.BooleanField(default=False)
    job_conf = models.TextField()

    def __str__(self):
        return self.name


class Statistic(models.Model):
    name = models.CharField(max_length=500)
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
    count = models.CharField(max_length=11, null=True, blank=True)
    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)

    class Meta:
        abstract = True

    def check_count(self, actual_count):
        if not isinstance(actual_count, int):
            raise BadRequest('The given count should be an int')
        if self.count == '*':
            return True
        if self.count == '+':
            if actual_count > 0:
                return True
            else:
                return False
        counts = self.count.split('-')
        if len(counts) == 2:
            if (actual_count >= int(counts[0]) and actual_count <=
                int(counts[1])):
                return True
        else:
            count = int(self.count)
            if actual_count != count:
                return False
        return True

    def __str__(self):
        return self.name


class Required_Job_Argument(Argument):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    rank = models.IntegerField()

    def save(self, *args, **kwargs):
        if self.job.has_uncertain_required_arg:
            raise BadRequest('This Job can only have one required argument with'
                             ' an uncertain count, and it should be the last'
                             ' one')
        if self.count == '+':
            self.job.has_uncertain_required_arg = True
        else:
            try:
                int(self.count)
            except ValueError:
                counts = self.count.split('-')
                if len(counts) == 2:
                    count1 = counts[0]
                    count2 = counts[1]
                    try:
                        count1 = int(count1)
                        count2 = int(count2)
                    except:
                        raise BadRequest('interval of counts are allowed but'
                                         ' its should be ints')
                    if count1 > count2:
                        raise BadRequest('interval of counts are allowed but'
                                         ' the first should be lower or equal'
                                         ' to the second')
                else:
                    raise BadRequest('count should be \'+\', an int or an'
                                     ' interval')
                self.job.has_uncertain_required_arg = True
        super(Argument, self).save(*args, **kwargs)

    class Meta:
        unique_together = (('name', 'job'), ('rank', 'job'))


class Optional_Job_Argument(Argument):
    job = models.ForeignKey(Job, on_delete=models.CASCADE)
    flag = models.CharField(max_length=500)

    def save(self, *args, **kwargs):
        if self.count == '*' or self.count == '+':
            pass
        else:
            try:
                int(self.count)
            except ValueError:
                counts = self.count.split('-')
                if len(counts) == 2:
                    count1 = counts[0]
                    count2 = counts[1]
                    try:
                        count1 = int(count1)
                        count2 = int(count2)
                    except:
                        raise BadRequest('interval of counts are allowed but its'
                                         ' should be ints')
                    if count1 > count2:
                        raise BadRequest('interval of counts are allowed but the'
                                         ' first should be lower or equal to the'
                                         ' second')
                else:
                    raise BadRequest('count should be \'*\', \'+\', an int or'
                                     ' an interval')
        super(Argument, self).save(*args, **kwargs)

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


class Installed_Job_Command_Result(models.Model):
    agent_ip = models.GenericIPAddressField()
    job_name = models.CharField(max_length=500)
    status_install = models.ForeignKey(Command_Result, null=True, blank=True,
                                       related_name='status_install_job')
    status_uninstall = models.ForeignKey(Command_Result, null=True, blank=True,
                                         related_name='status_uninstall_job')
    status_log_severity = models.ForeignKey(Command_Result, null=True,
                                            blank=True,
                                            related_name='status_log_severity')
    status_stat_policy = models.ForeignKey(Command_Result, null=True,
                                           blank=True,
                                           related_name='status_stat_policy')

    def get_json(self):
        result_json = {}
        if self.status_install:
            result_json['install'] = self.status_install.get_json()
        else:
            result_json['install'] = {'error': 'Action never asked',
                                      'returncode': 404}
        if self.status_uninstall:
            result_json['uninstall'] = self.status_uninstall.get_json()
        else:
            result_json['uninstall'] = {'error': 'Action never asked',
                                        'returncode': 404}
        if self.status_log_severity:
            result_json['log_severity'] = self.status_log_severity.get_json()
        else:
            result_json['log_severity'] = {'error': 'Action never asked',
                                           'returncode': 404}
        if self.status_stat_policy:
            result_json['stat_policy'] = self.status_stat_policy.get_json()
        else:
            result_json['stat_policy'] = {'error': 'Action never asked',
                                          'returncode': 404}
        return result_json

    class Meta:
        unique_together = ('agent_ip', 'job_name')


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
    status = models.CharField(max_length=500)
    update_status = models.DateTimeField()
    start_date = models.DateTimeField()
    stop_date = models.DateTimeField(null=True, blank=True)
    periodic = models.BooleanField()
    is_stopped = models.BooleanField(default=False)
    openbach_function_instance = models.ForeignKey("Openbach_Function_Instance",
                                                   null=True, blank=True)
    scenario_instance = models.ForeignKey("Scenario_Instance", null=True,
                                          blank=True)

    def __str__(self):
        return 'Job Instance {} of {}'.format(self.id, self.job)


class Job_Instance_Command_Result(models.Model):
    job_instance_id = models.IntegerField(primary_key=True)
    status_start = models.ForeignKey(Command_Result, null=True, blank=True,
                                     related_name='status_start')
    status_stop = models.ForeignKey(Command_Result, null=True, blank=True,
                                    related_name='status_stop')
    status_restart = models.ForeignKey(Command_Result, null=True, blank=True,
                                       related_name='status_restart')
    status_watch = models.ForeignKey(Command_Result, null=True, blank=True,
                                     related_name='status_watch')

    def get_json(self):
        result_json = {}
        if self.status_start:
            result_json['start'] = self.status_start.get_json()
        else:
            result_json['start'] = {'error': 'Action never asked',
                                    'returncode': 404}
        if self.status_stop:
            result_json['stop'] = self.status_stop.get_json()
        else:
            result_json['stop'] = {'error': 'Action never asked',
                                      'returncode': 404}
        if self.status_restart:
            result_json['restart'] = self.status_restart.get_json()
        else:
            result_json['restart'] = {'error': 'Action never asked',
                                      'returncode': 404}
        if self.status_watch:
            result_json['watch'] = self.status_watch.get_json()
        else:
            result_json['watch'] = {'error': 'Action never asked',
                                    'returncode': 404}
        return result_json


class Job_Argument_Instance(models.Model):
    argument_instance_id = models.AutoField(primary_key=True)


class Required_Job_Argument_Instance(Job_Argument_Instance):
    argument = models.ForeignKey(Required_Job_Argument,
                                 on_delete=models.CASCADE)
    job_instance = models.ForeignKey(Job_Instance, on_delete=models.CASCADE)

    def __str__(self):
        values = ''
        for job_argument_value in self.job_argument_value_set.all():
            if values == '':
                values = '\"{}\"'.format(job_argument_value)
            else:
                values = '{},\"{}\"'.format(values, job_argument_value)
        return 'Argument {} of Job Instance {} with values [{}]'.format(
            self.argument.name, self.job_instance.id, values)


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
        return 'Argument {} of Job Instance {} with values [{}]'.format(
            self.argument.name, self.job_instance.id, values)


class Argument_Value(models.Model):
    argument_value_id = models.AutoField(primary_key=True)
    value = models.CharField(max_length=500)

    ACCEPTED_BOOLS = frozenset({'True', 'true', 'TRUE', 'T', 't', 'False',
                                'false', 'FALSE', 'F', 'f'})

    def _check_type_internal(self, type, value):
        if type == 'int':
            try:
                int(value)
            except ValueError:
                raise ValueError('Argument_Value \'{}\' is not of the type'
                                 ' \'{}\''.format(value, type))
        elif type == 'bool':
            if str(value) not in self.ACCEPTED_BOOLS:
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
            pass
            #raise ValueError('When the type is \'{}\', it should not have value'
            #                 .format(type))
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
    job_argument_instance = models.ForeignKey(Job_Argument_Instance,
                                              on_delete=models.CASCADE)

    def check_and_set_value(self, value):
        type = self.job_argument_instance.argument.type
        self._check_type_internal(type, value)
        if type == 'json':
            self.value = json.dumps(value)
        elif type == 'list':
            new_value = ''
            for v in value:
                if new_value == '':
                    new_value = '"{}"'.format(v)
                else:
                    new_value = '{} "{}"'.format(new_value, v)
                self.value = new_value
        else:
            self.value = value


class Watch(models.Model):
    job = models.ForeignKey(Installed_Job, on_delete=models.CASCADE)
    job_instance_id = models.IntegerField(primary_key=True)
    interval = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return 'Watch of Job Instance {0.job_instance_id} of {0.job}'.format(
            self)


class Openbach_Function(models.Model):
    name = models.CharField(max_length=500, primary_key=True)

    def __str__(self):
        return self.name


class Openbach_Function_Argument(Argument):
    openbach_function = models.ForeignKey(Openbach_Function, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'openbach_function'))


class Scenario(models.Model):
    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)
    scenario = models.TextField()
    project = models.ForeignKey('Project', null=True, blank=True)

    class Meta:
        unique_together = (('name', 'project'))

    def __str__(self):
        return self.name

    def get_json(self):
        return json.loads(self.scenario)


class Scenario_Argument(Argument):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)

    def check_or_set_type(self, type):
        if self.type is 'None':
            self.type = type
        else:
            if self.type != type:
                return False
        return True

    def save(self, *args, **kwargs):
        if self.type is 'None':
            raise BadRequest('This Scenario_Argument \'{}\' is unused'.format(
                self.name))
        super(Argument, self).save(*args, **kwargs)

    class Meta:
        unique_together = (('name', 'scenario'))


class Scenario_Instance(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE)
    status = models.CharField(max_length=500, null=True, blank=True)
    status_date = models.DateTimeField(null=True, blank=True)
    is_stopped = models.BooleanField(default=False)
    openbach_function_instance_master = models.ForeignKey(
        "Openbach_Function_Instance", null=True, blank=True,
        related_name='openbach_function_instance_master')

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
        elif type == 'list':
            new_value = ''
            for v in value:
                if new_value == '':
                    new_value = '"{}"'.format(v)
                else:
                    new_value = '{} "{}"'.format(new_value, v)
                self.value = new_value
        else:
            self.value = value

    class Meta:
        unique_together = (('argument', 'scenario_instance'))

    def __str__(self):
        return self.value


class Operand(ContentTyped):
    def get_value(self):
        if self.__class__ == Operand:
            if self.content_model:
                return self.get_content_model().get_value()
        raise NotImplementedError

    def save(self, *args, **kwargs):
        self.set_content_model()
        super(Operand, self).save(*args, **kwargs)


class Operand_Database(Operand):
    name = models.CharField(max_length=500)
    key = models.CharField(max_length=500)
    attribute = models.CharField(max_length=500)

    def get_value(self):
        model = globals()[self.name]
        data = model.objects.get(pk=self.key)
        return getattr(data, self.attribute)


class Operand_Value(Operand):
    TRUE = frozenset({'True', 'true', 'TRUE'})
    FALSE = frozenset({'False', 'false', 'FALSE'})

    value = models.CharField(max_length=500)

    def get_value(self):
        value = self.value
        try:
            value = float(self.value)
        except ValueError:
            pass
        if self.value in self.TRUE:
            return True
        if self.value in self.FALSE:
            return False
        return value


class Operand_Statistic(Operand):
    UPDATE_STAT_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("{stat.field}")+FROM+"{stat.measurement}"'
    measurmement = models.CharField(max_length=500)
    field = models.CharField(max_length=500)

    def get_value(self, agent):
        url = self.UPDATE_STAT_URL.format(agent=agent, stat=self)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            raise BadRequest('Required Stats doesn\'t exist in the Database')

        for column, value in zip(columns, values):
            if column == 'last':
                return value


class Condition(ContentTyped):
    def get_value(self):
        if self.__class__ == Condition:
            if self.content_model:
                return self.get_content_model().get_value()
        raise NotImplementedError

    def save(self, *args, **kwargs):
        self.set_content_model()
        super(Condition, self).save(*args, **kwargs)


class Condition_Not(Condition):
    condition = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='not_condition')

    def get_value(self):
        return not self.condition.get_value()


class Condition_Or(Condition):
    condition1 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='or_condition1')
    condition2 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='or_condition2')

    def get_value(self):
        return self.condition1.get_value() or self.condition2.get_value()


class Condition_And(Condition):
    condition1 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='and_condition1')
    condition2 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='and_condition2')

    def get_value(self):
        return self.condition1.get_value() and self.condition2.get_value()


class Condition_Xor(Condition):
    condition1 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='xor_condition1')
    condition2 = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  related_name='xor_condition2')

    def get_value(self):
        return (self.condition1.get_value() or self.condition2.get_value()) and not (self.condition1.get_value() and self.condition2.get_value())


class Condition_Equal(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='equal_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='equal_operand2')

    def get_value(self):
        return self.operand1.get_value() == self.operand2.get_value()


class Condition_Unequal(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='unequal_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='unequal_operand2')

    def get_value(self):
        return self.operand1.get_value() != self.operand2.get_value()


class Condition_Below_Or_Equal(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='boe_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='boe_operand2')

    def get_value(self):
        return self.operand1.get_value() <= self.operand2.get_value()


class Condition_Below(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='below_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='below_operand2')

    def get_value(self):
        return self.operand1.get_value() < self.operand2.get_value()


class Condition_Upper_Or_Equal(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='uoe_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='uoe_operand2')

    def get_value(self):
        return self.operand1.get_value() >= self.operand2.get_value()


class Condition_Upper(Condition):
    operand1 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='upper_operand1')
    operand2 = models.ForeignKey(Operand, on_delete=models.CASCADE,
                                  related_name='upper_operand2')

    def get_value(self):
        return self.operand1.get_value() > self.operand2.get_value()


class Openbach_Function_Instance(models.Model):
    openbach_function = models.ForeignKey(Openbach_Function, on_delete=models.CASCADE)
    scenario_instance = models.ForeignKey(Scenario_Instance, on_delete=models.CASCADE)
    condition = models.ForeignKey(Condition, on_delete=models.CASCADE,
                                  null=True, blank=True)
    openbach_function_instance_id = models.IntegerField()
    status = models.CharField(max_length=500, null=True, blank=True)
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
        elif type == 'list':
            new_value = ''
            for v in value:
                if new_value == '':
                    new_value = '"{}"'.format(v)
                else:
                    new_value = '{} "{}"'.format(new_value, v)
                self.value = new_value
        else:
            self.value = value

    def __str__(self):
        return self.value


class Project(models.Model):
    name = models.CharField(max_length=500, primary_key=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.name

    def get_json(self):
        info_json = {
            'name': self.name,
            'description': self.description,
            'machine': [],
            'scenario': [],
            'network': []
        }
        for machine in self.machine_set.all():
            info_json['machine'].append(machine.get_json())
        for network in self.network_set.all():
            info_json['network'].append(network.get_json())
        for scenario in self.scenario_set.all():
            info_json['scenario'].append(scenario.get_json())
        return info_json


class Network(models.Model):
    name = models.CharField(max_length=500)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    class Meta:
        unique_together = (('name', 'project'))

    def __str__(self):
        return '{} for Project {}'.format(self.name, self.project.name)

    def get_json(self):
        return self.name


class Machine(models.Model):
    name = models.CharField(max_length=500)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    description = models.TextField(null=True, blank=True)
    agent = models.ForeignKey(Agent, null=True, blank=True)
    networks = models.ManyToManyField(Network)

    class Meta:
        unique_together = (('name', 'project'))

    def __str__(self):
        return '{} for Project {}'.format(self.name, self.project.name)

    def get_json(self):
        info_json = {
            'name': self.name,
            'description': self.description,
            'agent': None,
            'networks': []
        }
        for network in self.networks.all():
            info_json['networks'].append(network.get_json())
        if self.agent:
            info_json['agent'] = self.agent.get_json()
        return info_json

