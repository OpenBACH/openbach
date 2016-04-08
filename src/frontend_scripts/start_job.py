#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
start_job.py - <+description+>
"""

import requests, json
import argparse


def main(agent_ip, job_name, arguments, date, interval):
    url = "http://localhost:8000/conductor/instances/start"

    payload = {'agent_ip': agent_ip, 'job_name': job_name}
    if arguments == None:
        payload['args'] = list()
    else:
        payload['args'] = arguments
    if interval != None:
        payload['interval'] = interval
    if date != None:
        payload['date'] = date
    
    r = requests.post(url, data={'data': json.dumps(payload)})
    print r
    print(r._content)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP address of the Agent')
    parser.add_argument('job_name', metavar='job_name', type=str, nargs=1,
                        help='Name of the Job')
    parser.add_argument('-a', '--arguments', type=str, default=None,
                        nargs ='+', help='Arguments of the Job')
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

