#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
update_job_stat_policy.py - <+description+>
"""

import argparse
from frontend import update_job_stat_policy, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Update Job\'s stats Policy',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('-as', '--accept-stats', nargs='+', default=[], help='')
    parser.add_argument('-ds', '--deny-stats', nargs='+', default=[], help='')
    parser.add_argument('-dp', '--default-policy', action='store_true',
                        help='Send stats to the Collector')
    parser.add_argument('-d', '--date', metavar=DateMetavarHelper(),
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    job_name = args.job_name
    accept_stats = args.accept_stats
    deny_stats = args.deny_stats
    default_policy = args.default_policy
    date = args.date

    pretty_print(update_job_stat_policy)(agent_ip, job_name, accept_stats, deny_stats, default_policy, date)

