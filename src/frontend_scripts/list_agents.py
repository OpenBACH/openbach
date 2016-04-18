#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
list_agents.py - <+description+>
"""

from frontend import list_agents
import argparse
import pprint


def main(update):
    r = list_agents(update)
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-u', '--update', action='store_true', help='With this '
                        'option, the status is the last one present on the collector')
    
    # get args
    args = parser.parse_args()
    update = args.update

    main(update)

