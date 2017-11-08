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
from subprocess import Popen, PIPE, STDOUT
from statistics import mean

import collect_agent


def main(destination_ip, count, interval, n_mean, destport):
    cmd = ['stdbuf', '-oL']
    cmd += ['hping3', str(destination_ip), '-S']
    if destport:
        cmd += ['-p', str(destport)]
    if count:
        cmd += ['-c', str(count)]
    if interval:
        cmd += ['-i', str(interval)]

    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/hping/'
            'hping_rstats_filter.conf')
    if not success:
        message = "ERROR connecting to collect-agent"
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)
    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job hping')

    measurements = []

    # launch command
    p = Popen(cmd, stdout=PIPE, stderr=STDOUT)
    while True:
        timestamp = int(time.time() * 1000)
        rtt_data = None

        # read output
        output = p.stdout.readline().decode()
        if not output:
            if p.poll is not None:
                break
            continue

        try:
            for col in reversed(output.split()):
                if not col.startswith('rtt='):
                    continue
                rtt_data = float(col.split('=')[1])
                break
        except Exception as ex:
            message = 'ERROR: {}'.format(ex)
            collect_agent.send_stat(timestamp, status=message)
            collect_agent.send_log(syslog.LOG_ERR, message)
            sys.exit(message)

        if rtt_data is None:
            continue

        measurements.append(rtt_data)
        if len(measurements) == n_mean:
            collect_agent.send_stat(timestamp, rtt=mean(measurements))
            measurements = []


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', help='')
    parser.add_argument(
            '-p', '--destport', type=int, default=443,
            help='destination port for TCP ping')
    parser.add_argument('-c', '--count', type=int, help='')
    parser.add_argument('-i', '--interval', type=int, help='')
    parser.add_argument('-m', '--mean', type=int, help='', default=1)

    # get args
    args = parser.parse_args()
    destport = args.destport
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    n_mean = args.mean

    main(destination_ip, count, interval, n_mean, destport)
