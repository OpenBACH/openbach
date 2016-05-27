#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
start_instance.py - <+description+>
"""

import argparse
from frontend import start_instance, status_instance, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


def main(agent_ip, job_name, arguments, date, interval, status=None):
    response = start_instance(agent_ip, job_name, arguments, date, interval)
    print('Start Instance:')
    print(response)
    infos = response.json()
    pprint.pprint(infos)

    if status is not None:
        instance_id = int(infos['instance_id'])
        print('Start watch of the status:')
        pretty_print(status_instance)(instance_id, interval=status)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Start and Status Instance',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP address of the Agent')
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('-a', '--arguments', nargs='+', help='Arguments of the Instance')
    parser.add_argument('-s', '--status', help='Start a watch of the status with this interval')
    # Not sure here, you may want required=False
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-d', '--date', metavar=DateMetavarHelper(),
                        nargs=2, help='Date of the execution')
    group.add_argument('-i', '--interval', help='Interval of the execution')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    job_name = args.job_name
    arguments = args.arguments
    date = args.date
    interval = args.interval
    status = args.status

    main(agent_ip, job_name, arguments, date, interval, status)

