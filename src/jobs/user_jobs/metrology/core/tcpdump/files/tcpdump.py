#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
# 
# 
# Copyright © 2017 CNES
# 
# 
# This file is part of the OpenBACH testbed.
# 
# 
# OpenBACH is a free software : you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
# 
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
# 
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.

""" Sources of the job tcpdump """

__author__ = 'Viveris Technologies'
__credits__ = ''' Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''


import subprocess
import argparse
import select
import os
import syslog
import collect_agent
import sys

def main(iface, out_file, duration):
    # Connect to collect agent
    conffile = '/opt/openbach/agent/jobs/tcpdump/tcpdump.conf'
    success = collect_agent.register_collect(conffile)
    if not success:
        message = "ERROR connecting to collect-agent"
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    # Launch tcpdump
    cmd = ["tcpdump", "-i", iface]
    if out_file:
        cmd += ["-w", out_file]
    if duration:
        cmd = ["timeout", str(duration)] + cmd
    p = subprocess.Popen(cmd)
    if duration:
        p.wait()

if __name__ == "__main__":
    # Define usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("iface", type=str,
                        help='The interface name')
    parser.add_argument('-w', '--write', type=str, default='',
                        help='Output filename')
    parser.add_argument('-d', '--duration', type=int, default=0,
                        help='Duration in seconds of the capture')
    
    # Get arguments
    args = parser.parse_args()
    iface = args.iface
    out_file = args.write
    duration = args.duration
    
    main(iface, out_file, duration)
