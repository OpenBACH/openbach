#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).


   Copyright © 2016 CNES


   This file is part of the OpenBACH testbed.


   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.

   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.

   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.



   @file     send_stats.py
   @brief    Sources of the Job send_stats
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import datetime
try:
    import simplejson as json
except ImportError:
    import json
import os
import collect_agent_api as collect_agent


def send_stats(path, filename):
    conffile = "/opt/openbach-jobs/send_stats/send_stats_rstats_filter.conf"

    with open('{}{}'.format(path, filename)) as f:
        connection_recreated = False
        lines = f.readlines()
        for line in lines:
            line_json = json.loads(line)
            del line_json['flag']
            timestamp = line_json.pop('time')
            job_name = line_json.pop('job_name')
            job_instance_id = line_json.pop('job_instance_id')
            scenario_instance_id = line_json.pop('scenario_instance_id')
            try:
                suffix = line_json.pop('suffix')
            except KeyError:
                suffix = None
            os.environ['JOB_NAME'] = job_name
            os.environ['JOB_INSTANCE_ID'] = job_instance_id
            os.environ['SCENARIO_INSTANCE_ID'] = scenario_instance_id
            if not connection_recreated:
                # Connexion au service de collecte de l'agent
                success = collect_agent.register_collect(
                    conffile, new=True)
                if not success:
                    quit()
                connection_recreated = True
            collect_agent.send_stat(timestamp, suffix=suffix, **line_json)


def main(job_name, date):
    path = '/var/openbach_stats/'
    d = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    l = os.listdir('{}{}'.format(path, job_name))

    for f in l:
        if f.startswith(job_name):
            file_date_str = f.lstrip('{}_'.format(job_name)).rstrip('.stats')
            file_date = datetime.datetime.strptime(file_date_str,
                                                   '%Y-%m-%dT%H%M%S')
            if file_date > d:
                send_stats('{}{}/'.format(path, job_name), f)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('date', nargs=2, help='Date of the execution')

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    date = '{} {}'.format(*args.date)

    main(job_name, date)
