#!/usr/bin/python3
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



   @file     rstats.py
   @brief    The Collect-Agent (for the stats)
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import threading
import logging
import socket
import shlex
import os.path
import time
from configparser import ConfigParser
import yaml
from collections import namedtuple, defaultdict
try:
    import simplejson as json
except ImportError:
    import json

import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

BOOLEAN_TRUE = frozenset({'t', 'T', 'true', 'True', 'TRUE'})
BOOLEAN_FALSE = frozenset({'f', 'F', 'false', 'False', 'FALSE'})


class BadRequest(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class StatsManager:
    __shared_state = {'stats': {}, 'lookup': {}, 'mutex': threading.Lock(), 'id': 0}

    def __init__(self):
        self.__dict__ = self.__class__.__shared_state

    def statistic_lookup(self, instance_id, scenario_id):
        id = self.lookup.get((instance_id, scenario_id))
        if id is None:
            with self.mutex:
                self.id += 1
                self.lookup[(instance_id, scenario_id)] = id = self.id
        return id

    def __getitem__(self, id):
        return self.stats[id]

    def __setitem__(self, id, statistic):
        with self.mutex:
            self.stats[id] = statistic

    def __delitem__(self, id):
        with self.mutex:
            del self.stats[id]

    def __iter__(self):
        with self.mutex:
            yield from self.stats.items()


class Rstats:
    def __init__(self, logpath='/var/openbach_stats/', confpath='', conf=None,
                 suffix=None, id=None, job_name=None, job_instance_id=0,
                 scenario_instancd_id=0, agent_name='agent_name_not_found'):
        self._mutex = threading.Lock()
        self.conf = conf
        self.job_instance_id = job_instance_id
        self.scenario_instance_id = scenario_instance_id
        self.job_name = 'rstats' if job_name is None else job_name
        self.agent_name = agent_name
        self.suffix = suffix

        logger_name = 'Rstats' if id is None else 'Rstats{}'.format(id)
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)

        date = time.strftime("%Y-%m-%dT%H%M%S")
        logfile = os.path.join(
            logpath, '{0}/{0}_{1}.stats'.format(self.job_name, date))
        try:
            fhd = logging.FileHandler(logfile, mode='a')
            fhd.setFormatter(logging.Formatter('{message}', style='{'))
            self._logger.addHandler(fhd)
        except:  # [Mathias] except What?
            pass

        self._confpath = confpath
        self.reload_conf()

    def _is_broadcast_denied(self, stat_name):
        for rule in self._rules:
            if rule.name == stat_name:
                return rule.broadcast == RstatsRule.DENY
        return self._default_broadcast == RstatsRule.DENY

    def _is_storage_denied(self, stat_name):
        for rule in self._rules:
            if rule.name == stat_name:
                return rule.storage == RstatsRule.DENY
        return self._default_storage == RstatsRule.DENY

    def _send_tcp(self, data):
        try:
            # Creer la socket tcp
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            raise BadRequest('Failed to create socket')

        try:
            # Se connecter au serveur
            s.connect((self.conf.host, int(self.conf.port)))
        except socket.error:
            raise BadRequest('Failed to connect to server')

        # Envoyer les donnees
        s.send(data.encode())

        # Fermer la socket
        s.close()

    def _send_udp(self, data):
        try:
            # Creer la socket udp
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error:
            raise BadRequest('Failed to create socket')

        try:
            # Envoyer la commande
            s.sendto(data.encode(), (self.conf.host, int(self.conf.port)))
        except socket.error as msg:
            raise BadRequest('Error code: {}, Message {}'.format(*msg))

    def send_stat(self, suffix, stats):
        self._mutex.acquire()
        measurement_name = '{}.{}.{}.{}'.format(
            self.scenario_instance_id, self.job_instance_id, self.agent_name,
            self.job_name)
        if suffix is not None:
            measurement_name = '{}.{}'.format(measurement_name, suffix)

        # recuperation des stats
        time = str(stats['time'])
        del stats['time']

        flags = {0: [], 1: [], 2: [], 3: []}
        for stat_name, value in stats.items():
            flag = 0
            if not self._is_storage_denied(stat_name):
                flag += 1
            if not self._is_broadcast_denied(stat_name):
                flag += 2
            try:
                statistic = {stat_name: float(value)}
            except ValueError:
                # TODO: Gerer les vrais booleens dans influxdb (voir avec la
                #       conf de logstash aussi)
                if value in BOOLEAN_TRUE:
                    statistic = {stat_name: True}
                elif value in BOOLEAN_FALSE:
                    statistic = {stat_name: False}
                else:
                    statistic = {stat_name: value}
            flags[flag].append(statistic)
        for flag, statistics in flags.items():
            stats_to_send = {
                'time': time,
                'flag': flag
            }
            stats_to_log = stats_to_send.copy()
            stats_to_log['job_name'] = self.job_name
            stats_to_log['job_instance_id'] = self.job_instance_id
            stats_to_log['scenario_instance_id'] = self.scenario_instance_id
            if suffix is not None:
                stats_to_log['suffix'] = suffix
            for statistic in statistics:
                stats_to_send = {'measurement_name': measurement_name, 
                                 **stats_to_send, **statistic}
                stats_to_log = {**stats_to_log, **statistic}
                try:
                    send_function = {'udp': self._send_udp, 'tcp':
                                     self._send_tcp}[self.conf.mode]
                except KeyError:
                    raise BadRequest('Mode not known')
            if statistics:
                if flag != 0:
                    send_function(json.dumps(stats_to_send))
                self._logger.info(json.dumps(stats_to_log))
        self._mutex.release()

    def reload_conf(self):
        self._mutex.acquire()

        self._default_storage = RstatsRule.ACCEPT
        self._default_broadcast = RstatsRule.ACCEPT
        self._rules = []
        try:
            # Read file lines
            config = ConfigParser()
            config.read(self._confpath)
            for name in config.sections():
                value = config[name].getboolean('storage')
                storage = RstatsRule.ACCEPT if value else RstatsRule.DENY
                value = config[name].getboolean('broadcast')
                broadcast = RstatsRule.ACCEPT if value else RstatsRule.DENY
                if name == 'default':
                    self._default_storage = storage
                    self._default_broadcast = broadcast
                else:
                    self._rules.append(RstatsRule(name, storage, broadcast))
        except Exception:
            pass

        self._mutex.release()


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return zip(*args)


