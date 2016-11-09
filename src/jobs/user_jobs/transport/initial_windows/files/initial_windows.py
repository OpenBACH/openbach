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
   
   
   
   @file     initial_windows.py
   @brief    Sources of the Job initial_windows
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import subprocess


def main(network, gw, interface, initcwnd, initrwnd):
    cmd = 'ip route change {} via {} dev {} initcwnd {} initrwnd {}'.format(
        network, gw, interface, initcwnd, initrwnd)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('network', type=str, help='The destination network')
    parser.add_argument('gw', type=str, help='The next hop of the route')
    parser.add_argument('interface', type=str,
                        help='Interface where to set the initial windows')
    parser.add_argument('initcwnd', type=int, help='Initial congestion window')
    parser.add_argument('initrwnd', type=int,
                        help='Initial congestion receipt window')

    # get args
    args = parser.parse_args()
    network = args.network
    gw = args.gw
    interface = args.interface
    initcwnd = args.initcwnd
    initrwnd = args.initrwnd

    main(network, gw, interface, initcwnd, initrwnd)

