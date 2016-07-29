#!/usr/bin/python3

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
from collections import namedtuple

import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

BOOLEAN_TRUE = frozenset({'t', 'T', 'true', 'True', 'TRUE'})
BOOLEAN_FALSE = frozenset({'f', 'F', 'false', 'False', 'FALSE'})

class BadRequest(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class StatsManager:
    __shared_state = {}

    def __init__(self, init=False):
        self.__dict__ = self.__class__.__shared_state

        if init:
            self.stats = {}
            self.mutex = threading.Lock()
            self.id = 0

    def __enter__(self):
        self.mutex.acquire()
        return self.stats

    def __exit__(self, t, v, tb):
        self.mutex.release()

    def increment_id(self):
        self.id += 1
        return self.id


class Rstats:
    def __init__(self, logpath='/var/openbach_stats/', confpath='', conf=None,
                 prefix=None, id=None, job_name=None):
        self._mutex = threading.Lock()
        self.conf = conf
        self.job_name = 'rstats' if job_name is None else job_name
        self.prefix = self.conf.prefix if prefix is None else prefix

        logger_name = 'Rstats' if id is None else 'Rstats{}'.format(id)
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)

        date = time.strftime("%Y-%m-%dT%H%M%S")
        logfile = os.path.join(logpath, '{0}/{0}_{1}.stats'.format(self.job_name, date))
        try:
            fhd = logging.FileHandler(logfile, mode='a')
            fhd.setFormatter(logging.Formatter('{asctime} | {levelname} | {message}', style='{'))
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
        if self.prefix:
            stat_name = '{}.{}'.format(self.prefix, stat_name)

        # recuperation des stats
        time = str(stats['time'])
        del stats['time']
        formatted_header_log = [
                'Stat{{0}}{}'.format(stat_name),
                'Time{{0}}{}'.format(time),
        ]
        formatted_stats = ['{}{{0}}"{}"'.format(k, v) for k, v in stats.items()]
        logs = ', '.join(formatted_header_log).format(': ') + ', ' + ', '.join(formatted_stats).format(': ')
        self._logger.info(logs)

        if flag != 0:
            stats_to_send = '"stat_name": "{}", "time": {}, "flag": {}'.format(stat_name, time, flag)
            for k, v in stats.items():
                try:
                    float(v)
                    stats_to_send = '{}, "{}": {}'.format(stats_to_send, k, v)
                except ValueError:
                    # TODO: Gerer les vrais booleens dans influxdb (voir avec la
                    #       conf de logstash aussi)
                    if v in BOOLEAN_TRUE:
                        stats_to_send = '{}, "{}": "true"'.format(stats_to_send, k)
                    elif v in BOOLEAN_FALSE:
                        stats_to_send = '{}, "{}": "false"'.format(stats_to_send, k)
                    else:
                        stats_to_send = '{}, "{}": "{}"'.format(stats_to_send, k, v)
            stats_to_send = '{}{}{}'.format('{', stats_to_send, '}')
            try:
                send_function = {'udp': self._send_udp, 'tcp': self._send_tcp}[self.conf.mode]
            except KeyError:
                raise BadRequest('Mode not known')
            send_function(stats_to_send)
        self._mutex.release()

    def reload_conf(self):
        self._mutex.acquire()
        self._logger.info('Load new configuration:')

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

        for rule in self._rules:
            self._logger.info('    {}', rule)
        self._mutex.release()


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return zip(*args)


class Conf:
    def __init__(self, conf_path='config.ini'):
        config = ConfigParser()
        config.read(conf_path)
        self.host = config.get('logstash', 'host')
        self.port = config.get('logstash', 'port')
        self.mode = config.get('logstash', 'mode')
        self.prefix = config.get('agent', 'prefix')


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
    def __init__(self, client_socket, conf):
        super().__init__()
        self.socket = client_socket
        self.conf = conf

    def parse_and_check(self, data):
        data_received = shlex.split(data)
        try:
            request_type = int(data_received[0])
        except (ValueError, IndexError):
            raise BadRequest('KO Type not recognize')

        bounds = [(3, 4), (6, None), (2, 2), (1, 1)]
        minimum, maximum = bounds[request_type - 1]

        length = len(data_received)
        if length < minimum:
            raise BadRequest(
                    'KO Message not formed well. Not enough arguments.')

        if maximum is not None and length > maximum:
            raise BadRequest(
                    'KO Message not formed well. Too much arguments.')

        if request_type == 2:
            if length % 2:
                raise BadRequest(
                        'KO Message not formed well. '
                        'Arguments should come in pairs.')
            else:
                try:
                    data_received[1] = int(data_received[1])
                    data_received[3] = int(data_received[3])
                except ValueError:
                    raise BadRequest(
                            'KO Message not formed well. Second and '
                            'forth argument should be integers.')
        elif request_type == 3:
            try:
                data_received[1] = int(data_received[1])
            except ValueError:
                raise BadRequest(
                        'KO Message not formed well. Second '
                        'argument should be an integer.')

        data_received[0] = request_type
        return data_received

    def create_stat(self, confpath, job, *prefix):
        id = StatsManager().increment_id()
        prefix = None if not prefix else prefix[0]

        # creer le rstatsclient
        stats_client = Rstats(
                confpath=confpath,
                job_name=job,
                prefix=prefix,
                id=id,
                conf=self.conf)

        # ajouter le rstatsclient au dict
        with StatsManager() as stats:
            stats[id] = stats_client

        # envoyer OK
        return id

    def send_stat(self, id, stat, time, *extra_stats):
        # recuperer le rstatsclient et son mutex
        with StatsManager() as stats:
            try:
                stats_client = stats[id]
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
        with StatsManager() as stats:
            try:
                stats_client = stats[id]
            except KeyError:
                raise BadRequest(
                        'KO The given id doesn\'t '
                        'represent an open connection')
        # reload la conf
        stats_client.reload_conf()

    def reload_stats(self):
        with StatsManager() as stats:
            for stats_client in stats.values():
                # reload la conf
                stats_client.reload_conf()

    def execute_request(self, data): 
        request, *args = self.parse_and_check(data)
        functions = [
                self.create_stat,
                self.send_stat,
                self.reload_stat,
                self.reload_stats,
        ]
        return functions[request-1](*args)

    def run(self):
        data = self.socket.recv(2048)
        try:
            result = self.execute_request(data.decode())
        except BadRequest as e:
            self.socket.send(e.reason.encode())
        except UnicodeError:
            self.socket.send(b'KO The message couldn\'t be decyphered')
        else:
            if result is None:
                self.socket.send(b'OK')
            else:
                msg = 'OK {}'.format(result)
                self.socket.send(msg.encode())
        finally:
            self.socket.close()


if __name__ == '__main__':
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 1111))
    tcp_socket.listen(1000)

    StatsManager(init=True)
    conf = Conf('rstats.cfg')

    while True:
        client, _ = tcp_socket.accept()
        ClientThread(client, conf).start()

