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
   
   
   
   @file     tcp_buffer.py
   @brief    Sources of the Job tcp_buffer
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import subprocess


def main(name, min_size, size, max_size):
    cmd = 'sysctl net.ipv4.tcp_{}=\'{} {} {}\''.format(
        name, min_size, size, max_size)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('name', type=str,
                        help='The name of the tcp buffer to set')
    parser.add_argument('min_size', type=int,
                        help='The minial size of the buffer')
    parser.add_argument('size', type=int, help='The size of the buffer')
    parser.add_argument('max_size', type=int,
                        help='The maximum size of the buffer')
    parser.add_argument('-sii', '--scenario-instance-id', type=int,
                        help='The Id of the Scenario Instance')

    # get args
    args = parser.parse_args()
    name = args.name
    min_size = args.min_size
    size = args.size
    max_size = args.maw_size

    main(name, min_size, size, max_size)

