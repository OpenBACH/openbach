#!/usr/bin/env python 
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
add_agent.py - <+description+>
"""

import argparse
from frontend import add_agent, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Add Agent',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    parser.add_argument('collector_ip', help='IP Address of the Collector')
    parser.add_argument('username', help='Username of the Agent')
    parser.add_argument('password', help='Password of the Agent')
    parser.add_argument('name', help='Name of the Agent')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    collector_ip = args.collector_ip
    username = args.username
    password = args.password
    name = args.name

    pretty_print(add_agent)(agent_ip, collector_ip, username, password, name)

