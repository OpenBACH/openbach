#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
stop_job.py - <+description+>
"""

import requests, json
import argparse
import pprint


def main(instance_id, date):
    url = "http://localhost:8000/conductor/instances/stop"

    payload = {'instance_id': instance_id}
    if date != None:
        payload['date'] = date
    
    r = requests.post(url, data={'data': json.dumps(payload)})
    print r
    pprint.pprint(r.json())


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('instance_id', metavar='instance_id', type=str, nargs=1,
                        help='Id of the instance')
    parser.add_argument('-d', '--date', type=str, default=None,
                        help='Date of the execution')
    
    # get args
    args = parser.parse_args()
    instance_id = args.instance_id[0]
    date = args.date

    main(instance_id, date)

