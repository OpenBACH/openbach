#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
stop_instance.py - <+description+>
"""

from frontend import stop_instance, date_to_timestamp
import argparse
import pprint


def main(instance_ids, date):
    r = stop_instance(instance_ids, date)
    print r
    pprint.pprint(r.json())

    
if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_ids', metavar='instance_ids', type=str,
                        nargs='+', help='Id of the instance')
    parser.add_argument('-d', '--date', type=str, default=None,
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    instance_ids = args.instance_ids
    if args.date == None:
        date = None
    else:
        date = int(date_to_timestamp(args.date[0] + " " + args.date[1])*1000)

    main(instance_ids, date)

