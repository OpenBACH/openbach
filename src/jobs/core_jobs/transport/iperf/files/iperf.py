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


"""Sources of the Job iperf"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import re
import sys
import syslog
import time
import argparse
import subprocess
from itertools import repeat
from collections import defaultdict
import collect_agent

BRACKETS = re.compile(r'[\[\]]')

class AutoIncrementFlowNumber:
    def __init__(self):
        self.count = 0

    def __call__(self):
        self.count += 1
        return 'Flow{0.count}'.format(self)


def multiplier(unit, base):
    if unit == base:
        return 1
    if unit.startswith('M'):
        return 1024 * 1024
    if unit.startswith('K'):
        return 1024
    if unit.startswith('m'):
        return 0.001
    return 1


def _command_build_helper(flag, value):
    if value is not None:
        yield flag
        yield str(value)


def client(client, interval, length, port, udp, bandwidth, time):
    cmd = ['iperf', '-c', client]
    if interval:
        cmd += ['-i', str(interval)]
    if length:
        cmd += ['-l', str(length)]
    if port:
        cmd += ['-p', str(port)]
    if udp:
        cmd += ['-u']
    if udp and bandwidth is not None:
        cmd += ['-b', str(bandwidth)]
    if time is not None:
        cmd += ['-t', str(time)]
    p = subprocess.run(cmd)
    if p.returncode:
        message = 'WARNING: \'{}\' exited with non-zero code'.format(
                ' '.join(cmd))
        

def server(interval, length, port, udp, bandwidth, duration):
    # Connect to collect agent
    collect_agent.register_collect(
            '/opt/openbach/agent/jobs/iperf/'
            'iperf_rstats_filter.conf')
    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job iperf')
    
    cmd = ['iperf', '-s']
    if interval:
        cmd += ['-i', str(interval)]
    if length:
        cmd += ['-l', str(length)]
    if port:
        cmd += ['-p', str(port)]
    if udp:
        cmd += ['-u']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    
    flow_map = defaultdict(AutoIncrementFlowNumber())

    for flow_number in repeat(None):
        line = p.stdout.readline().decode()
        tokens = BRACKETS.sub('', line).split()
        if not tokens:
            if p.poll() is not None:
                break
            continue
        timestamp = int(time.time() * 1000)
        if len(tokens) > 1 and tokens[1][-1] == '-':
            tokens[1] = tokens[1] + tokens[2]
            del(tokens[2])
        if len(tokens) > 9 and tokens[9][-1] == '/':
            tokens[9] = tokens[9] + tokens[10]
            del(tokens[10])
        try:
            try:
                flow, duration, _, transfer, transfer_units, bandwidth, bandwidth_units, jitter, jitter_units, packets_stats, datagrams = tokens
                jitter = float(jitter)
                datagrams = float(datagrams[1:-2])
                lost, total = map(int, packets_stats.split('/'))
            except ValueError:
                udp = False
                flow, duration, _, transfer, transfer_units, bandwidth, bandwidth_units = tokens
            else:
                udp = True
            transfer = float(transfer)
            bandwidth = float(bandwidth)
            interval_begin, interval_end = map(float, duration.split('-'))
        except ValueError:
            # filter out non-stats lines
            continue

        if not transfer or interval_end - interval_begin > interval:
            # filter out lines covering the whole duration
            continue

        try:
            flow_number = flow_map[int(flow)]
        except ValueError:
            if flow.upper() != "SUM":
                continue

        statistics = {
                'sent_data': transfer * multiplier(transfer_units, 'Bytes'),
                'throughput': bandwidth * multiplier(bandwidth_units, 'bits/sec'),
        }
        if udp:
            statistics['jitter'] = jitter * multiplier(jitter_units, 's')
            statistics['lost_pkts'] = lost
            statistics['sent_pkts'] = total
            statistics['plr'] = datagrams
        collect_agent.send_stat(timestamp, suffix=flow_number, **statistics)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
            '-s', '--server', action='store_true',
            help='Run in server mode')
    group.add_argument(
            '-c', '--client', type=str,
            help='Run in client mode and specify server IP address')
    parser.add_argument(
            '-i', '--interval', type=int, default=1,
            help='Pause *interval* seconds between '
            'periodic bandwidth reports')
    parser.add_argument(
            '-l', '--length', type=int,
            help='Set length read/write buffer to n (default 8 KB)')
    parser.add_argument(
            '-p', '--port', type=int,
            help='Set server port to listen on/connect to '
            'n (default 5001)')
    parser.add_argument(
            '-u', '--udp', action='store_true',
            help='Use UDP rather than TCP')
    parser.add_argument(
            '-b', '--bandwidth', type=str,
            help='Set target bandwidth to n [M/K]bits/sec (default '
            '1Mbit/sec). This setting requires UDP (-u).')
    parser.add_argument(
            '-t', '--time', type=float,
            help='Time in seconds to transmit for (default 10secs). '
            'This setting requires client mode.')

    # get args
    args = parser.parse_args()
    interval = args.interval
    length = args.length
    port = args.port
    udp = args.udp
    bandwidth = args.bandwidth
    duration = args.time
    if args.server:
        server(interval, length, port, udp, bandwidth, duration)
    else:
        client(args.client, interval, length, port, udp, bandwidth, duration)
