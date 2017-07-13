#!/usr/bin/python3

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


"""RStats daemon

This module defines the necessary building blocks to receive, tag and
route the various statistics generated by the jobs part of the OpenBACH
testbed.
"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import threading
import logging
import socket
import shlex
import os.path
import functools
import contextlib
import configparser
from itertools import groupby
from time import strftime
from collections import namedtuple
try:
    import simplejson as json
except ImportError:
    import json

import yaml


DEFAULT_LOG_PATH = '/var/openbach_stats/'
RSTATS_CONFIG_FILE = '/opt/rstats/rstats.yml'
COLLECTOR_CONFIG_FILE = '/opt/openbach/agent/collector.yml'

BOOLEAN_TRUE = frozenset({'t', 'T', 'true', 'True', 'TRUE'})
BOOLEAN_FALSE = frozenset({'f', 'F', 'false', 'False', 'FALSE'})


def grouper(iterable, n):
    """Group items of `iterable` n by n. Generate tuples of size n."""
    args = [iter(iterable)] * n
    return zip(*args)


class BadRequest(ValueError):
    """Base exception for this module"""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


@functools.lru_cache(maxsize=1)
def get_statistics_sender():
    """Build the function that will route data to the logstash
    server based on the provided configuration files.
    """

    with open(COLLECTOR_CONFIG_FILE) as stream:
        content = yaml.load(stream)
    host = content['address']
    port = content['stats']['port']
    address = (host, int(port))

    # Build functions to send stats to the configured address

    @contextlib.contextmanager
    def socket_error_to_bad_request(message):
        """Helper context manager aimed at reducing boilerplate code"""
        try:
            yield
        except socket.error as err:
            raise BadRequest(message.format(*err))

    def send_udp(data):
        with socket_error_to_bad_request('Failed to create socket'):
            logstash = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        with logstash:
            with socket_error_to_bad_request('Error code: {}, Message {}'):
                logstash.sendto(data.encode(), address)

    def send_tcp(data):
        with socket_error_to_bad_request('Failed to create socket'):
            logstash = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        with logstash:
            with socket_error_to_bad_request('Failed to connect to server'):
                logstash.connect(address)
            with socket_error_to_bad_request('Error code: {}, Message {}'):
                logstash.send(data.encode())

    with open(RSTATS_CONFIG_FILE) as stream:
        content = yaml.load(stream)

    # Select the right function to use based on the configured mode
    try:
        return {
            'tcp': send_tcp,
            'udp': send_udp,
        }[content['logstash']['mode']]
    except KeyError:
        raise BadRequest('Mode not known')


class Rstats:
    def __init__(self, logpath=DEFAULT_LOG_PATH, confpath='',
                 suffix=None, id=None, job_name=None, job_instance_id=0,
                 scenario_instance_id=0, owner_scenario_instance_id=0,
                 agent_name='agent_name_not_found'):
        self._mutex = threading.Lock()
        self.metadata = {
                'job_name': 'rstats' if job_name is None else job_name,
                'agent_name': agent_name,
                'job_instance_id': job_instance_id,
                'scenario_instance_id': scenario_instance_id,
                'owner_scenario_instance_id': owner_scenario_instance_id,
        }
        if suffix is not None:
            self.metadata['suffix'] = suffix

        logger_name = 'Rstats' if id is None else 'Rstats{}'.format(id)
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        date = strftime("%Y-%m-%dT%H%M%S")
        filename = '{}_{}.stats'.format(self.metadata['job_name'], date)
        logfile = os.path.join(logpath, self.metadata['job_name'], filename)
        try:
            fhd = logging.FileHandler(logfile, mode='a')
        except OSError:
            pass
        else:
            fhd.setFormatter(logging.Formatter('{message}\n', style='{'))
            self._logger.addHandler(fhd)

        self._confpath = confpath
        self.reload_conf()

    def reload_conf(self):
        config = configparser.ConfigParser()
        with self._mutex:
            self._rules = {'default': RstatsRule('default',
                                                 RstatsRule.ACCEPT,
                                                 RstatsRule.ACCEPT)}
            try:
                config.read(self._confpath)
            except configparser.Error:
                return

            self._rules.update(
                    (name, RstatsRule(name,
                                      section.getboolean('storage'),
                                      section.getboolean('broadcast')))
                    for name, section in config.items()
            )

    def send_stat(self, suffix, time, stats):
        with self._mutex:
            statistics_metadata = {'time': time, **self.metadata}
            if suffix is not None:
                statistics_metadata['suffix'] = suffix

            statistics_by_flag = sorted((
                {statistic_name: self._parse(value)}
                for statistic_name, value in stats.items()
            ), key=self._get_flag)

            for flag, statistics_group in groupby(statistics_by_flag, self._get_flag):
                statistics_metadata['flag'] = flag
                statistics = {
                        k: v
                        for statistic in statistics_group
                        for k, v in statistic.items()
                }
                statistics['_metadata'] = statistics_metadata
                message_to_send = json.dumps(statistics)
                if flag != 0:
                    get_statistics_sender()(message_to_send)
                self._logger.info(message_to_send)

    def _get_flag(self, statistic_holder):
        statistic_name, = statistic_holder
        try:
            return self._rules[statistic_name].flag
        except KeyError:
            return self._rules['default'].flag

    @staticmethod
    def _parse(statistic_value):
        with contextlib.suppress(ValueError):
            return int(statistic_value)
        with contextlib.suppress(ValueError):
            return float(statistic_value)
        if statistic_value in BOOLEAN_TRUE:
            return True
        if statistic_value in BOOLEAN_FALSE:
            return False
        return statistic_value


class RstatsRule(namedtuple('RstatsRule', 'name storage broadcast')):
    ACCEPT = True
    DENY = False

    @property
    def flag(self):
        return bool(self.storage) + 2 * bool(self.broadcast)

    @staticmethod
    def _rule_to_str(rule_value):
        return 'ACCEPT' if rule_value else 'DENY'

    def __str__(self):
        return 'storage: {}, broadcast: {} for {}'.format(
                self._rule_to_str(self.storage),
                self._rule_to_str(self.broadcast),
                self.name)


class StatsManager:
    """Borg storing the connections opened with the daemon"""

    __shared_state = {
            'stats': {},
            'cache': {},
            'mutex': threading.Lock(),
            'id': 0,
    }

    def __init__(self):
        self.__dict__ = self.__class__.__shared_state

    def statistic_lookup(self, instance_id, scenario_id):
        key = (instance_id, scenario_id)
        with self.mutex:
            try:
                return self.cache[key]
            except KeyError:
                self.id += 1
                self.cache[key] = self.id
                return self.id

    @contextlib.contextmanager
    def _id_check(self):
        try:
            yield
        except KeyError:
            raise BadRequest("The given id doesn't represent an open connection")

    def __getitem__(self, id_):
        with self._id_check():
            return self.stats[id_]

    def __setitem__(self, id_, statistic):
        with self.mutex:
            self.stats[id_] = statistic

    def __delitem__(self, id_):
        with self.mutex, self._id_check():
            del self.stats[id_]

    def __iter__(self):
        with self.mutex:
            yield from self.stats.items()


class ClientThread(threading.Thread):
    def __init__(self, data, client_addr):
        super().__init__()
        self.data = data
        self.client = client_addr

    @contextlib.contextmanager
    def _handle_parse_errors(self, name, expected_type):
        try:
            yield
        except ValueError:
            raise BadRequest('Message not formed well. Argument {} should '
                             'be of type {}'.format(name, expected_type))

    def create_stat(self, confpath, job, job_instance_id, scenario_instance_id,
                    owner_scenario_instance_id, agent_name, new=False):
        # Type conversion
        with self._handle_parse_errors('job_instance_id', 'integer'):
            job_instance_id = int(job_instance_id)
        with self._handle_parse_errors('scenario_instance_id', 'integer'):
            scenario_instance_id = int(scenario_instance_id)
        with self._handle_parse_errors('owner_scenario_instance_id', 'integer'):
            owner_scenario_instance_id = int(owner_scenario_instance_id)
        with self._handle_parse_errors('new', 'boolean'):
            new = bool(int(new))

        manager = StatsManager()
        statistic_id = manager.statistic_lookup(job_instance_id, scenario_instance_id)

        if not new:
            try:
                manager[statistic_id]
            except BadRequest:
                new = True

        if new:
            manager[statistic_id] = Rstats(
                    confpath=confpath,
                    job_name=job,
                    id=statistic_id,
                    job_instance_id=job_instance_id,
                    scenario_instance_id=scenario_instance_id,
                    owner_scenario_instance_id=owner_scenario_instance_id,
                    agent_name=agent_name)

        return statistic_id

    def send_stat(self, connection_id, timestamp, *statistics):
        # Type conversion
        with self._handle_parse_errors('connection_id', 'integer'):
            connection_id = int(connection_id)
        with self._handle_parse_errors('timestamp', 'integer'):
            timestamp = int(timestamp)

        client_connection = StatsManager()[connection_id]
        suffix = statistics[-1] if len(statistics) % 2 else None
        statistics = dict(grouper(statistics, 2))
        client_connection.send_stat(suffix, timestamp, statistics)

    def reload_stat(self, connection_id):
        # Type conversion
        with self._handle_parse_errors('connection_id', 'integer'):
            connection_id = int(connection_id)

        client_connection = StatsManager()[connection_id]
        client_connection.reload_conf()

    def remove_stat(self, connection_id):
        # Type conversion
        with self._handle_parse_errors('connection_id', 'integer'):
            connection_id = int(connection_id)

        del StatsManager()[connection_id]

    def reload_stats(self):
        for _, client_connection in StatsManager():
            client_connection.reload_conf()

    def change_config(self, scenario_instance_id, job_instance_id, broadcast, storage):
        # Type conversion
        with self._handle_parse_errors('job_instance_id', 'integer'):
            job_instance_id = int(job_instance_id)
        with self._handle_parse_errors('scenario_instance_id', 'integer'):
            scenario_instance_id = int(scenario_instance_id)
        with self._handle_parse_errors('broadcast', 'boolean'):
            broadcast = bool(int(broadcast))
        with self._handle_parse_errors('storage', 'boolean'):
            storage = bool(int(storage))

        manager = StatsManager()
        id = manager.statistic_lookup(job_instance_id, scenario_instance_id)
        client_connection = manager[id]
        client_connection._rules['default'] = RstatsRule('default', storage, broadcast)

    def execute_request(self, data):
        try:
            request, *args = shlex.split(data)
            request = int(request) - 1  # Compensate for collect_agent using 1-based indexing
        except ValueError:
            raise BadRequest('Type of request not recognized')

        functions = [
                self.create_stat,
                self.send_stat,
                self.reload_stat,
                self.remove_stat,
                self.reload_stats,
                self.change_config,
        ]
        if request not in range(len(functions)):
            raise BadRequest('Type of request not recognized')

        try:
            return functions[request](*args)
        except TypeError as e:
            raise BadRequest('Arguments length mismatch: {}'.format(e))

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            result = self.execute_request(self.data.decode())
        except BadRequest as e:
            msg = 'KO: {}\0'.format(e.reason)
            sock.sendto(msg.encode(), self.client)
        except Exception as e:
            msg = 'KO: An error occured: {}\0'.format(e)
            sock.sendto(msg.encode(), self.client)
        else:
            if result is None:
                sock.sendto(b'OK\0', self.client)
            else:
                msg = 'OK {}\0'.format(result)
                sock.sendto(msg.encode(), self.client)
        finally:
            sock.close()


if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('', 1111))

    while True:
        data, remote = udp_socket.recvfrom(2048)
        ClientThread(data, remote).start()
