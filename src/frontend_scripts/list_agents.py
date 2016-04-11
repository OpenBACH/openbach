#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_agents.py - <+description+>
"""

from frontend import list_agents
import argparse
import pprint


def main():
    r = list_agents()
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    
    # get args
    args = parser.parse_args()

    main()

