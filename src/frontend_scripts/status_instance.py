#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
status_instance.py - <+description+>
"""

from frontend import status_instance, date_to_timestamp
import argparse
import pprint


def main(instance_id, date, interval, stop, agent_ip, job_name):
    r = status_instance(instance_id, date, interval, stop, agent_ip, job_name)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_id', metavar='instance_id', type=str, nargs=1,
                        help='Id of the Instance')
    parser.add_argument('-d', '--date', type=str, default=None,
                        nargs=2, help='Date when the status will be check')
    parser.add_argument('-i', '--interval', type=str, default=None,
                        help='Start a watch of the status with this interval')
    parser.add_argument('-s', '--stop', type=str, default=None,
                        nargs=2, help='Stop a watch of the status')
    parser.add_argument('-a', '--agent-ip', type=str, default=None,
                        help='IP address of the Agent')
    parser.add_argument('-j', '--job-name', type=str, default=None,
                        help='Name of the Job')
    
    # get args
    args = parser.parse_args()
    instance_id = args.instance_id[0]
    if args.date == None:
        date = None
    else:
        date = int(date_to_timestamp(args.date[0] + " " + args.date[1])*1000)
    interval = args.interval
    if args.stop == None:
        stop = None
    else:
        stop = int(date_to_timestamp(args.stop[0] + " " + args.stop[1])*1000)
    if ((date != None) and (interval != None)) or ((date != None) and (stop !=
       None)) or ((interval != None) and (stop != None)):
        print("You can only provide a start date OR an interval OR a stop date,"
              " but not two or three of them")
        exit(1)
    agent_ip = args.agent_ip
    job_name = args.job_name
    if ((agent_ip != None) and (job_name == None)) or ((agent_ip == None) and
                                                       (job_name != None)):
        print("If you provide an agent_ip, you have to provide the job_name and"
              " reciprocity")
        exit(1)

    main(instance_id, date, interval, stop, agent_ip, job_name)

