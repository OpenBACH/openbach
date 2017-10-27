#!/usr/bin/python
# -*- coding: utf-8 -*-

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


"""OpenBACH Job rsyslog_job

Allow to modify the logs policy of a Job on an Agent
"""

__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import subprocess
import argparse
from os import rename, remove


def main(file_id, job_name, disable_code):
    pattern = '/etc/rsyslog.d/{}{{}}{{}}.conf{{}}'.format(job_name)

    for local_part in ('', '_local'):
        from_playbook = pattern.format(file_id, local_part, '.locked')
        final_dest = pattern.format('', local_part, '')
        rename(from_playbook, final_dest)

    if disable_code & 0x01:
        remove(pattern.format('', ''))
    if disable_code & 0x10:
        remove(pattern.format('_local', ''))

    subprocess.check_call(['systemctl', 'restart', 'rsyslog'])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
            'transfer_id', metavar='ID', type=int,
            help='Unique ID used to transfer the input files')
    parser.add_argument(
            'job_name', metavar='job_name',
            help='The name of the Job you want to change the logs policy')
    parser.add_argument(
            '-d', '--disable-code', type=int, default=0,
            help='Disable SSL/TLS')

    args = parser.parse_args()
    main(args.transfer_id, args.job_name, args.disable_code)
