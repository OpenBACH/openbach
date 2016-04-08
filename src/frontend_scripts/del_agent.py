#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
del_agent.py - <+description+>
"""

import requests, json
import argparse
import pprint


def main(agent_ip, date):
    url = "http://localhost:8000/conductor/agents/del"

    payload = {'address': agent_ip}
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
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the installation')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    date = args.date

    main(agent_ip, date)

