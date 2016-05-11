#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
add_agent.py - <+description+>
"""

from frontend import add_agent
import argparse
import pprint


def main(agent_ip, collector_ip, username, password, name):
    r = add_agent(agent_ip, collector_ip, username, password, name)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP Address of the Agent')
    parser.add_argument('collector_ip', metavar='collector_ip', type=str, nargs=1,
                        help='IP Address of the Collector')
    parser.add_argument('username', metavar='username', type=str, nargs=1,
                        help='Username of the Agent')
    parser.add_argument('password', metavar='password', type=str, nargs=1,
                        help='Password of the Agent')
    parser.add_argument('name', metavar='name', type=str, nargs=1,
                        help='Name of the Agent')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    collector_ip = args.collector_ip[0]
    username = args.username[0]
    password = args.password[0]
    name = args.name[0]

    main(agent_ip, collector_ip, username, password, name)

