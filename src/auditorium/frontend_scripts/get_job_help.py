#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
get_job_help.py - <+description+>
"""

import argparse
from frontend import get_job_help


def pretty_print(job_name):
    response = get_job_help(job_name)
    print(response)

    infos = response.json()
    if 'help' in infos:
        print('Job name:', infos['job_name'])
        print(infos['help'])
    else:
        print(infos)
    if 400 <= response.status_code < 600:
        exit(1)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Display Job Help',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    
    # get args
    args = parser.parse_args()
    job_name = args.job_name

    pretty_print(job_name)

