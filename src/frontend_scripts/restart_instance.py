#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
restart_instance.py - <+description+>
"""

from frontend import restart_instance
import argparse
import pprint


def main(instance_id, arguments, date, interval):
    r = restart_instance(instance_id, arguments, date, interval)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_id', metavar='instance_id', type=str, nargs=1,
                        help='Id of the instance')
    parser.add_argument('-a', '--arguments', type=str, default=None,
                        nargs ='+', help='Arguments of the Instance')
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the execution')
    parser.add_argument('-i', '--interval', type=str, default=None,
                        help='Interval of the execution')
    
    # get args
    args = parser.parse_args()
    instance_id = args.instance_id[0]
    arguments = args.arguments
    date = args.date
    interval = args.interval
    if (date != None) and (interval != None):
        print("You can only provide a date OR an interval, but not both")
        exit(1)

    main(instance_id, arguments, date, interval)

