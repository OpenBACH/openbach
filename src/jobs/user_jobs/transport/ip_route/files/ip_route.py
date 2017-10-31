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


"""Sources of the Job ip_route"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Oumaima ZERROUQ <oumaima.zerrouq@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import sys
import syslog
import argparse
import ipaddress
import subprocess

import collect_agent


def main(destination_ip, subnet_mask, gateway_ip,
         action, default_gateway, default_gw_name):
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/ip_route/'
            'ip_route_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)

    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job ip_route')

    # Adding a new variable 'action' for the addition/deletion of a route
    action_message = 'added' if action == 1 else 'deleted'
    default_message = 'default ' if default_gateway == 1 else ''
    command = [
            'route', 'add' if action == 1 else 'del',
            'default', 'gw', destination_ip, default_gw_name,
    ] if default_gateway == 1 else [
            'route', 'add' if action == 1 else 'del',
            '-net', destination_ip,
            'netmask', subnet_mask,
            'gw', gateway_ip,
    ]

    try:
        subprocess.check_call(command)
    except Exception as ex:
        message = 'ERROR: {}'.format(ex)
        collect_agent.send_log(syslog.LOG_ERR, message)
        sys.exit(message)
    else:
        collect_agent.send_log(
                syslog.LOG_DEBUG,
                'New {} route {}'.format(default_message, action_message))


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
            '-i', '--destination_ip', type=ipaddress.ip_address,
            help='')
    parser.add_argument(
            '-s', '--subnet_mask', type=ipaddress.ip_address,
            help='')
    parser.add_argument(
            '-g', '--gateway_ip', type=ipaddress.ip_address,
            help='')
    parser.add_argument('-a', '--action', type=int, help='')
    parser.add_argument('-d', '--default_gateway', type=int, help='')
    parser.add_argument('-b', '--default_gw_name', type=str, help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    subnet_mask = args.subnet_mask
    gateway_ip = args.gateway_ip
    action = args.action
    default_gateway = args.default_gateway
    default_gw_name = args.default_gw_name

    main(destination_ip, subnet_mask, gateway_ip,
         action, default_gateway, default_gw_name)
