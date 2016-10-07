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
   
   
   
   @file     rate_monitoring.py
   @brief    Sources of the Job rate_monitoring
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import subprocess
import argparse
import time
import sys
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats


def main(job_instance_id, scenario_instance_id, destination_ip, count, interval,
         interface, packetsize, ttl, duration):
    conffile = "/opt/openbach-jobs/ping/ping_rstats_filter.conf"

    cmd = 'ping {}'.format(destination_ip)
    if count:
        cmd = '{} -c {}'.format(cmd, count)
    if interval:
        cmd = '{} -i {}'.format(cmd, interval)
    if interface:
        cmd = '{} -I {}'.format(cmd, interface)
    if packetsize:
        cmd = '{} -s {}'.format(cmd, packetsize)
    if ttl:
        cmd = '{} -t {}'.format(cmd, ttl)
    if duration:
        cmd = '{} -w {}'.format(cmd, duration)

    p = subprocess.Popen(cmd, shell=True)
    p.wait()
    if p.returncode:
        stat_name = 'ping'
        # Connexion au service de collecte de l'agent
        connection_id = rstats.register_stat(conffile, 'ping')
        if connection_id == 0:
            quit()
        # Envoie de la stat au collecteur
        timestamp = int(round(time.time() * 1000))
        if not scenario_instance_id:
            scenario_instance_id = 0
        statistics = { 'status': 'Error', 'job_instance_id': job_instance_id,
                       'scenario_instance_id': scenario_instance_id }
        r = rstats.send_stat(connection_id, stat_name, timestamp, **statistics)


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('job_instance_id', metavar='job_instance_id', type=int,
                        help='The Id of the Job Instance')
    parser.add_argument('destination_ip', metavar='destination_ip', type=str,
                        help='')
    parser.add_argument('-sii', '--scenario-instance-id', type=int,
                        help='The Id of the Scenario Instance')
    parser.add_argument('-c', '--count', type=int,
                        help='')
    parser.add_argument('-i', '--interval', type=int,
                        help='')
    parser.add_argument('-I', '--interface', type=str,
                        help='')
    parser.add_argument('-s', '--packetsize', type=int,
                        help='')
    parser.add_argument('-t', '--ttl', type=int,
                        help='')
    parser.add_argument('-w', '--duration', type=int,
                        help='')

    # get args
    args = parser.parse_args()
    job_instance_id = args.job_instance_id
    scenario_instance_id = args.scenario_instance_id
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    interface = args.interface
    packetsize = args.packetsize
    ttl = args.ttl
    duration = args.duration

    main(job_instance_id, scenario_instance_id, destination_ip, count, interval,
         interface, packetsize, ttl, duration)

