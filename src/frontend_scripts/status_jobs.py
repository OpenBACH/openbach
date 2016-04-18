#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
status_jobs.py - <+description+>
"""

from frontend import status_jobs
import argparse
import pprint


def main(agents_ip):
    r = status_jobs(agents_ip)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agents_ip', metavar='agents_ip', type=str, nargs='+',
                        help='IP Address of the Agents')
    
    # get args
    args = parser.parse_args()
    agents_ip = args.agents_ip

    main(agents_ip)

