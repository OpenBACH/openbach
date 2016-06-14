#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
del_job.py - <+description+>
"""

import argparse
from frontend import del_job, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Delete Job',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_name', help='Name of the Job')
    
    # get args
    args = parser.parse_args()
    job_name = args.job_name

    pretty_print(del_job)(job_name)

