#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
get_job_help.py - <+description+>
"""

from frontend import get_job_help
import argparse


def main(job_name):
    r = get_job_help(job_name)
    print r
    print "Job name : " + r.json()['job_name']
    print r.json()['help']


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', metavar='job_name', type=str, nargs=1,
                        help='Name of the Job')
    
    # get args
    args = parser.parse_args()
    job_name = args.job_name[0]

    main(job_name)

