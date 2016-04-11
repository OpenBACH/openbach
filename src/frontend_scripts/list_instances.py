#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_instances.py - <+description+>
"""

from frontend import list_instances
import argparse
import pprint


def main(agent_ip):
    responses = list_instances(agent_ip)
    for i in range(len(responses)):
        r = responses[i]
        print r
        pprint.pprint(r.json())


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

