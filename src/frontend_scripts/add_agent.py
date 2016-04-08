#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
add_agent.py - <+description+>
"""

import requests, json
import argparse
import pprint


def main(agent_ip, collector_ip, username, password, name, date):
    url = "http://localhost:8000/conductor/agents/add"

    payload = {'address': agent_ip, 'username': username, 'password':
               password, 'collector': collector_ip}
    if name != None:
        payload['name'] = name
    if date != None:
        payload['date'] = date
    
    r = requests.post(url, data={'data': json.dumps(payload)})
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
    parser.add_argument('-n', '--name', type=str, default=None,
                        help='Name of the Agent')
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the installation')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    collector_ip = args.collector_ip[0]
    username = args.username[0]
    password = args.password[0]
    name = args.name
    date = args.date

    main(agent_ip, collector_ip, username, password, name, date)

