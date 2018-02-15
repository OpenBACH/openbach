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


"""Sources of the Job configure_link"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import re
import sys
import syslog
import argparse
import subprocess

import collect_agent

def run_command(cmd):
    """ Run a command, return return code """
    p = subprocess.run(cmd, stderr=subprocess.PIPE)
    if p.returncode:
        collect_agent.send_log(syslog.LOG_ERR,
                "Error when executing command '{}': '{}'".format(
                    ' '.join(cmd), p.stderr.decode()))
    return p.returncode

def delete_qdisc(interface):
    """ Delete the tc qdisc on an interface """
    cmd = ['tc', 'qdisc', 'del', 'dev', interface, 'root']
    run_command(cmd)

def add_qdisc_bandwidth(interface, bandwidth):
    """ Add a qdisc to limit the bandwidth on interface """
    cmds = [[
                'tc', 'qdisc', 'add', 'dev', interface, 'root',
                'handle', '1:', 'htb', 'default', '11'
            ],[
                'tc', 'class', 'add', 'dev', interface, 'parent',
                '1:', 'classid', '1:1', 'htb', 'rate', '{}bps'.format(bandwidth),
                'burst', '1000b'
            ],[
                'tc', 'class', 'add', 'dev', interface, 'parent',
                '1:1', 'classid', '1:11', 'htb', 'rate', '{}bit'.format(bandwidth),
                'burst', '1000b'
            ]]
    for cmd in cmds:
        run_command(cmd)

def add_qdisc_delay(interface, delay, loss, handle):
    """ Add a qdisc to set a delayh on interface """
    cmd = ['tc', 'qdisc', 'add', 'dev', interface]
    cmd.extend(handle)
    cmd.extend(['netem', 'delay', '{}ms'.format(delay)])
    cmd.extend(['loss', '{}%'.format(loss)])
    run_command(cmd)

def main(interfaces, delay=None, bandwidth=None, loss=None):
    collect_agent.register_collect(
            '/opt/openbach/agent/jobs/configure_link/'
            'configure_link_rstats_filter.conf')     

    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting configure_link job')

    for interface in interfaces.split(','):
        handle = ['root', 'handle', '1:']
        # Delete existing qdisc
        delete_qdisc(interface)
        # Add bandwidth if pertinent
        if bandwidth:
            if not re.findall(r'^[0-9]+[KM]$', bandwidth):
                collect_agent.send_log(syslog.LOG_ERR,
                        "Invalid format for bandwidth: expecting "
                        "'{}', found '{}'".format('{VALUE}{M|K}', bandwidth))
                sys.exit(1)
            add_qdisc_bandwidth(interface, bandwidth)
            handle = ['parent', '1:11', 'handle', '10:']
        # Add delay
        add_qdisc_delay(interface, delay, loss, handle)


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('interfaces', type=str, help='')
    parser.add_argument('-d', '--delay', type=int, default=0, help='')
    parser.add_argument('-b', '--bandwidth', type=str, help='')
    parser.add_argument('-l', '--loss', type=float, default=0.0, help='')

    # get args
    args = parser.parse_args()

    main(**vars(args))
