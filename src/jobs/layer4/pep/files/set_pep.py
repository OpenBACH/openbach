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
   
   
   
   @file     set_pep.py
   @brief    Sources of the Job Pep (start)
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import argparse
import subprocess


def main(sat_network, pep_port):
    cmd = 'ip rule add fwmark 1 lookup 100'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'ip route add local 0.0.0.0/0 dev lo table 100'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_mem'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_rmem'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_wmem'
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'iptables -A PREROUTING -t mangle -p tcp -m tcp -s'
    cmd = '{} {} -j TPROXY --on-port {} --tproxy-mark 1'.format(
        sat_network, pep_port)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'iptables -A PREROUTING -t mangle -p tcp -m tcp -d'
    cmd = '{} {} -j TPROXY --on-port {} --tproxy-mark 1'.format(
        sat_network, pep_port)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()

    cmd = 'pepsal -d -p {}'.format(pep_port)
    p = subprocess.Popen(cmd, shell=True)
    p.wait()


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('sat_network', type=str,
                        help='The network of the satellite link')
    parser.add_argument('-p', '--pep-port', type=int, default=5002,
                        help='The port to use')

    # get args
    args = parser.parse_args()
    sat_network = args.sat_network
    pep_port = args.pep_port

    main(sat_network, pep_port)

