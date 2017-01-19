#!/usr/bin/env python 
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


import time
import argparse
import iptc
import threading
import syslog
import signal
from sys import exit
from apscheduler.schedulers.blocking import BlockingScheduler
import collect_agent


def signal_term_handler(signal, frame):
    chain.delete_rule(rule)
    exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)


def monitor():
    global chain
    global mutex
    global previous_bytes_count
    global previous_timestamp

    # Refresh the table (allowing to update the stats)
    table = iptc.Table(iptc.Table.FILTER)
    table.refresh()

    # Get the rule (Attention, the rule shall be in first position)
    rule = chain.rules[0]

    # Get the stats
    timestamp = int(round(time.time() * 1000))
    bytes_count = rule.get_counters()[1]

    # Compute data rate
    mutex.acquire()
    diff_timestamp = float(timestamp - previous_timestamp) / 1000 # in seconds
    rate = float(bytes_count - previous_bytes_count)/diff_timestamp
    mutex.release()

    # Send the stat to the Collector
    statistics = {'rate': rate}
    r = collect_agent.send_stat(timestamp, **statistics)

    # Update the old stats for the next computation of the data rate
    mutex.acquire()
    previous_bytes_count = bytes_count
    previous_timestamp = timestamp
    mutex.release()


def main(rule, interval):
    global chain
    global mutex
    global previous_bytes_count
    global previous_timestamp

    # To add the rule
    chain.insert_rule(rule)

    # Save the first stats for computing the rate
    mutex = threading.Lock()
    previous_timestamp = int(round(time.time() * 1000))
    previous_bytes_count = rule.get_counters()[1]

    # Monitoring
    sched = BlockingScheduler()
    sched.add_job(monitor, 'interval', seconds=interval)
    sched.start()


if __name__ == "__main__":
    global chain
    conffile = "/opt/openbach-jobs/rate_monitoring/rate_monitoring_rstats_filter.conf"

    # Connect to collect agent
    success = collect_agent.register_collect(conffile)
    if not success:
        quit()

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('interval', metavar='interval', type=int, nargs=1,
                        help='Time interval (in sec) use to calculate rate')
    parser.add_argument('chain', metavar='chain', type=str, nargs=1,
                        help='Chain to use (INPUT or FORWARD)')
    parser.add_argument('-j', '--jump', type=str, nargs=1,
                        help='target')
    parser.add_argument('-s', '--source', type=str, nargs=1,
                        help='source ip address')
    parser.add_argument('-d', '--destination', type=str, nargs=1,
                        help='destination ip address')
    parser.add_argument('-p', '--protocol', type=str, nargs=1,
                        help='protocol of the rule')
    parser.add_argument('-i', '--in-interface', type=str, nargs=1,
                        help='input interface')
    parser.add_argument('-o', '--out-interface', type=str, nargs=1,
                        help='output interface')
    parser.add_argument('--dport', type=str, nargs=1,
                        help='destination port')
    parser.add_argument('--sport', type=str, nargs=1,
                        help='source port')

    # get args
    args = parser.parse_args()
    interval = args.interval[0]
    chain_name = args.chain[0]
    if type(args.jump) == list:
        jump = args.jump[0]
    else:
        jump = None
    if type(args.source) == list:
        source = args.source[0]
    else:
        source = None
    if type(args.destination) == list:
        destination = args.destination[0]
    else:
        destination = None
    if type(args.protocol) == list:
        protocol = args.protocol[0]
    else:
        protocol = None
    if type(args.out_interface) == list:
        out_interface = args.out_interface[0]
    else:
        out_interface = None
    if type(args.in_interface) == list:
        in_interface = args.in_interface[0]
    else:
        in_interface = None
    if type(args.dport) == list and protocol != None:
        dport = args.dport[0]
    else:
        dport = None
    if type(args.sport) == list and protocol != None:
        sport = args.sport[0]
    else:
        sport = None

    # Get the table ('filter')
    table = iptc.Table(iptc.Table.FILTER)

    # Get the chain
    chain = None
    for c in table.chains:
        if c.name == chain_name:
            chain = c
            continue
    if chain == None:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR: " + chain_name + " does not exist in FILTER table")
        exit(1)

    # Creation of the Rule
    rule = iptc.Rule(chain=chain)

    # Add Matchs
    if source != None:
       rule.src = source 
    if destination != None:
        rule.dst = destination
    if protocol != None:
        rule.protocol = protocol
    if in_interface != None:
        rule.in_interface = in_interface
    if out_interface != None:
        rule.out_interface = out_interface
    if sport != None:
        match = iptc.Match(rule, protocol)
        match.sport = sport
        rule.add_match(match)
    if dport != None:
        match = iptc.Match(rule, protocol)
        match.dport = dport
        rule.add_match(match)

    # Add the Target
    if jump != None:
        rule.create_target(jump)
    else:
        rule.create_target("")

    main(rule, interval)

