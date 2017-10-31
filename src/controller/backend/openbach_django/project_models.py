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
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''


from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

from .scenario_models import Scenario
from .utils import nullable_json


class Collector(models.Model):
    """Data associated to a Collector"""

    address = models.GenericIPAddressField(primary_key=True)
    logs_port = models.IntegerField(default=10514)
    logs_query_port = models.IntegerField(default=9200)
    logs_database_name = models.CharField(max_length=500, default='openbach')
    stats_port = models.IntegerField(default=2222)
    stats_query_port = models.IntegerField(default=8086)
    stats_database_name = models.CharField(max_length=500, default='openbach')
    stats_database_precision = models.CharField(max_length=10, default='ms')
    logstash_broadcast_mode = models.CharField(
            max_length=3, default='udp', choices=(('udp', 'UDP'), ('tcp', 'TCP')))
    logstash_broadcast_port = models.IntegerField(default=2223)

    def __str__(self):
        return self.address

    def update(self, logs_port=None, logs_query=None, logs_cluster=None,
               stats_port=None, stats_query=None, database_name=None,
               database_precision=None, broadcast=None, broadcast_port=None):
        new_values = {
                'logs_port': logs_port,
                'logs_query_port': logs_query,
                'logs_database_name': logs_cluster,
                'stats_port': stats_port,
                'stats_query_port': stats_query,
                'stats_database_name': database_name,
                'stats_database_precision': database_precision,
                'logstash_broadcast_mode': broadcast,
                'logstash_broadcast_port': broadcast_port,
        }

        updated = False
        for attribute_name, value in new_values.items():
            if value is not None:
                updated = True
                setattr(self, attribute_name, value)

        self.save()
        return updated

    @property
    def json(self):
        return {
                'address': self.address,
                'logs_port': self.logs_port,
                'logs_query_port': self.logs_query_port,
                'logs_database_name': self.logs_database_name,
                'stats_port': self.stats_port,
                'stats_query_port': self.stats_query_port,
                'stats_database_name': self.stats_database_name,
                'stats_database_precision': self.stats_database_precision,
                'logstash_broadcast_mode': self.logstash_broadcast_mode,
                'logstash_broadcast_port': self.logstash_broadcast_port,
        }


class Agent(models.Model):
    """Data associated to an Agent"""

    name = models.CharField(max_length=500, unique=True)
    address = models.GenericIPAddressField(primary_key=True)
    status = models.CharField(max_length=500, null=True, blank=True)
    update_status = models.DateTimeField(null=True, blank=True)
    reachable = models.BooleanField(default=False)
    update_reachable = models.DateTimeField(null=True, blank=True)
    available = models.BooleanField(default=False)
    update_available = models.DateTimeField(null=True, blank=True)
    collector = models.ForeignKey(Collector, related_name='agents')

    def set_status(self, status):
        self.status = status
        self.update_status = timezone.now()

    def set_reachable(self, reachable):
        self.reachable = reachable
        self.update_reachable = timezone.now()

    def set_available(self, available):
        self.available = available
        self.update_available = timezone.now()

    def __str__(self):
        return '{0.name} ({0.address})'.format(self)

    @property
    def has_entity(self):
        try:
            self.entity
        except Entity.DoesNotExist:
            return False
        return True

    @property
    def json(self):
        try:
            entity = self.entity
        except Entity.DoesNotExist:
            project = None
        else:
            project = entity.project.name

        return {
                'name': self.name,
                'address': self.address,
                'collector_ip': self.collector.address,
                'reachable': self.reachable,
                'available': self.available,
                'status': self.status,
                'project': project,
        }


