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
                 prefix=None, id=None, job_name=None, instance=0, scenario=0):
        self._mutex = threading.Lock()
        self.conf = conf
        self.job_instance_id = instance
        self.scenario_instance_id = scenario
        self.job_name = 'rstats' if job_name is None else job_name
        self.prefix = self.conf.prefix if prefix is None else prefix

        logger_name = 'Rstats' if id is None else 'Rstats{}'.format(id)
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)

        date = time.strftime("%Y-%m-%dT%H%M%S")
        logfile = os.path.join(logpath, '{0}/{0}_{1}.stats'.format(self.job_name, date))
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

    def send_stat(self, stat_name, stats):
        self._mutex.acquire()
        flag = 0
        if not self._is_storage_denied(stat_name):
            flag += 1
        if not self._is_broadcast_denied(stat_name):
            flag += 2
        stat_name_with_prefix = '{}.{}.{}.{}'.format(self.scenario_instance_id,
                                                     self.job_instance_id,
                                                     self.prefix, stat_name)

        # recuperation des stats
        time = str(stats['time'])
        del stats['time']

        template = '"stat_name": "{}", "time": {}, "flag": {}, "job_instance_id": {}, "scenario_instance_id": {}'
        stats_to_send = '"stat_name": "{}", "time": {}, "flag": {}'.format(
            stat_name_with_prefix, time, flag)
        stats_to_log = template.format(
            stat_name, time, flag,
            self.job_instance_id, self.scenario_instance_id)
        statistics = ''
        for k, v in stats.items():
            try:
                float(v)
                statistics = '{}, "{}": {}'.format(statistics, k, v)
            except ValueError:
                # TODO: Gerer les vrais booleens dans influxdb (voir avec la
                #       conf de logstash aussi)
                if v in BOOLEAN_TRUE:
                    statistics = '{}, "{}": "true"'.format(statistics, k)
                elif v in BOOLEAN_FALSE:
                    statistics = '{}, "{}": "false"'.format(statistics, k)
                else:
                    statistics = '{}, "{}": "{}"'.format(statistics, k, v)
        stats_to_send = '{}{}{}{}'.format('{', stats_to_send, statistics, '}')
        stats_to_log = '{}{}{}{}'.format('{', stats_to_log, statistics, '}')
        try:
            send_function = {'udp': self._send_udp, 'tcp': self._send_tcp}[self.conf.mode]
        except KeyError:
            raise BadRequest('Mode not known')
        if flag != 0:
            send_function(stats_to_send)
        self._logger.info(stats_to_log)
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
        config = ConfigParser()
        config.read(conf_path)
        self.mode = config.get('logstash', 'mode')
        self.prefix = config.get('agent', 'prefix')
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

        bounds = [(5, 6), (6, None), (2, 2), (1, 1)]
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
                # convert job_instance_id
                data_received[3] = int(data_received[3])
                # convert scenario_instance_id
                data_received[4] = int(data_received[4])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Third and '
                        'forth arguments should be integers.')
        if request_type == 2:  # send stats
            if length % 2:
                raise BadRequest(
                        'KO Message not formed well. '
                        'Arguments should come in pairs.')
            else:
                try:
                    # convert stat id
                    data_received[1] = int(data_received[1])
                    # convert timestamp
                    data_received[3] = int(data_received[3])
                except ValueError:
                    raise BadRequest(
                            'KO Message not formed well. Second and '
                            'forth arguments should be integers.')
        elif request_type == 3:  # reload stat
            try:
                # convert stat id
                data_received[1] = int(data_received[1])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Second '
                        'argument should be an integer.')

        data_received[0] = request_type
        return data_received

    def create_stat(self, confpath, job, job_instance_id, scenario_instance_id,
                    new=False, prefix=None):
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
                    prefix=prefix,
                    id=id,
                    instance=job_instance_id,
                    scenario=scenario_instance_id,
                    conf=self.conf)

            manager[id] = stats_client

        # envoyer OK
        return id

    def send_stat(self, id, stat, time, *extra_stats):
        # recuperer le rstatsclient et son mutex
        try:
            stats_client = StatsManager()[id]
        except KeyError:
            raise BadRequest(
                    'KO The given id doesn\'t '
                    'represent an open connection')

        # recuperer les stats
        stats = {key: value for key, value in grouper(extra_stats, 2)}
        stats['time'] = time
        # send les stats
        stats_client.send_stat(stat, stats)

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

    def get_config(self):
        configs = defaultdict(set)
        for _, job_config in StatsManager():
            configs[job_config.job_name].add(job_config._confpath)
        return json.dumps({name: list(paths) for name, paths in configs.items()})

    def execute_request(self, data): 
        request, *args = self.parse_and_check(data)
        functions = [
                self.create_stat,
                self.send_stat,
                self.reload_stat,
                self.remove_stat,
                self.reload_stats,
                self.get_config,
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

    conf = Conf('/opt/rstats/rstats.cfg', '/opt/openbach-agent/collector.yml')

    while True:
        data, remote = udp_socket.recvfrom(2048)
        ClientThread(data, remote, conf).start()

