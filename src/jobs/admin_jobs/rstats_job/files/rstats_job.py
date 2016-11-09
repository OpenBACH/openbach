#!/usr/bin/python
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
   
   
   
   @file     rstats_job.py
   @brief    Sources of the Job rstats_job
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import subprocess
import argparse
from os import rename


def main(job_instance_id, job_name):
    path = '/opt/openbach-jobs/{}/'.format(job_name)
    filename1 = '{}{}_rstats_filter.conf'.format(job_name, job_instance_id)
    filename2 = '{}_rstats_filter.conf'.format(job_name)
    rename('{}{}.locked'.format(path, filename1), '{}{}'.format(path,
                                                                filename2))

    cmd = 'service rstats reload'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('job_name', metavar='job_name', type=str,
                        help='The name of the Job you want to change the logs'
                        ' policy')

    # get args
    args = parser.parse_args()
    job_instance_id = args.job_instance_id
    job_name = args.job_name

    main(job_instance_id, job_name)