class Project(models.Model):
    """Data associated to an OpenBACH Project"""

    name = models.CharField(max_length=500, primary_key=True)
    description = models.TextField(null=True, blank=True)
    owners = models.ManyToManyField(User, related_name='private_projects')

    class MalformedError(Exception):
        def __init__(self, section, error):
            message = 'Project is malformed'
            super().__init__(message)
            self.error = {
                    'error': message,
                    'section': section,
                    'message': error,
            }

    def __str__(self):
        return self.name

    @property
    def json(self):
        return {
                'name': self.name,
                'description': self.description,
                'owners': [user.get_username() for user in self.owners.all()],
                'entity': [
                    entity.json for entity
                    in self.entities.order_by('name')
                ],
                'scenario': [
                    scenario.json for scenario
                    in self.scenarios.order_by('name')
                ],
                'network': [
                    network.json for network
                    in self.networks.order_by('name')
                ],
                'hidden_network': [
                    hidden_network.name for hidden_network
                    in self.hidden_networks.order_by('name')
                ],
        }

    def load_from_json(self, json_data):
        owners = json_data.get('owners', [])
        if not isinstance(owners, list):
            raise Project.MalformedError(
                    'owners', 'Entry \'owners\' has '
                    'the wrong kind of value (expected '
                    '{} got {})'.format(list, type(owners)))

        entities = json_data.get('entity', [])
        if not isinstance(entities, list):
            raise Project.MalformedError(
                    'entity', 'Entry \'entity\' has '
                    'the wrong kind of value (expected '
                    '{} got {})'.format(list, type(entities)))

        hidden_networks = json_data.get('hidden_network', [])
        if not isinstance(hidden_networks, list):
            raise Project.MalformedError(
                    'hidden_network', 'Entry \'hidden_network\''
                    ' has the wrong kind of value (expected '
                    '{} got {})'.format(list, type(hidden_networks)))

        entity_data = {}
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                raise Project.MalformedError(
                        'entity.{}'.format(index), 'Entry '
                        '\'entity\' should contain only dict '
                        'values (found {})' .format(type(entity)))
            try:
                name = entity['name']
            except KeyError:
                raise Project.MalformedError(
                        'entity.{}'.format(index), 'Entity '
                        'data should contain the name of the '
                        'entity to create.')
            entity_data[name] = entity

        entity_names = set(entity_data)
        existing_entity_names = {entity.name for entity in self.entities.all()}
        # Cleanup of old, unused entities and hidden networks
        self.entities.filter(name__in=existing_entity_names - entity_names).delete()
        self.hidden_networks.all().delete()
        # Update reused entities' description
        for entity in self.entities.filter(name__in=existing_entity_names & entity_names):
            entity_json = entity_data[entity.name]
            entity.description = entity_json.get('description')
            entity.save()
        # Creation of new entities
        for entity_name in entity_names - existing_entity_names:
            entity_json = entity_data[entity_name]
            description = entity_json.get('description')
            entity = Entity.objects.create(
                    name=entity_name, project=self,
                    description=description)
        # Creation of hidden networks
        for hidden_network_name in hidden_networks:
            HiddenNetwork.objects.get_or_create(
                    name=hidden_network_name, project=self)

        scenarios = json_data.get('scenario', [])
        for index, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                raise Project.MalformedError(
                        'scenario.{}'.format(index), 'Entry '
                        '\'scenario\' should contain only dict '
                        'values (found {})' .format(type(scenario)))
            try:
                name = scenario['name']
            except KeyError:
                raise Project.MalformedError(
                        'scenario.{}'.format(index), 'Scenario '
                        'data should contain the name of the '
                        'scenario to create.')
            description = scenario.get('description')
            scenario_instance, _ = Scenario.objects.get_or_create(
                    name=name, project=self,
                    defaults={'description': description})
            scenario_instance.description = description
            scenario_instance.save()
            try:
                scenario_instance.load_from_json(scenario)
            except Scenario.MalformedError as e:
                raise Project.MalformedError('scenario.{}'.format(name), e.error)


class Network(models.Model):
    """Data associated to a Network"""

    name = models.CharField(max_length=500)
    address = models.CharField(max_length=500)
    project = models.ForeignKey(
            Project,
            models.CASCADE,
            related_name='networks')

    class Meta:
        unique_together = (('address', 'project'))

    def __str__(self):
        return '{} for Project {}'.format(self.name, self.project)

    @property
    def json(self):
        return {
                'name': self.name,
                'address': self.address,
        }

class HiddenNetwork(models.Model):
    """Data associated to a Network"""

    name = models.CharField(max_length=500)
    project = models.ForeignKey(
            Project,
            models.CASCADE,
            related_name='hidden_networks')

    class Meta:
        unique_together = (('name', 'project'))

    def __str__(self):
        return '{} for Project {}'.format(self.name, self.project)


class Entity(models.Model):
    """Data associated to an Entity"""

    name = models.CharField(max_length=500)
    description = models.TextField(null=True, blank=True)
    networks = models.ManyToManyField(Network, related_name='entities')
    project = models.ForeignKey(
            Project,
            models.CASCADE,
            related_name='entities')
    agent = models.OneToOneField(
            Agent,
            models.SET_NULL,
            null=True, blank=True,
            related_name='entity')

    class Meta:
        unique_together = (('name', 'project'))

    def __str__(self):
        return '{} for Project {}'.format(self.name, self.project)

    @property
    def json(self):
        return {
                'name': self.name,
                'description': self.description,
                'agent': nullable_json(self.agent),
                'networks': [network.json for network in self.networks.all()]
        }
