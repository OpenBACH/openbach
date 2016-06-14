#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
push_file.py - <+description+>
"""

import argparse
from frontend import push_file, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Push File',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('local_path', help='Path of the file in the Controller')
    parser.add_argument('remote_path', help='Path where the file should be pushed')
    parser.add_argument('agent_ip', help='IP address of the Agent')
    
    # get args
    args = parser.parse_args()
    local_path = args.local_path
    remote_path = args.remote_path
    agent_ip = args.agent_ip

    pretty_print(push_file)(local_path, remote_path, agent_ip)

