#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_installed_jobs.py - <+description+>
"""

from frontend import list_installed_jobs
import argparse
import pprint


def main(agent_ip, update):
    r = list_installed_jobs(agent_ip, update=update)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP Address of the Agent')
    parser.add_argument('-u', '--update', action='store_true', help='With this '
                        'option, the status is the last one present on the collector')
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip[0]
    update = args.update

    main(agent_ip, update)

