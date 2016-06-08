#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_instances.py - <+description+>
"""

import argparse
from frontend import list_instances, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - List Instances',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agents_ip', nargs='+', help='IP addresses of the Agents')
    parser.add_argument('-u', '--update', action='store_true',
                        help='Use only the last status present on the collector')
    
    # get args
    args = parser.parse_args()
    agents_ip = args.agents_ip
    update = args.update

    pretty_print(list_instances)(agents_ip, update)

