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


'''Sources of the Job tcpprobe_monitoring'''


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * David PRADAS <david.pradas@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import os
import time
import signal
import syslog
import argparse
from sys import exit

import collect_agent


def signal_term_handler(signal, frame):
    cmd = 'PID=`cat /var/run/tcpprobe_monitoring.pid`; kill -TERM $PID; rm '
    cmd += '/var/run/tcpprobe_monitoring.pid'
    os.system(cmd)
    cmd = 'rmmod tcp_probe > /dev/null 2>&1'
    os.system(cmd)
    exit(0)


signal.signal(signal.SIGTERM, signal_term_handler)


def watch(fn):
    with open(fn, 'r') as fp:
        while True:
            new = fp.readline()
            # (Improvement) Indicate the line that is being read
            # Once all lines are read this just returns ''
            # until the file changes and a new line appears
            if new:
                yield new
            else:
                # TODO: (Improvement2) Indicate to the script that it can stop it
                time.sleep(0.5)


def main(path, port, interval):
    # Connect to the Agent collecting service
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/tcpprobe_monitoring/'
            'tcpprobe_monitoring_rstats_filter.conf')
    if not success:
        message = "ERROR connecting to collect-agent"
        collect_agent.send_log(syslog.LOG_ERR, message)
        exit(message)

    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job'
            ' tcpprobe_monitoring')
    
    # Build stat names
    stats_list = [
            'cwnd_monitoring',
            'ssthresh_monitoring',
            'sndwnd_monitoring',
            'rtt_monitoring',
            'rcvwnd_monitoring',
    ]

    collect_agent.send_log(
            syslog.LOG_DEBUG,
            'DEBUG: the following stats have been '
            'built --> {}'.format(stats_list))

    # Unload existing tcp_probe job and/or module (if exists)
    cmd = 'PID=`cat /var/run/tcpprobe_monitoring.pid`; kill -TERM $PID; rm '
    cmd += '/var/run/tcpprobe_monitoring.pid'
    try:
        os.system(cmd)
    except Exception as exe_error:
        collect_agent.send_log(syslog.LOG_DEBUG, 'No previous tcp_probe job to kill before launching the job: %s' % exe_error)
        exit('No previous tcp_probe job to kill before launching the job')
    
    cmd = 'rmmod tcp_probe > /dev/null 2>&1'
    try:
        os.system(cmd)
    except Exception as exe_error:
        collect_agent.send_log(syslog.LOG_ERROR, 'Existing tcp_probe cannot be unloaded: %s' % exe_error)

    # Monitoring setup
    cmd = (
            'modprobe tcp_probe port={}'
            ' full=1 > /dev/null 2>&1'.format(port)
    )
    
    # The reference time
    init_time = int(time.time() * 1000)
    
    try:
        os.system(cmd)
    except Exception as exe_error:
        collect_agent.send_log(syslog.LOG_ERROR, 'tcp_probe cannot be executed: %s' % exe_error)
        exit('tcp_probe cannot be executed')

    cmd = 'chmod 444 /proc/net/tcpprobe'
    os.system(cmd)
    cmd = 'PID=`cat /proc/net/tcpprobe > ' + path + ' & echo $!`; echo $PID >'
    cmd += ' /var/run/tcpprobe_monitoring.pid'
    os.system(cmd)

    collect_agent.send_log(syslog.LOG_DEBUG, "Finished setting up probe")

    for i, row in enumerate(watch(path)):
        if i % interval == 0:
            data = row.split()
            if len(data) == 11:
                timestamp = data[0].strip('\x00')
                timestamp_sec, timestamp_nsec = timestamp.split('.', 1)
                timestamp_real = init_time + int(timestamp_sec)*1000 + int(timestamp_nsec[:3])
                try:
                    collect_agent.send_stat(
                            timestamp_real,
                            port=port,
                            cwnd_monitoring=data[6],
                            ssthresh_monitoring=data[7],
                            sndwnd_monitoring=data[8],
                            rtt_monitoring=data[9],
                            rcvwnd_monitoring=data[10],)
                except Exception as connection_err:
                    message = 'ERROR: {}'.format(connection_err)
                    collect_agent.send_log( syslog.LOG_ERR, message)
                    exit(message)


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description='Activate/Deactivate tcpprobe monitoring on outgoing traffic.',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('port', type=int, help='Port to monitor (dest or src)')
    parser.add_argument(
            '-p', '--path', default='/tmp/tcpprobe.out',
            help='path to result file')
    parser.add_argument(
            '-i', '--interval', type=int, default=10,
            help='get the cwnd of 1/interval packet')

    # get args
    args = parser.parse_args()
    port = args.port
    path = args.path
    interval = args.interval

    main(path, port, interval)
