#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
uninstall_agent.py - <+description+>
"""

import argparse
from frontend import uninstall_agent, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Delete Agent',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip

    pretty_print(uninstall_agent)(agent_ip)

