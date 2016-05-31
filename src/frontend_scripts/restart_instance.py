#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
restart_instance.py - <+description+>
"""

import argparse
from frontend import restart_instance, date_to_timestamp, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Restart Instance',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_id', help='Id of the instance')
    parser.add_argument('-a', '--arguments', nargs='+',
            help='Arguments of the Instance')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('-d', '--date', metavar=DateMetavarHelper(),
            nargs=2, help='Date of the execution')
    group.add_argument('-i', '--interval', help='Interval of the execution')
    
    # get args
    args = parser.parse_args()
    instance_id = args.instance_id
    arguments = args.arguments
    date = date_to_timestamp('{} {}'.format(*args.date)) if args.date else None
    interval = args.interval

    pretty_print(restart_instance)(instance_id, arguments, date, interval)

