#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_installed_jobs.py - <+description+>
"""

import argparse
from frontend import list_installed_jobs, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - List installed jobs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    parser.add_argument('-u', '--update', action='store_true',
        help='Use only the last status present on the collector')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    update = args.update

    pretty_print(list_installed_jobs)(agent_ip, update)

