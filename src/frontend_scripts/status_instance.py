#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
status_instance.py - <+description+>
"""

import argparse
from frontend import status_instance, date_to_timestamp, pretty_print


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

    pretty_print(status_instance)(instance_id, date, interval, stop, agent_ip, job_name)

