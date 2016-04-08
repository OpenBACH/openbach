#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_agents.py - <+description+>
"""

import requests
import argparse


def main():
    url = "http://localhost:8000/conductor/agents/list"

    r = requests.get(url)
    print r
    print(r._content)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # get args
    args = parser.parse_args()

    main()

