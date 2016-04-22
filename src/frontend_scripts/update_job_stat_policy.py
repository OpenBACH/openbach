#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
update_job_stat_policy.py - <+description+>
"""

from frontend import update_job_stat_policy, date_to_timestamp
import argparse
import pprint


def main(agent_ip, job_name, accept_stats, deny_stats, default_policy, date):
    r = update_job_stat_policy(agent_ip, job_name, accept_stats, deny_stats, default_policy, date)
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
    parser.add_argument('-as', '--accept-stats', type=str, default=None,
                        nargs='+', help='')
    parser.add_argument('-ds', '--deny-stats', type=str, default=None,
                        nargs='+', help='')
    parser.add_argument('-dp', '--default-policy', action='store_true', help='With this '
                        'option, the default policy is to send stats to the '
                        'Collector. Without it, it is to not send stats to the '
                        'Collector')
    parser.add_argument('-d', '--date', type=str, default=None,
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    job_name = args.job_name[0]
    if args.accept_stats == None:
        accept_stats = []
    else:
        accept_stats = args.accept_stats
    if args.deny_stats == None:
        deny_stats = []
    else:
        deny_stats = args.deny_stats
    default_policy = args.default_policy
    if args.date == None:
        date = None
    else:
        date = int(date_to_timestamp(args.date[0] + " " + args.date[1])*1000)

    main(agent_ip, job_name, accept_stats, deny_stats, default_policy, date)

