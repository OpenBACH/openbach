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


"""OpenBACH Job rstats_job

Allow to modify the stats policy of a Job on an Agent
"""

__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import subprocess
import argparse
from os import rename


def main(file_id, job_name):
    template = '/opt/openbach-jobs/{0}/{0}{1}_rstats_filter.conf'
    path = template.format(job_name, file_id)
    rename('{}.locked'.format(path), path)
    subprocess.check_call(['service', 'rstats', 'reload'])


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

    args = parser.parse_args()
    main(args.transfert_id, args.job_name)
