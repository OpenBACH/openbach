#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_agents.py - <+description+>
"""

import argparse
from frontend import status_agents, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Status Agent',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agents_ip', help='IP address of the Agents', nargs='+')
    
    # get args
    args = parser.parse_args()

    pretty_print(status_agents)(args.agents_ip)

