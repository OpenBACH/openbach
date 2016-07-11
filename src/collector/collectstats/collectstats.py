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
   
   
   
   @file     collectstats.py
   @brief    The Collector daemon for the statistics
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import threading
import socket
import shlex
import requests
import traceback
from configparser import ConfigParser

import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))


BOOLEAN = frozenset({'t', 'T', 'true', 'True', 'TRUE', 'f', 'F', 'false', 'False', 'FALSE'})
URL = 'http://127.0.0.1:{}/write?db={}&precision={}&u={}&p={}'


def parse_type(value):
    try:
        int(value)
        return '{}i'.format(value)
    except ValueError:
        try:
            float(value)
            return value
        except ValueError:
            if value in BOOLEAN:
                return value
            else:
                return '"{}"'.format(value)


def send_stat(stat_name, time, stats, url):
    # Former la commande
    data = '{0} {2} {1}'.format(stat_name, time,
        ','.join('{}={}'.format(k, parse_type(v)) for k, v in stats.items()))

    # Envoyer la commande
    try:
        result = requests.post(url, data=data)
    except requests.ConnectionError:
        traceback.print_stack()
        return 'ConnectionError'
    return result._content


def parse_and_check(data):
    data_received = shlex.split(data)

    num_args = len(data_received)
    if num_args < 4 or num_args % 2:
        raise ValueError('Message not formed well')

    try:
        data_received[1] = int(data_received[1])
    except ValueError:
        raise ValueError('Timestamp should be an int in milliseconds')

    return data_received


def grouper(iterable, n):
    args = [iter(iterable)] * n
    return zip(*args)


def check_and_send(data, url):
    try:
        request = parse_and_check(data.decode())
    except ValueError as err:
        print(err)
        traceback.print_stack()
        return False

    request_iterator = grouper(request, 2)
    stat_name, time = next(request_iterator)
    stats = {key:value for key, value in request_iterator}
    send_stat(stat_name, time, stats, url)

    return True


def handle_command_tcp(client_socket, url):
    data = client_socket.recv(2048)
    response = check_and_send(data, url)
    client_socket.send(b'KO' if not response else b'OK')
    client_socket.close()


class TcpThread(threading.Thread):
    def __init__(self, tcp_socket, url):
        super().__init__()
        self.socket = tcp_socket
        self.url = url

    def run(self):
        while True:
            client, _ = self.socket.accept()
            threading.Thread(target=handle_command_tcp, args=(client, self.url)).start()


class UdpThread(threading.Thread):
    def __init__(self, udp_socket, url):
        super().__init__()
        self.socket = udp_socket
        self.url = url
    
    def run(self):
        while True:
            data = self.socket.recv(1024)
            threading.Thread(target=check_and_send, args=(data, self.url)).start()


class Conf:
    def __init__(self, conf_path='config.ini'):
        config = ConfigParser()
        config.read(conf_path)
        self.collectstats_port = int(config['collectstats']['port'])

        database = config['influxdb']
        self.port = database['port']
        self.database = database['database']
        self.username = database['username']
        self.password = database['password']
        self.time_precision = database['time_precision']


if __name__ == '__main__':
    conf = Conf('collectstats.cfg')
    url = URL.format(conf.port, conf.database, conf.time_precision, conf.username, conf.password)

    # Creer la socket udp
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('', conf.collectstats_port))

    # Creer la socket tcp
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.bind(('', conf.collectstats_port))
    tcp.listen(1000)

    # Lancer l'ecoute sur les deux sockets
    TcpThread(tcp, url).start()
    UdpThread(udp, url).start()

