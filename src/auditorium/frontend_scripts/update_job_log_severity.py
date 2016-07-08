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
   
   
   
   @file     update_job_log_severity.py
   @brief    Call the openbach-function udpate_job_log_severity
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


#!/usr/bin/env python3

import argparse
from frontend import update_job_log_severity, date_to_timestamp, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Update Job\'s log Severity',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('severity', help='Log severity we want to send to the Collector')
    parser.add_argument('-l', '--local-severity', type=int, default=None,
                        help='Log severity we want to save in local')
    parser.add_argument('-d', '--date', metavar=DateMetavarHelper(),
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    job_name = args.job_name
    severity = args.severity
    local_severity = args.local_severity
    date = date_to_timestamp('{} {}'.format(*args.date)) if args.date else None

    pretty_print(update_job_log_severity)(agent_ip, job_name, severity, local_severity, date)

