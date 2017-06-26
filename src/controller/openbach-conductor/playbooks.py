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
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Collection of Ansible plays built programmatically"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


def _common_helper(name, *tasks):
    return dict(name=name, hosts='all', tasks=list(tasks))


def check_connection():
    return _common_helper('Check Available Connection')


def status_agent():
    return _common_helper(
            'Retrieve the Status of an Agent', {
                'name': 'Get status of openbach-agent (pre 16.04)',
                'action': {
                    'module': 'shell',
                    'args': 'service openbach-agent status',
                },
                'when': 'ansible_distribution_version != "16.04"',
            }, {
                'name': 'Get status of openbach-agent (post 16.04)',
                'action': {
                    'module': 'service',
                    'name': 'openbach-agent',
                    'state': 'restarted',
                },
                'become': 'yes',
                'when': 'ansible_distribution_version == "16.04"',
            })


def assign_collector():
    return _common_helper(
            'Assign a new collector to an agent', {
                'name': 'Assign new Collector',
                'action': {
                    'module': 'template',
                    'src': '/opt/openbach-controller/src_agent/openbach-agent/collector.yml.j2',
                    'dest': '/opt/openbach-agent/collector.yml',
                },
                'become': 'yes',
            })


def push_file(local_path, remote_path):
    return _common_helper(
            'Send file to a remote location', {
                'name': 'Push file',
                'action': {
                    'module': 'copy',
                    'src': local_path,
                    'dest': remote_path,
                },
                'become': 'yes',
            })


def enable_logs(severity, local_severity, logs_path):
    base_commands = _common_helper('Update rsyslog configuration files')

    if severity != 8:
        base_commands['tasks'].append({
            'name': 'Push new rsyslog configuration file',
            'action': {
                'module': 'template',
                'src': '{}/templates/job.j2'.format(logs_path),
                'dest': '/etc/rsyslog.d/{{ job }}{{ transfer_id }}.conf.locked',
                'owner': 'root',
                'group': 'root',
            },
            'become': 'yes',
        })

    if local_severity != 8:
        base_commands['tasks'].append({
            'name': 'Push new local rsyslog configuration file',
            'action': {
                'module': 'template',
                'src': '{}/templates/job_local.j2'.format(logs_path),
                'dest': '/etc/rsyslog.d/{{ job }}{{ transfer_id }}_local.conf.locked',
                'owner': 'root',
                'group': 'root',
            },
            'become': 'yes',
        })

    return base_commands


PREDEFINED_PLAYS = {
        'check_connection': check_connection,
        'status_agent': status_agent,
        'assign_collector': assign_collector,
        'push_file': push_file,
        'enable_logs': enable_logs,
}
