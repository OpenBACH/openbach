#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" 
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).
   
   
   Copyright © 2016 CNES
   
   
   This file is part of the OpenBACH testbed.
   
   
   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.
   
   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.
   
   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.
   
   
   
   @file     send_logs.py
   @brief    Sources of the Job send_logs
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import datetime
import syslog
import yaml
import socket
try:
    import simplejson as json
except ImportError:
    import json
from os import listdir


# Configure logger
syslog.openlog("send_logs", syslog.LOG_PID, syslog.LOG_USER)


def send_logs(path, filename, address, port):
    with open('{}{}'.format(path, filename), 'r') as f:
        lines = f.readlines()
        for line in lines:
            line_json = json.loads(line)
            pri = line_json.pop('pri')
            timestamp = line_json.pop('timestamp')
            hostname = line_json.pop('hostname')
            programname = line_json.pop('programname')
            procid = line_json.pop('procid')
            msg = line_json.pop('msg')
            msg_to_send = '<{}>{} {} {}[{}]: {}'.format(pri, timestamp,
                                                        hostname, programname,
                                                        procid, msg)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            except socket.error:
                syslog.syslog(syslog.LOG_NOTICE, 'Failed to create socket')
                raise
            try:
                s.sendto(msg_to_send.encode(), (address, int(port)))
            except socket.error as msg:
                syslog.syslog(syslog.LOG_NOTICE, 'Error code: {}, Message'
                              ' {}'.format(*msg))
                raise


def main(job_name, date):
    config_file = '/opt/openbach-agent/collector.yml'
    try:
        with open(config_file, 'r') as stream:
            try:
                content = yaml.load(stream)
            except yaml.YAMLError:
                syslog.syslog(syslog.LOG_NOTICE, 'Collector configuration file'
                              ' is malformed')
                raise
    except FileNotFoundError:
        syslog.syslog(syslog.LOG_NOTICE, 'Collector configuration file not'
                      ' found')
        raise
    try:
        address = content['address']
        port = content['logs']['port']
    except KeyError:
        syslog.syslog(syslog.LOG_NOTICE, 'Collector configuration file is'
                      ' malformed')
        raise

    path = '/var/log/openbach/'
    d = datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    l = listdir(path)

    for filename in l:
        if filename.startswith(job_name):
            f = filename[len(job_name)+1:]
            if f.endswith('.log'):
                f = f[:len(f)-4]
                file_date = datetime.datetime.strptime(f, '%Y-%m-%dT%H%M%S')
                if file_date >= d:
                    send_logs(path, filename, address, port)

    syslog.closelog()


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('job_name', help='Name of the Job')
    parser.add_argument('date', nargs=2, help='Date of the execution')
    parser.add_argument('-sii', '--scenario-instance-id', type=int,
                        help='The Id of the Scenario Instance')

    # get args
    args = parser.parse_args()
    job_name = args.job_name
    date = '{} {}'.format(*args.date)

    main(job_name, date)

