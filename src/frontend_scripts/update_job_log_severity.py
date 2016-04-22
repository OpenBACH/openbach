#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
update_job_log_severity.py - <+description+>
"""

from frontend import update_job_log_severity, date_to_timestamp
import argparse
import pprint


def main(agent_ip, job_name, severity, local_severity, date):
    r = update_job_log_severity(agent_ip, job_name, severity, local_severity, date)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP Address of the Agent')
    parser.add_argument('job_name', metavar='job_name', type=str, nargs=1,
                        help='Name of the Job')
    parser.add_argument('severity', metavar='severity', type=int, nargs=1,
                        help='Log severity we want to send to the Collector')
    parser.add_argument('-l', '--local-severity', type=int, default=None,
                        help='Log severity we want to save in local')
    parser.add_argument('-d', '--date', type=str, default=None,
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    job_name = args.job_name[0]
    severity = args.severity[0]
    local_severity = args.local_severity
    if args.date == None:
        date = None
    else:
        date = int(date_to_timestamp(args.date[0] + " " + args.date[1])*1000)

    main(agent_ip, job_name, severity, local_severity, date)

