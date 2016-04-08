#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_jobs.py - <+description+>
"""

import requests
import argparse
import pprint


def main():
    url = "http://localhost:8000/conductor/jobs/list"

    r = requests.get(url)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # get args
    args = parser.parse_args()

    main()

