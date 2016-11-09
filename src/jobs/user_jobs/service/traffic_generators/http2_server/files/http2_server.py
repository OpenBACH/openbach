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
   
   
   
   @file     http2_server.py
   @brief    Sources of the Job http2_server
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import subprocess
import argparse


def main(port, no_tls):
    cmd = 'nghttpd {}'.format(port)
    if no_tls:
        cmd = '{} --no-tls'.format(cmd)

    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('port', metavar='port', type=int,
                        help='Port where the server id available')
    parser.add_argument('-n', '--no-tls', action='store_true',
                        help='Disable SSL/TLS')

    # get args
    args = parser.parse_args()
    port = args.port
    no_tls = args.no_tls

    main(port, no_tls)

