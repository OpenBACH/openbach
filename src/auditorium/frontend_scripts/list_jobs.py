#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_jobs.py - <+description+>
"""

import argparse
from frontend import list_jobs, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - List Jobs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # get args
    args = parser.parse_args()

    pretty_print(list_jobs)()
