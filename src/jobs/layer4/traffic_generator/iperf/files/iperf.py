#!/usr/bin/python
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
   
   
   
   @file     iperf.py
   @brief    Sources of the Job iperf
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import subprocess
import argparse
from os import rename


def main(mode, interval, length, port, udp):
    cmd = 'iperf {}'.format(mode)
    if interval:
        cmd = '{} -i {}'.format(cmd, interval)
    if length:
        cmd = '{} -l {}'.format(cmd, length)
    if port:
        cmd = '{} -p {}'.format(cmd, port)
    if udp:
        cmd = '{} -u'.format(cmd)
    print(cmd)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-s', '--server', action='store_true',
                       help='Run in server mode')
    group.add_argument('-c', '--client', type=str,
                       help='Run in client mode')
    parser.add_argument('-i', '--interval', type=int,
                        help='Pause *interval* seconds between periodic'
                        ' bandwidth reports')
    parser.add_argument('-l', '--length', type=int,
                        help='Set length read/write buffer to n (default 8 KB)')
    parser.add_argument('-p', '--port', type=int,
                        help='Set server port to listen on/connect to to n'
                        ' (default 5001)')
    parser.add_argument('-u', '--udp', action='store_true',
                        help='Use UDP rather than TCP')

    # get args
    args = parser.parse_args()
    server = args.server
    client = args.client
    if server:
        mode = '-s'
    else:
        mode = '-c {}'.format(client)
    interval = args.interval
    length = args.length
    port = args.port
    udp = args.udp

    main(mode, interval, length, port, udp)

