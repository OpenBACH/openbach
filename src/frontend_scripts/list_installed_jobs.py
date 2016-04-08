#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_installed_jobs.py - <+description+>
"""

import requests
import argparse


def main(agent_ip):
    url = "http://localhost:8000/conductor/" + agent_ip + "/jobs/list"

    r = requests.get(url)
    print r
    print(r._content)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP Address of the Agent')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]

    main(agent_ip)

