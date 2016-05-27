#!/usr/bin/env python 
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
add_job.py - <+description+>
"""

import argparse
from frontend import add_job, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Add Job',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('path', help='Path of the sources') 

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    path = args.path

    pretty_print(add_job)(job_name, path)

