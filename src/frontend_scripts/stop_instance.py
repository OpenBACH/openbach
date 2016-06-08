#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
stop_instance.py - <+description+>
"""

import argparse
from frontend import stop_instance, date_to_timestamp, pretty_print


class DateMetavarHelper:
    def __init__(self):
        self.first = False

    def __repr__(self):
        self.first = not self.first
        return 'DATE' if self.first else 'TIME'


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Stop Instance',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_ids', nargs='+', help='Id of the instance')
    parser.add_argument('-d', '--date', metavar=DateMetavarHelper(),
                        nargs=2, help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    instance_ids = args.instance_ids
    date = date_to_timestamp('{} {}'.format(*args.date)) if args.date else None

    pretty_print(stop_instance)(instance_ids, date)

