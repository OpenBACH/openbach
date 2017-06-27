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

DEFAULT_PORT = 5000

import subprocess
import argparse
import time
import sys
import syslog
import collect_agent

def main(mode, persist, measure_t, filename, n_times):
    conffile = "/opt/openbach-jobs/netcat/netcat_rstats_filter.conf"
    
    # Connect to collect agent
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to "
                               "collect-agent")
        quit(1)
      
    cmd = ['nc']
    if persist:
        cmd.append('-k')
    if measure_t:
        cmd = ['/usr/bin/time', '-f', '%e', '--quiet'] + cmd
    cmd = cmd + mode.split()
    for n in range(n_times):
        if filename:
            with open(filename) as file_in:
                try:
                    p = subprocess.Popen(cmd, stdin=file_in,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.PIPE)
                    p.wait()
                except Exception as ex:
                    collect_agent.send_log(syslog.LOG_ERR, "ERROR executing netcat:"
                                           " %s" % ex)
                    
        else:
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
            continue
        if p.returncode == 0:
            try:
                duration = float(p.stderr.read())
                statistics = { 'duration' : duration }
            except ValueError:
                collect_agent.send_log(syslog.LOG_ERR, "ERROR: cannot convert output"
                                       " to duration value : %s" % (p.stderr.read()))
                continue
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
    parser.add_argument('-l', '--listen', action='store_true',
                       help='Run in server mode')
    parser.add_argument('-c', '--client', type=str,
                       help='Run in client mode (specify remote IP address)')
    parser.add_argument('-p', '--port', type=int,
                       help='The port number')
    parser.add_argument('-k', '--persist', action='store_true',
                        help='Keep listening after current connection is'
                        ' completed')
    parser.add_argument('-t', '--time', action='store_true',
                        help='Measure the duration of the process')
    parser.add_argument('-n', '--n-times', type=int, default=1,
                        help='The number of times the connection is '
                        'established')
    parser.add_argument('-f', '--file', type=str,
                        help='The path of a file to send to the server')

    # get args
    args = parser.parse_args()
    server = args.listen
    client = args.client
    n_times = args.n_times
    port = args.port
    if not port:
        port = DEFAULT_PORT
    if server:
        mode = '-l {}'.format(port)
    else:
        mode = '{} {}'.format(client, port)
    persist = args.persist
    measure_t = args.time
    filename = args.file

    main(mode, persist, measure_t, filename, n_times)
