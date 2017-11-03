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


"""Sources of the Job fping"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * David PRADAS <david.pradas@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import sys
import time
import syslog
import argparse
import subprocess
from statistics import mean
import collect_agent


def command_line_flag_for_argument(argument, flag):
    if argument is not None:
        yield flag
        yield str(argument)


def handle_exception(exception, timestamp):
    message = 'ERROR: {}'.format(exception)
    collect_agent.send_stat(timestamp, status=message)
    collect_agent.send_log(syslog.LOG_ERR, message)
    return message


def main(destination_ip, count, interval, interface, packetsize, ttl, n_mean):
    cmd = ['fping', destination_ip]
    if count == 0:
        cmd += ['-l']
    else:
        cmd += ['-c', str(count)]
    cmd.extend(command_line_flag_for_argument(interval, '-i'))
    cmd.extend(command_line_flag_for_argument(interface, '-I'))
    cmd.extend(command_line_flag_for_argument(packetsize, '-s'))
    cmd.extend(command_line_flag_for_argument(ttl, '-t'))

    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/fping/'
            'fping_rstats_filter.conf')
    if not success:
        message = "ERROR connecting to collect-agent"
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job fping')

    measurements = []

    # launch command
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    while True:
        timestamp = int(time.time() * 1000)

        # read output
        output = p.stdout.readline().decode()
        if not output:
            if p.poll is not None:
                break
            continue

        try:
            rtt_data = float(output.split()[5])
        except (IndexError, ValueError) as ex:
            message = handle_exception(ex, timestamp)
            sys.exit(message)

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
    parser.add_argument('-c', '--count', type=int, default=0, help='')
    parser.add_argument('-i', '--interval', type=int, help='')
    parser.add_argument('-I', '--interface', type=str, help='')
    parser.add_argument('-s', '--packetsize', type=int, help='')
    parser.add_argument('-t', '--ttl', type=int, help='')
    parser.add_argument('-m', '--mean', type=int, default=1, help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    interface = args.interface
    packetsize = args.packetsize
    ttl = args.ttl
    n_mean = args.mean

    main(destination_ip, count, interval, interface, packetsize, ttl, n_mean)
