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


"""Sources of the Job mptcp"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * David PRADAS <david.pradas@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import syslog
import argparse
import subprocess
from sys import exit

import collect_agent


SCHEDULERS = {'default', 'roundrobin', 'redundant'}
PATH_MANAGERS = {'default', 'fullmesh', 'ndiffports', 'binder'}


def exit_with_message(message):
    collect_agent.send_log(syslog.LOG_ERR, message)
    exit(message)


def sysctl_command(command, debug_log):
    try:
        subprocess.call(['sysctl', '-w', command])
        subprocess.call(['sysctl', '-p'])
        collect_agent.send_log(syslog.LOG_DEBUG, debug_log)
    except Exception as ex:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR modifying sysctl {}'.format(ex))


def main(iface_link1, iface_link2, iface_on1, iface_on2,
         conf_up, checksum, syn_retries, path_manager, scheduler):
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/mptcp/'
            'mptcp_rstats_filter.conf')
    if not success:
        exit_with_message('Error connecting to collect_agent')

    # Check if valid scheduler and path_manager values
    if path_manager and (path_manager not in PATH_MANAGERS):
        exit_with_message('ERROR path manager not in {}'.format(PATH_MANAGERS))
    if scheduler and (scheduler not in SCHEDULERS):
        exit_with_message('ERROR scheduler not in {}'.format(SCHEDULERS))

    # Configure MPTCP routing
    mptcp_enabled = 1 if conf_up == 1 else 0
    debug_message = 'enabled' if conf_up == 1 else 'disabled'
    sysctl_command(
            'net.mptcp.mptcp_enabled={}'.format(mptcp_enabled),
            'MPTCP is {}'.format(debug_message))

    # Change checksum
    if checksum is not None:
        sysctl_command(
                'net.mptcp.mptcp_checksum={}'.format(checksum),
                'MPTCP checksum updated')

    # Change syn_retries
    if syn_retries is not None:
        sysctl_command(
                'net.mptcp.mptcp_syn_retries={}'.format(syn_retries),
                'MPTCP syn_retries updated')

    # Change path_manager
    if path_manager is not None:
        sysctl_command(
                'net.mptcp.mptcp_path_manager={}'.format(path_manager),
                'MPTCP path_manager updated')

    # Change scheduler
    if scheduler is not None:
        sysctl_command(
                'net.mptcp.mptcp_scheduler={}'.format(scheduler),
                'MPTCP scheduler updated')

    # Enable interfaces
    for enabled, iface in ((iface_on1, iface_link1), (iface_on2, iface_link2)):
        debug_message = 'Enabled' if enabled else 'Disabled'
        try:
            subprocess.call(['ip', 'link', 'set', 'dev', iface_link1,
                             'multipath', 'on' if enabled else 'off'])
        except Exception as ex:
            collect_agent.send_log(
                    syslog.LOG_ERROR,
                    'Error when setting multipath on interface '
                    '{}: {}'.format(iface_link1, ex))
        else:
            collect_agent.send_log(
                    syslog.LOG_DEBUG,
                    '{} multipath on iface {}'
                    .format(debug_message, iface_link1))


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('iface_link1', metavar='iface_link1', help='')
    parser.add_argument('iface_link2', metavar='iface_link2', help='')
    parser.add_argument('-o', '--iface-on1', action='store_true', help='')
    parser.add_argument('-O', '--iface-on2', action='store_true', help='')
    parser.add_argument('-c', '--conf_up', type=int, default=1, help='')
    parser.add_argument('-k', '--checksum', type=int, help='')
    parser.add_argument('-y', '--syn-retries', type=int, help='')
    parser.add_argument('-p', '--path-manager', type=str, help='')
    parser.add_argument('-s', '--scheduler', type=str, help='')

    # get args
    args = parser.parse_args()
    iface_link1 = args.iface_link1
    iface_link2 = args.iface_link2
    iface_on1 = args.iface_on1
    iface_on2 = args.iface_on2
    conf_up = args.conf_up
    checksum = args.checksum
    syn_retries = args.syn_retries
    path_manager = args.path_manager
    scheduler = args.scheduler

    main(iface_link1, iface_link2, iface_on1,
         iface_on2, conf_up, checksum,
         syn_retries, path_manager, scheduler)
