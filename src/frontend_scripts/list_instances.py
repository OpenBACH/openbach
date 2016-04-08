#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_instances.py - <+description+>
"""

import requests
import argparse


def main(agent_ip):
    if agent_ip == None:
        url = ["http://localhost:8000/conductor/instances/list"]
    else:
        url = list()
        for i in agent_ip:
            url.append("http://localhost:8000/conductor/" + i +
                       "/instances/list")

    for i in range(len(url)):
        r = requests.get(url[i])
        print r
        print(r._content)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-a', '--agent-ip', type=str, default=None,
                        nargs ='+', help='Ip Address of the Agents')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip

    main(agent_ip)

