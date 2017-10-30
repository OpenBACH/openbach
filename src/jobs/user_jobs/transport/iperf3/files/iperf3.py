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
'''


import argparse
import subprocess
import time
import syslog
import sys
import re

import collect_agent


def multiplier(unit, base):
    if unit == base:
        return 1
    if unit.startswith('M'):
        return 1024*1024
    if unit.startswith('K'):
        return 1024
    if unit.startswith('m'):
        return (1.0/1000)
    return 1


def main(mode, interval, length, port, udp, bandwidth, duration, num_flows):
    # Connect to collect_agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/iperf3/'
            'iperf3_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    cmd = ['iperf3']
    cmd += mode
    if interval:
        cmd += ['-i', str(interval)]
    if length:
        cmd += ['-l', str(length)]
    if port:
        cmd += ['-p', str(port)]
    if udp:
        cmd += ['-u']
    if mode[0] == '-c' and udp and bandwidth is not None:
        cmd += ['-b', str(bandwidth)]
    if mode[0] == '-c' and duration is not None:
        cmd += ['-t', str(duration)]
    if mode[0] == '-c' and num_flows is not None:
        cmd += ['-P', str(num_flows)]
    # If client, launch and exit
    if mode[0] == '-c':
        p = subprocess.run(cmd)
        sys.exit(p.returncode)
        
    # If server, read output, and send stats
    p = subprocess.Popen(['stdbuf', '-oL'] + cmd, stdout=subprocess.PIPE)

    flows = {}
    n_flows = 0

    while True:
        # read output
        out = p.stdout.readline().decode()
        if not out:
            if p.poll is not None:
                break
            continue

        timestamp = int(time.time() * 1000)

        # remove brackets
        out_s = re.sub('[\[\]]', '', out).split()

        # check if stats line
        try:
            int(out_s[0])
        except ValueError:
            # save SUM all the same
            if not out_s[0] == "SUM":
                continue

        # filter unnecessary messages
        if out_s[1] == "local":
            continue
        if out_s[-1] in {"sender", "receiver"}:
            # since it's last message (TCP) , remove flow
            try: 
                del flows[out_s[0]]
            except KeyError:
                pass
            continue
        
        # get index
        try:
            flow_no = flows[out_s[0]]
        except KeyError:
            if out_s[0] == "SUM":
                flows[out_s[0]] = "sum"
                flow_no = "sum"
            else:
                flows[out_s[0]] = n_flows
                flow_no = n_flows
                n_flows += 1

        # remove stats covering the whole duration
        try:
            report_ival = (float(out_s[1].split('-')[1]) - 
                           float(out_s[1].split('-')[0]))
        except ValueError:
            continue
        if (report_ival > float(interval)):
            # since it's last message (UDP) , remove flow
            try: 
                del flows[out_s[0]]
            except KeyError:
                pass
            continue

        statistics = {}
        if len(out_s) == 7:
            # TCP
            if float(out_s[3]) == 0.0:
                continue
            statistics["sent_data_{}".format(flow_no)] = (float(out_s[3]) * 
                    multiplier(out_s[4], "Bytes"))
            statistics["throughput_{}".format(flow_no)] = (float(out_s[5]) * 
                    multiplier(out_s[6], "bits/sec"))
            collect_agent.send_stat(timestamp, **statistics)
        elif len(out_s) == 11:
            # UDP
            if float(out_s[3]) == 0.0:
                continue
            statistics["sent_data_{}".format(flow_no)] = (float(out_s[3]) * 
                    multiplier(out_s[4], "Bytes"))
            statistics["throughput_{}".format(flow_no)] = (float(out_s[5]) * 
                    multiplier(out_s[6], "bits/sec"))
            statistics["jiggle_{}".format(flow_no)] = (float(out_s[7]) * 
                    multiplier(out_s[8], "s"))
            statistics["lost_pkts_{}".format(flow_no)] = int(out_s[9].split('/')[0])
            statistics["sent_pkts_{}".format(flow_no)] = int(out_s[9].split('/')[1])
            statistics["plr_{}".format(flow_no)] = float(out_s[10][1:-2])
            collect_agent.send_stat(timestamp, **statistics)
        else:
            # unknown 
            continue


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
            '-b', '--bandwidth', type=float,
            help='Set target bandwidth to n bits/sec (default '
            '1Mbit/sec). This setting requires UDP (-u).')
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
    server = args.server
    client = args.client
    exit = args.exit
    mode = ['-s','-1'] if server and exit else \
           ['-s'] if server else ['-c', client]
    interval = args.interval
    length = args.length
    port = args.port
    udp = args.udp
    bandwidth = args.bandwidth
    duration= args.time
    num_flows = args.num_flows

    main(mode, interval, length, port, udp, bandwidth, duration, num_flows)
