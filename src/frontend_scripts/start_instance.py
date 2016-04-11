#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
start_instance.py - <+description+>
"""

from frontend import start_instance
import argparse
import pprint


def main(agent_ip, job_name, arguments, date, interval):
    r = start_instance(agent_ip, job_name, arguments, date, interval)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP address of the Agent')
    parser.add_argument('job_name', metavar='job_name', type=str, nargs=1,
                        help='Name of the Job')
    parser.add_argument('-a', '--arguments', type=str, default=None,
                        nargs ='+', help='Arguments of the Instance')
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the execution')
    parser.add_argument('-i', '--interval', type=str, default=None,
                        help='Interval of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    job_name = args.job_name[0]
    arguments = args.arguments
    date = args.date
    interval = args.interval
    if (date != None) and (interval != None):
        print("You can only provide a date OR an interval, but not both")
        exit(1)

    main(agent_ip, job_name, arguments, date, interval)

