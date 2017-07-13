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


"""Sources of the Job send_stats"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import argparse
import datetime
from contextlib import suppress
try:
    import simplejson as json
except ImportError:
    import json

import collect_agent


ENVIRON_METADATA = (
        'job_name',
        'job_instance_id',
        'scenario_instance_id',
        'owner_scenario_instance_id',
)


def send_stats(filename):
    conf_file = '/opt/openbach/agent/jobs/send_stats/send_stats_rstats_filter.conf'

    with open(filename) as statistics:
        first_line = json.loads(next(statistics))
        metadata = first_line.pop('_metadata')
        timestamp = metadata['time']
        suffix = metadata.get('suffix')
        # Setup for register_collect to work properly
        for name in ENVIRON_METADATA:
            os.environ[name.upper()] = metadata[name]
        # Recreate connection with rstats
        success = collect_agent.register_collect(conf_file, new=True)
        if not success:
            raise ConnectionError('cannot communicate with rstats')
        collect_agent.send_stat(timestamp, suffix=suffix, **first_line)

        for line in statistics:
            line_json = json.loads(line)
            metadata = line_json.pop('_metadata')
            timestamp = metadata['time']
            suffix = metadata.get('suffix')
            collect_agent.send_stat(timestamp, suffix=suffix, **line_json)


def main(job_name, date, stats_folder='/var/openbach_stats/'):
    from_date = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    date_format = '{}_%Y-%m-%dT%H%M%S.stats'.format(job_name)

    for filename in os.listdir(os.path.join(stats_folder, job_name)):
        with suppress(ValueError):
            file_date = datetime.datetime.strptime(filename, date_format)
            if file_date >= from_date:
                send_stats(os.path.join(stats_folder, job_name, filename))


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('date', nargs=2, help='Date of the execution')

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    date = '{} {}'.format(*args.date)
    main(job_name, date)
