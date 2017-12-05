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


"""Sources of the Job iperf3"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import sys
import time
import syslog
import argparse
import subprocess
from itertools import repeat

import collect_agent


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


def client(client, interval, length, port, udp, bandwidth, duration, num_flows):
    cmd = ['iperf3', '-c', client]
    cmd.extend(_command_build_helper('-i', interval))
    cmd.extend(_command_build_helper('-l', length))
    cmd.extend(_command_build_helper('-p', port))
    if udp:
        cmd.append('-u')
        cmd.extend(_command_build_helper('-b', bandwidth))
    cmd.extend(_command_build_helper('-t', duration))
    cmd.extend(_command_build_helper('-P', num_flows))

    p = subprocess.run(cmd)
    sys.exit(p.returncode)


def server(exit, interval, length, port, udp):
    # Connect to collect_agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/iperf3/'
            'iperf3_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    cmd = ['stdbuf', '-oL', 'iperf3', '-s']
    if exit:
        cmd.append('-1')
    cmd.extend(_command_build_helper('-i', interval))
    cmd.extend(_command_build_helper('-l', length))
    cmd.extend(_command_build_helper('-p', port))
    if udp:
        cmd.append('-u')

    # Read output, and send stats
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    for flow_number in repeat(None):
        tokens = p.stdout.readline().decode().split()
        if not tokens:
            if p.poll() is not None:
                break
            continue

        timestamp = int(time.time() * 1000)

        try:
            if udp:
                flow, duration, _, transfer, transfer_units, bandwidth, bandwidth_units, jitter, jitter_units, packets_stats, datagrams = tokens
                jitter = float(jitter)
                datagrams = float(datagrams[1:-2])
                lost, total = map(int, packets_stats.split('/'))
            else:
                flow, duration, _, transfer, transfer_units, bandwidth, bandwidth_units = tokens
            transfer = float(transfer)
            bandwidth = float(bandwidth)
            interval_begin, interval_end = map(float, duration.split('-'))
        except ValueError:
            # filter out non-stats lines
            continue

        if not transfer or interval_end - interval_begin >= interval:
            # filter out lines covering the whole duration
            continue

        try:
            # Remove brackets
            flow = int(flow[1:-1])
        except ValueError:
            if flow[1:-1].strip().upper() != "SUM":
                continue
        else:
            flow_number = str(flow)

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
            '1M). This setting requires UDP (-u).')
    parser.add_argument(
            '-t', '--time', type=float, default=0,
            help='Time in seconds to transmit for (default: unlimited). '
            'This setting requires client mode.')
    parser.add_argument(
            '-1', '--exit', action='store_true',
            help='For a server, exit upon completion of one connection.')
    parser.add_argument(
            '-n', '--num-flows', type=int,
            help='For a client, the number of parallel flows.')

    # get args
    args = parser.parse_args()
    interval = args.interval
    length = args.length
    port = args.port
    udp = args.udp

    if args.server:
        server(args.exit, interval, length, port, udp)
    else:
        bandwidth = args.bandwidth
        duration = args.time
        num_flows = args.num_flows
        client(args.client, interval, length, port, udp, bandwidth, duration, num_flows)
