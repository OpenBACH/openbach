#!/usr/bin/python3
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



   @file     netcat.py
   @brief    Sources of the Job netcat
   @author   Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
"""

import subprocess
import argparse
import time
import sys
import syslog
import collect_agent

def main(input_s, output_t, measure_t):
    conffile = "/opt/openbach-jobs/socat/netcat_rstats_filter.conf"
    
    # Connect to collect agent
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to "
                               "collect-agent")
        quit(1)
      
    cmd = ['socat']
    cmd.append(input_s)
    cmd.append(output_s)
    if measure_t:
        cmd = ['/usb/bin/time', '-f', '%e', '--quiet'] + cmd
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stdin=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        p.wait()
    except:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR executing netcat:"
                               " %s" % ex)
    
    statistics = {}
    timestamp = int(round(time.time() * 1000))
    if not measure_t:
        return
    if p.returncode == 0:
        try:
            duration = float(p.stderr.read())
            statistics = { 'duration' : duration }
        except ValueError:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR: cannot convert output"
                                   " to duration value : %s" % (p.stderr.read()))
            return
    else:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR: return code %d : %s" %
                               (p.returncode, p.stderr.read()))
    try:
        r = collect_agent.send_stat(timestamp, **statistics)
    except Exception as ex:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR sending stat: %s" % ex)

if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    #group = parser.add_mutually_exclusive_group(required=True)
    # TODO: add mutual exclusivities
    parser.add_argument('input', metavar='input', type=str,
                       help='The input to socat')
    parser.add_argument('output', metavar='output', type=str,
                       help='The output of socat')
    parser.add_argument('-t', '--time', action='store_true',
                        help='Measure the duration of the process')

    # get args
    args = parser.parse_args()
    input_s = args.input
    output_s = args.output
    measure_t = args.time

    main(input_s, output_s, measure_t)
