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


import sys
import time
import syslog
import argparse
import subprocess

import collect_agent


def main(input_s, output_t, measure_t):
    # Connect to collect agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/socat/'
            'socat_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    cmd = ['socat', input_s, output_s]
    if measure_t:
        cmd = ['/usb/bin/time', '-f', '%e', '--quiet'] + cmd

    try:
        p = subprocess.run(
                cmd, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)
    except Exception as ex:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR executing netcat: {}'.format(ex))

    if measure_t and p.returncode == 0:
        timestamp = int(time.time() * 1000)
        stderr = p.stderr
        try:
            duration = float(stderr)
        except ValueError:
            collect_agent.send_log(
                    syslog.LOG_ERR,
                    'ERROR: cannot convert output to duration '
                    'value: {}'.format(stderr))
        else:
            try:
                collect_agent.send_stat(timestamp, duration=duration)
            except Exception as ex:
                collect_agent.send_log(
                        syslog.LOG_ERR,
                        'ERROR sending stat: {}'.format(ex))
    elif p.returncode:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR: return code {}: {}'
                .format(p.returncode, p.stderr))


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('input', help='The input to socat')
    parser.add_argument('output', help='The output of socat')
    parser.add_argument(
            '-t', '--time', action='store_true',
            help='Measure the duration of the process')

    # get args
    args = parser.parse_args()
    input_s = args.input
    output_s = args.output
    measure_t = args.time

    main(input_s, output_s, measure_t)
