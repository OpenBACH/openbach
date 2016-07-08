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
   
   
   
   @file     status_job_instance.py
   @brief    Call the openbach-function status_job_instance
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


#!/usr/bin/env python3

import argparse
from frontend import status_job_instance, date_to_timestamp, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Status Instance',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_id', help='Id of the Instance')
    parser.add_argument('-a', '--agent-ip', help='IP address of the Agent')
    parser.add_argument('-j', '--job-name', help='Name of the Job')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-d', '--date', metavar=DateMetavarHelper(),
                       nargs=2, help='Date when the status will be check')
    group.add_argument('-i', '--interval',
                       help='Start a watch of the status with this interval')
    group.add_argument('-s', '--stop', metavar=DateMetavarHelper(),
                       nargs=2, help='Stop a watch of the status')
    
    # get args
    args = parser.parse_args()
    instance_id = args.instance_id
    date = date_to_timestamp('{} {}'.format(*args.date)) if args.date else None
    interval = args.interval
    stop = date_to_timestamp('{} {}'.format(*args.stop)) if args.stop else None
    agent_ip = args.agent_ip
    job_name = args.job_name

    pair_ip_name = (agent_ip, job_name)
    if any(pair_ip_name) and not all(pair_ip_name):
        parser.error('-a and -j arguments must be provided by pairs')

    pretty_print(status_job_instance)(instance_id, date, interval, stop, agent_ip, job_name)

