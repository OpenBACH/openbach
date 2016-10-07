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
   
   
   
   @file     empty_influxdb_db.py
   @brief    Sources of the Job empty_influxdb_db
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import requests


def main(job_instance_id, scenario_instance_id, influxdb_port, database,
         username, password):
    url = 'http://localhost:{0}/query?db={1}&epoch=ms&q=DROP DATABASE' \
          ' {1}'.format(influxdb_port, database)
    requests.get(url)
    url = 'http://localhost:{0}/query?db={1}&epoch=ms&q=CREATE DATABASE' \
          ' {1}'.format(influxdb_port, database)
    requests.get(url)
    url = 'http://localhost:{}/query?db={}&epoch=ms&q=CREATE USER {} WITH' \
          ' PASSWORD {} WITH ALL PRIVILEGES'.format(influxdb_port, database,
                                                    username, password)
    requests.get(url)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('-sii', '--scenario-instance-id', type=int,
                        help='The Id of the Scenario Instance')
    parser.add_argument('-p', '--port', type=int, default=8086,
                        help='port of InfluxDB')
    parser.add_argument('-d', '--database', type=str, default='openbach',
                        help='name of the database')
    parser.add_argument('-u', '--username', type=str, default='openbach',
                        help='name of the user')
    parser.add_argument('-pa', '--password', type=str, default='openbach',
                        help='password of the user')
    
    # get args
    args = parser.parse_args()
    job_instance_id = args.job_instance_id
    scenario_instance_id = args.scenario_instance_id
    port = args.port
    database = args.database_name
    username = args.username
    password = args.password
    
    main(job_instance_id, scenario_instance_id, port, database, username,
         password)

