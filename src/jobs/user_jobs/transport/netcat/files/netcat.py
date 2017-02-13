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
import collect_agent
import time

def main(mode, persist, measure_t, filename):
    cmd = ['nc'] + mode.split()
    if persist:
        cmd.append('-k')
    if measure_t:
        cmd = ['/usr/bin/time', '-f', '%e', '--quiet'] + cmd
    if filename:
        with open(filename) as file_in:
            try:
                p = subprocess.run(cmd, stdin=file_in, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
            except Exception as ex:
                collect_agent.send_log(syslog.LOG_ERR, "ERROR executing netcat:"
                                       " %s" % ex)
                
    else:
        try:
            p = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        except:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR executing netcat:"
                                   " %s" % ex)
    timestamp = int(round(time.time() * 1000))
    if mesure_t and p.returncode == 0:
        try:
            duration = float(p.stderr)
        except ValueError:
            return
    statistics = { 'duration' : duration }
    try:
        r = collect_agent.send_stat(timestamp, **statistics)
    except Exception as ex:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR sending stat: %s" % ex)

if __name__ == "__main__":
    conffile = "/opt/openbach-jobs/netcat/netcat_rstats_filter.conf"
    
    # Connect to collect agent
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to "
                               "collect-agent")
        quit(1)
        
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-l', '--listen', action='store_true',
                       help='Run in server mode')
    group.add_argument('-c', '--client', type=str,
                       help='Run in client mode (specify remote IP address)')
    group.add_argument('-p', '--port', type=int,
                       help='The port number')
    parser.add_argument('-k', '--persist', action='store_true',
                        help='Keep listening after current connection is'
                        ' completed')
    parser.add_argument('-t', '--time', action='store_true',
                        help='Measure the duration of the process')
    parser.add_argument('-f', '--file', type=str,
                        help='The path of a file to send to the server')

    # get args
    args = parser.parse_args()
    server = args.listen
    client = args.client
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

    main(mode, persist, measure_t, filename)
