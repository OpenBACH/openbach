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


"""Sources of the Job hping"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * David PRADAS <david.pradas@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import sys
import time
import shlex
import syslog
import argparse
from subprocess import run, PIPE, STDOUT

import collect_agent


def get_simple_cmd_output(cmd, stderr=STDOUT):
    """Execute a simple external command and get its output"""
    args = shlex.split(cmd)
    result = run(args, stdout=PIPE, stderr=stderr)
    return result.stdout


def main(destination_ip, count, interval, destport):
    cmd = 'hping3 {} -S'.format(destination_ip)
    if destport:
        cmd = '{} -p {}'.format(cmd, destport)
    if count:
        cmd = '{} -c {}'.format(cmd, count)
    if interval:
        cmd = '{} -i {}'.format(cmd, interval)

    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/hping/'
            'hping_rstats_filter.conf')
    if not success:
        message = "ERROR connecting to collect-agent"
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)
    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job hping')

    # persitent jobs that only finishes when it is stopped by OpenBACH
    while True:
        timestamp = int(time.time() * 1000)
        try:
            output = get_simple_cmd_output(cmd).strip().decode()
            rtt_data = output.split('\n')[2].split('=')[1].split('/')[1]
        except Exception as ex:
            message = 'ERROR: {}'.format(ex)
            collect_agent.send_stat(timestamp, status=message)
            collect_agent.send_log(syslog.LOG_ERR, message)
            sys.exit(message)
        collect_agent.send_stat(timestamp, rtt=rtt_data)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', help='')
    parser.add_argument(
            '-p', '--destport', type=int, default=443,
            help='destination port for TCP ping')
    parser.add_argument('-c', '--count', type=int, default=3, help='')
    parser.add_argument('-i', '--interval', type=int, help='')

    # get args
    args = parser.parse_args()
    destport = args.destport
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval

    main(destination_ip, count, interval, destport)
