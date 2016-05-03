#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
push_file.py - <+description+>
"""

from frontend import push_file
import argparse
import pprint


def main(local_path, remote_path, agent_ip):
    r = push_file(local_path, remote_path, agent_ip)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('local_path', metavar='local_path', type=str, nargs=1,
                        help='Path of the file in the Controller')
    parser.add_argument('remote_path', metavar='remote_path', type=str, nargs=1,
                        help='Path where the file should be pushed')
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP address of the Agent')
    
    # get args
    args = parser.parse_args()
    local_path = args.local_path[0]
    remote_path = args.remote_path[0]
    agent_ip = args.agent_ip[0]

    main(local_path, remote_path, agent_ip)

