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



   @file     tcpprobe_dmonitoring.py
   @brief    Sources of the Job tcpprobe_monitoring
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
             David PRADAS <david.pradas@toulouse.viveris.com>
"""

import syslog
import argparse
import time
import os
from sys import exit
import signal
import rstats_api as rstats


def signal_term_handler(signal, frame):
    cmd = "PID=`cat /var/run/tcpprobe_monitoring.pid`; kill -TERM $PID; rm "
    cmd += "/var/run/tcpprobe_monitoring.pid"
    os.system(cmd)
    cmd = "rmmod tcp_probe_new_fix > /dev/null 2>&1"
    os.system(cmd)
    exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)
syslog.openlog("tcpprobe_monitoring", syslog.LOG_PID, syslog.LOG_USER)

def watch(fn):
    fp = open(fn, 'r')
    while True:
        new = fp.readline()
        #(Improvement) Indicate the line that is being read
        # Once all lines are read this just returns ''
        # until the file changes and a new line appears

        if new:
            yield new
        else:
            # TODO: (Improvement2) Indicate to the script that it can stop it 
            time.sleep(0.5)

def main(path, port, interval):
    # Monitoring setup
    cmd = "insmod /opt/openbach-jobs/tcpprobe_monitoring/tcp_probe_new_fix/tcp_probe_new_fix.ko"
    cmd += " port=" + str(port) + " full=1 > /dev/null 2>&1"
    try:
        os.system(cmd)
    except Exception as exe_error:
        syslog.syslog(syslog.LOG_ERROR, "ERROR: %s" % exe_error)
        exit("tcp_probe_new_fix.ko can not be executed")

    cmd = "chmod 444 /proc/net/tcpprobe"
    os.system(cmd)
    cmd = "PID=`cat /proc/net/tcpprobe > " + path + " & echo $!`; echo $PID >"
    cmd += " /var/run/tcpprobe_monitoring.pid"
    os.system(cmd)

    # Build stat names 
    stats_list = ["cwnd_monitoring", "ssthresh_monitoring",
                  "sndwnd_monitoring", "rtt_monitoring", "rcvwnd_monitoring"]

    conffile = "/opt/openbach-jobs/tcpprobe_monitoring/tcpprobe_monitoring_rstats_filter.conf"

    syslog.syslog(syslog.LOG_DEBUG, "DEBUG: the following stats have been built --> %s" % stats_list)

    # Connect to the Agent collecting service
    connection_id = rstats.register_stat(conffile)
    if connection_id == 0:
        quit()

    i = 1
    for row in watch(path):
        if i == interval:
            data = row.split(' ')
            stat = []
            if len(data) == 11:
                timestamp = data[0]
                timestamp_sec = timestamp.split('.')[0]
                timestamp_nsec = timestamp.split('.')[1]
                timestamp = timestamp_sec + timestamp_nsec[:3]
                stat.append(data[6]) # cwnd
                stat.append(data[7]) # ssthresh
                stat.append(data[8]) # sndwnd
                stat.append(data[9]) # srtt
                stat.append(data [10]) # rcvwnd

                try:
                    statistics = {"port": port}
                    for nstats in range(len(stats_list)):
                        # Send stats to Collector
                        statistics[stats_list[nstats]] = stat[nstats]

                    r = rstats.send_stat(connection_id, int(timestamp),
                                         **statistics)
                except Exception as connection_err:
                    syslog.syslog(syslog.LOG_ERR, "ERROR: %s" % connection_err)
                    return

            i = 1
        else:
            i += 1


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='Active/Deactive tcpprobe monitoring.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('port', metavar='port', type=int, nargs=1,
                        help='Port to monitor')
    parser.add_argument('-p', '--path', type=str,
                        default='/tmp/tcpprobe.out',
                        help='path to result file')
    parser.add_argument('-i', '--interval', type=int, default=10,
                        help='get the cwnd of 1/interval packet')

    # get args
    args = parser.parse_args()
    port = args.port[0]
    path = args.path
    interval = args.interval

    main(path, port, interval)

