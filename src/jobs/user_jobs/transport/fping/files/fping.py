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



   @file     fping.py
   @brief    Sources of the Job fping
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
             David PRADAS <david.pradas@toulouse.viveris.com>
"""


import subprocess
import argparse
import time
import syslog
import rstats_api as rstats


# Configure logger
syslog.openlog('fping', syslog.LOG_PID, syslog.LOG_USER)


def command_line_flag_for_argument(argument, flag):
    if argument is not None:
        yield flag
        yield str(argument)


def handle_exception(exception, connection_id, timestamp):
    statistics = {'status': 'Error'}
    rstats.send_stat(connection_id, timestamp, **statistics)
    syslog.syslog(syslog.LOG_ERR, "ERROR: %s" % exception)


def main(destination_ip, count, interval, interface, packetsize, ttl, duration):
    conffile = "/opt/openbach-jobs/fping/fping_rstats_filter.conf"

    cmd = ['fping', destination_ip]
    cmd.extend(command_line_flag_for_argument(count, '-c'))
    cmd.extend(command_line_flag_for_argument(interval, '-i'))
    cmd.extend(command_line_flag_for_argument(interface, '-I'))
    cmd.extend(command_line_flag_for_argument(packetsize, '-s'))
    cmd.extend(command_line_flag_for_argument(ttl, '-t'))
    cmd.extend(command_line_flag_for_argument(duration, '-w'))

    connection_id = rstats.register_stat(conffile)
    if connection_id == 0:
        return

    while True:
        timestamp = int(round(time.time() * 1000))
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as ex:
            if ex.returncode in (-15, -9):
                continue
            handle_exception(ex, connection_id, timestamp)
            return
        try:
            rtt_data = output.strip().decode().split(':')[-1].split('=')[-1].split('/')[1]
        except IndexError as ex:
            handle_exception(ex, connection_id, timestamp)
            return
        statistics = {'rtt': rtt_data}
        rstats.send_stat(connection_id, timestamp, **statistics)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', metavar='destination_ip', type=str,
                        help='')
    parser.add_argument('-c', '--count', type=int,
                        help='', default=3)
    parser.add_argument('-i', '--interval', type=int,
                        help='')
    parser.add_argument('-I', '--interface', type=str,
                        help='')
    parser.add_argument('-s', '--packetsize', type=int,
                        help='')
    parser.add_argument('-t', '--ttl', type=int,
                        help='')
    parser.add_argument('-w', '--duration', type=int,
                        help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    interface = args.interface
    packetsize = args.packetsize
    ttl = args.ttl
    duration = args.duration

    main(destination_ip, count, interval, interface, packetsize, ttl, duration)

