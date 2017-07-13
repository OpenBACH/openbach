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


"""Sources of the Job netcat"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''

import time
import syslog
import argparse
import subprocess

import collect_agent


def main(mode, port, persist, measure_t, filename):
    # Connect to collect agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/netcat/'
            'netcat_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        exit(message)

    cmd = ['nc', mode, str(port)]
    if persist:
        cmd.append('-k')
    if measure_t:
        cmd = ['/usr/bin/time', '-f', '%e', '--quiet'] + cmd

    if filename:
        with open(filename) as file_in:
            try:
                p = subprocess.run(
                        cmd, stdin=file_in,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
            except Exception as ex:
                collect_agent.send_log(
                        syslog.LOG_ERR,
                        'ERROR executing netcat: {}'.format(ex))
    else:
        try:
            p = subprocess.run(
                    cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
        except Exception as ex:
            collect_agent.send_log(
                    syslog.LOG_ERR,
                    'ERROR executing netcat: {}'.format(ex))

    timestamp = int(time.time() * 1000)
    if measure_t and p.returncode == 0:
        try:
            duration = float(p.stderr)
        except ValueError:
            return
    try:
        collect_agent.send_stat(timestamp, duration=duration)
    except Exception as ex:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR sending stat: {}'.format(ex))


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
            '-l', '--listen', action='store_true',
            help='Run in server mode')
    group.add_argument(
            '-c', '--client', type=str,
            help='Run in client mode (specify remote IP address)')
    group.add_argument(
            '-p', '--port', type=int, default=5000,
            help='The port number')
    parser.add_argument(
            '-k', '--persist', action='store_true',
            help='Keep listening after current connection is completed')
    parser.add_argument(
            '-t', '--time', action='store_true',
            help='Measure the duration of the process')
    parser.add_argument(
            '-f', '--file', type=str,
            help='The path of a file to send to the server')

    # get args
    args = parser.parse_args()
    server = args.listen
    client = args.client
    port = args.port
    mode = '-l' if server else client
    persist = args.persist
    measure_t = args.time
    filename = args.file

    main(mode, port, persist, measure_t, filename)
