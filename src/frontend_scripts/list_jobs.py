#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_jobs.py - <+description+>
"""

from frontend import list_jobs
import argparse
import pprint


def main():
    r = list_jobs()
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # get args
    args = parser.parse_args()

    main()

