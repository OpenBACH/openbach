#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
install_jobs.py - <+description+>
"""

import requests, json
import argparse


def main(jobs_name, agents_ip, date):
    url = "http://localhost:8000/conductor/jobs/install"

    payload = {'addresses': agents_ip, 'names': jobs_name}
    if date != None:
        payload['date'] = date
    
    r = requests.post(url, data={'data': json.dumps(payload)})
    print r
    print(r._content)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', metavar='job_name', type=str, nargs='+',
                        help='Name of the Jobs to install')
    parser.add_argument('agent_ip', metavar='agent_ip', type=str, nargs=1,
                        help='IP address of the agent')
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the installation')
    
    # get args
    args = parser.parse_args()
    jobs_name = args.job_name
    agent_ip = args.agent_ip[0]
    date = args.date
    # TODO On devra plus tard pouvoir demander l'install de plusieurs jobs sur
    # plusieurs agents
    agents_ip = list()
    agents_ip.append(agent_ip)

    main(jobs_name, agents_ip, date)

