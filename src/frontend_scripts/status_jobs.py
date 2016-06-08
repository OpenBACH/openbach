#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
status_jobs.py - <+description+>
"""

import argparse
from frontend import status_jobs, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Status Jobs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agents_ip', nargs='+',
                        help='IP Address of the Agents')
    
    # get args
    args = parser.parse_args()

    pretty_print(status_jobs)(args.agents_ip)

