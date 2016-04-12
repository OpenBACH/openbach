#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
start_instance.py - <+description+>
"""

from frontend import start_instance, date_to_timestamp, status_instance
import argparse
import pprint


def main(agent_ip, job_name, arguments, date, interval, status):
    r = start_instance(agent_ip, job_name, arguments, date, interval)
    print "Start Instance:"
    print r
    pprint.pprint(r.json())
    if status != None:
        instance_id = int(r.json()['instance_id'])
        interval = status
        r = status_instance(instance_id, interval=interval)
        print "Start watch of the status:"
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
                        nargs=2, help='Date of the execution')
    parser.add_argument('-i', '--interval', type=str, default=None,
                        help='Interval of the execution')
    parser.add_argument('-s', '--status', type=str, default=None,
                        help='Start a watch of the status with this interval')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    job_name = args.job_name[0]
    arguments = args.arguments
    if args.date == None:
        date = None
    else:
        date = int(date_to_timestamp(args.date[0] + " " + args.date[1])*1000)
    interval = args.interval
    status = args.status
    if (date != None) and (interval != None):
        print("You can only provide a date OR an interval, but not both")
        exit(1)

    main(agent_ip, job_name, arguments, date, interval, status)

