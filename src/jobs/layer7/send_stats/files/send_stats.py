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
import sys
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats
from os import listdir


def send_stats(path, filename, connection_id):
    with open('{}{}'.format(path, filename)) as f:
        lines = f.readlines()
        for line in lines:
            line_json = json.loads(line)
            del line_json['flag']
            timestamp = line_json.pop('time')
            stat_name = line_json.pop('stat_name')
            rstats.send_stat(connection_id, stat_name, timestamp, **line_json)


def main(job_name, date):
    path = '/var/openbach_stats/'
    d = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    l = listdir('{}{}'.format(path, job_name))

    conffile = "/opt/openbach-jobs/send_stats/send_stats_rstats_filter.conf"

    # Connexion au service de collecte de l'agent
    if l:
        connection_id = rstats.register_stat(conffile, 'send_stats')
        if connection_id == 0:
            quit()

    for f in l:
        if f.startswith(job_name):
            file_date_str = f.lstrip('{}_'.format(job_name)).rstrip('.stats')
            file_date = datetime.datetime.strptime(file_date_str,
                                                   '%Y-%m-%dT%H%M%S')
            if file_date > d:
                send_stats('{}{}/'.format(path, job_name), f, connection_id)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('date', nargs=2, help='Date of the execution')
    parser.add_argument('-sii', '--scenario-instance-id', type=int,
                        help='The Id of the Scenario Instance')

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    date = '{} {}'.format(*args.date)

    main(job_name, date)

