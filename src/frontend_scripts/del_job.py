#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
del_job.py - <+description+>
"""

from frontend import del_job
import argparse
import pprint


def main(job_name):
    r = del_job(job_name)
    print r
    pprint.pprint(r.json())


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