class Conf:
    def __init__(self, conf_path, collector_conf):
        with open(conf_path) as stream:
            content = yaml.load(stream)
        self.mode = content['logstash']['mode']
        with open(collector_conf) as stream:
            content = yaml.load(stream)
        self.host = content['address']
        self.port = content['stats']['port']


class RstatsRule(namedtuple('RstatsRule', 'name storage broadcast')):
    ACCEPT = True
    DENY = False

    def __str__(self):
        return 'storage: {}, broadcast: {} for {}'.format('ACCEPT' if
                                                          self.storage else
                                                          'DENY', 'ACCEPT' if
                                                          self.broadcast else
                                                          'DENY', self.name)


class ClientThread(threading.Thread):
    def __init__(self, data, client_addr, conf):
        super().__init__()
        self.data = data
        self.client = client_addr
        self.conf = conf

    def parse_and_check(self, data):
        data_received = shlex.split(data)
        try:
            request_type = int(data_received[0])
        except (ValueError, IndexError):
            raise BadRequest('KO Type not recognize')

        bounds = [(6, 7), (5, None), (2, 2), (2, 2), (1, 1), (5, 5)]
        minimum, maximum = bounds[request_type - 1]

        length = len(data_received)
        if length < minimum:
            raise BadRequest(
                    'KO Message not formed well. Not enough arguments.')

        if maximum is not None and length > maximum:
            raise BadRequest(
                    'KO Message not formed well. Too much arguments.')

        if request_type == 1:  # create stats
            try:
                # convert job_instance_id, scenario_instance_id and new
                data_received[2:5] = map(int, data_received[2:5])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Third, forth'
                        'and fifth arguments should be integers.')
        if request_type == 2:  # send stats
            try:
                # convert stat id
                data_received[1] = int(data_received[1])
                # convert timestamp
                data_received[2] = int(data_received[2])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Second and '
                        'third arguments should be integers.')
        elif request_type == 3 of request_type == 4:  # reload and remove stat
            try:
                # convert stat id
                data_received[1] = int(data_received[1])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Second '
                        'argument should be an integer.')
        elif request_type == 6:  # change config
            try:
                data_received[1:5] = map(int, data_received[1:5])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. All '
                        'arguments should be integers.')

        data_received[0] = request_type
        return data_received

    def create_stat(self, confpath, job, job_instance_id, scenario_instance_id,
                    agent_name, new=False):
        manager = StatsManager()
        id = manager.statistic_lookup(job_instance_id, scenario_instance_id)

        try:
            if new:
                raise KeyError()
            stats_client = manager[id]
        except KeyError:
            # creer le rstatsclient
            stats_client = Rstats(
                    confpath=confpath,
                    job_name=job,
                    id=id,
                    instance=job_instance_id,
                    scenario=scenario_instance_id,
                    agent_name=agent_name,
                    conf=self.conf)

            manager[id] = stats_client

        # envoyer OK
        return id

    def send_stat(self, id, time, *extra_stats):
        # recuperer le rstatsclient et son mutex
        try:
            stats_client = StatsManager()[id]
        except KeyError:
            raise BadRequest(
                    'KO The given id doesn\'t '
                    'represent an open connection')

        # Recuperer l'eventuel suffix
        if len(extra_stats) % 2:
            suffix = extra_stats[-1]
            extra_stats = extra_stats[:-1]
        else:
            suffix = None

        # recuperer les stats
        stats = {key: value for key, value in grouper(extra_stats, 2)}
        stats['time'] = time
        # send les stats
        stats_client.send_stat(suffix, stats)

    def reload_stat(self, id):
        # recuperer le rstatsclient et son mutex
        try:
            stats_client = StatsManager()[id]
        except KeyError:
            raise BadRequest(
                    'KO The given id doesn\'t '
                    'represent an open connection')
        # reload la conf
        stats_client.reload_conf()

    def remove_stat(self, id):
        try:
            del StatsManager()[id]
        except KeyError:
            raise BadRequest(
                    'KO The given id doesn\'t '
                    'represent an open connection')

    def reload_stats(self):
        for _, stats_client in StatsManager():
            # reload la conf
            stats_client.reload_conf()

    def change_config(self, job_instance_id, scenario_instance_id, broadcast,
                      storage):
        manager = StatsManager()
        id = manager.statistic_lookup(job_instance_id, scenario_instance_id)
        try:
            stats_client = manager[id]
        except KeyError:
            raise BadRequest('KO No connection is available for these ids')
        stats_client._default_storage = storage
        stats_client._default_broadcast = broadcast

    def execute_request(self, data): 
        request, *args = self.parse_and_check(data)
        functions = [
                self.create_stat,
                self.send_stat,
                self.reload_stat,
                self.remove_stat,
                self.reload_stats,
                self.change_config,
        ]
        return functions[request-1](*args)

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            result = self.execute_request(self.data.decode())
        except BadRequest as e:
            sock.sendto(e.reason.encode(), self.client)
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
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(('', 1111))

    conf = Conf('/opt/rstats/rstats.yml', '/opt/openbach-agent/collector.yml')

    while True:
        data, remote = udp_socket.recvfrom(2048)
        ClientThread(data, remote, conf).start()

