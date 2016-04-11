#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
install_jobs.py - <+description+>
"""

from frontend import install_jobs
import argparse
import pprint


def main(jobs_name, agents_ip):
    r = install_jobs(jobs_name, agents_ip)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', metavar='job_name', type=str, nargs='+',
                        help='Name of the Jobs to install')
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP address of the agent')
    
    # get args
    args = parser.parse_args()
    jobs_name = args.job_name
    agent_ip = args.agent_ip[0]
    # TODO On devra plus tard pouvoir demander l'install de plusieurs jobs sur
    # plusieurs agents
    agents_ip = list()
    agents_ip.append(agent_ip)

    main(jobs_name, agents_ip)

