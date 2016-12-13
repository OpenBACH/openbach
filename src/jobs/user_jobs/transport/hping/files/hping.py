#!/usr/bin/env python3
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



   @file     rate_monitoring.py
   @brief    Sources of the Job rate_monitoring
   @author   David PRADAS <david.pradas@toulouse.viveris.com>
"""


import subprocess
import shlex
import argparse
import time
import sys
import syslog
import collect_agent
from subprocess import Popen, PIPE, STDOUT

def get_simple_cmd_output(cmd, stderr=STDOUT):
    """
    Execute a simple external command and get its output.
    """
    args = shlex.split(cmd)
    return Popen(args, stdout=PIPE, stderr=stderr).communicate()[0]


def main(destination_ip, count, interval, destport, tcpmode):
    conffile = "/opt/openbach-jobs/hping/hping_rstats_filter.conf"

    cmd = 'hping3 {}'.format(destination_ip)
    if destport:
        cmd = '{} -p {}'.format(cmd, destport)
    if count:
        cmd = '{} -c {}'.format(cmd, count)
    if interval:
        cmd = '{} -i {}'.format(cmd, interval)
    if tcpmode:
        cmd = '{} -S'.format(cmd)

    success = collect_agent.register_collect(conffile)
    if not success:
        quit()

    #persitent jobs that only finishes when it is stopped by OpenBACH
    while True:
        timestamp = int(round(time.time() * 1000))
        try:
            rtt_data = get_simple_cmd_output(cmd).strip().decode().split('\n')[2].split('=')[1].split('/')[1]

        except Exception as ex:
            statistics = {'status': 'Error'}
            collect_agent.send_stat(timestamp, **statistics)
            collect_agent.send_log(syslog.LOG_ERR, "ERROR: %s" % ex)
            return

        statistics = {'rtt': rtt_data}
        r = collect_agent.send_stat(timestamp, **statistics)


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', metavar='destination_ip', type=str,
                        help='')
    parser.add_argument('-p', '--destport', type=int,
                        help='destination port for TCP ping', default=443)
    parser.add_argument('-c', '--count', type=int,
                        help='', default=3)
    parser.add_argument('-i', '--interval', type=int,
                        help='')
    parser.add_argument('-S', '--tcpmode', action='store_true',
                        help='to send TCP SYN packet')

    # get args
    args = parser.parse_args()
    destport = args.destport
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    tcpmode = args.tcpmode

    main(destination_ip, count, interval, destport, tcpmode)
