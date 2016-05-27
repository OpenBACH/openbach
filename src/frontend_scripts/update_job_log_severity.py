#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
update_job_log_severity.py - <+description+>
"""

import argparse
from frontend import update_job_log_severity, pretty_print


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
    date = args.date

    pretty_print(update_job_log_severity)(agent_ip, job_name, severity, local_severity, date)

