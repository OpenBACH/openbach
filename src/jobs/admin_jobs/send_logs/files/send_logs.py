#!/usr/bin/env python3

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
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Sources of the Job send_logs"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import socket
import syslog
import argparse
import datetime
from contextlib import suppress
try:
    import simplejson as json
except ImportError:
    import json

import yaml


# Configure logger
syslog.openlog('send_logs', syslog.LOG_PID, syslog.LOG_USER)
LOGS_DIR = '/var/log/openbach/'


def get_collector_infos(config_file='/opt/openbach/agent/collector.yml'):
    with open(config_file) as stream:
        return yaml.load(stream)


def send_logs(filename, dest):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except socket.error:
        syslog.syslog(syslog.LOG_NOTICE, 'Failed to create socket')
        raise

    with sock, open(os.path.join(LOGS_DIR, filename)) as log:
        for line in log:
            message = (
                    '<{line[pri]}>{line[timestamp]} '
                    '{line[hostname]} {line[programname]}'
                    '[{line[procid]}]: {line[msg]}'
                    .format(line=json.loads(line))
            )
            try:
                sock.sendto(message.encode(), dest)
            except socket.error as error:
                syslog.syslog(
                        syslog.LOG_NOTICE,
                        'Error code: {}, Message {}'.format(*error))
                raise


def main(job_name, date):
    try:
        collector = get_collector_infos()
    except yaml.YAMLError:
        syslog.syslog(
                syslog.LOG_NOTICE,
                'Collector configuration file is malformed')
        raise
    except FileNotFoundError:
        syslog.syslog(
                syslog.LOG_NOTICE,
                'Collector configuration file not found')
        raise

    try:
        address = collector['address']
        port = collector['logs']['port']
    except KeyError:
        syslog.syslog(
                syslog.LOG_NOTICE,
                'Collector configuration file is malformed')
        raise

    logstash = (address, int(port))
    from_date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    date_format = '{}_%Y-%m-%dT%H%M%S.log'.format(job_name)
    for filename in os.listdir(LOGS_DIR):
        with suppress(ValueError):
            file_date = datetime.datetime.strptime(filename, date_format)
            if file_date >= from_date:
                send_logs(filename, logstash)


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('date', nargs=2, help='Date of the execution')

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    date = '{} {}'.format(*args.date)
    main(job_name, date)
    syslog.closelog()
