#!/usr/bin/env python3

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Sources of the Job rate_monitoring"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''


import time
import syslog
import signal
import argparse
import threading
from sys import exit
from functools import partial

import iptc
from apscheduler.schedulers.blocking import BlockingScheduler

import collect_agent


def signal_term_handler(chain, rule, signal, frame):
    chain.delete_rule(rule)
    exit(0)


def monitor(chain, mutex, previous):
    # Refresh the table (allowing to update the stats)
    table = iptc.Table(iptc.Table.FILTER)
    table.refresh()

    # Get the rule (Attention, the rule shall be in first position)
    rule = chain.rules[0]

    # Get the stats
    timestamp = int(time.perf_counter() * 1000)
    bytes_count = rule.get_counters()[1]

    # Get previous stats and update them
    with mutex:
        previous_timestamp, previous_bytes_count = previous
        previous[:] = timestamp, bytes_count

    diff_timestamp = (timestamp - previous_timestamp) / 1000  # in seconds
    rate = (bytes_count - previous_bytes_count) * 8 / diff_timestamp

    # Send the stat to the Collector
    collect_agent.send_stat(timestamp, rate=rate)


def main(interval, chain_name, jump, source, destination,
         protocol, in_interface, out_interface, dport, sport):
    # Connect to collect agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/rate_monitoring/'
            'rate_monitoring_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        exit(message)
    collect_agent.send_log(syslog.LOG_DEBUG, 'Starting job rate_monitoring')

    table = iptc.Table(iptc.Table.FILTER)
    chains = [chain for chain in table.chains if chain.name == chain_name]
    try:
        chain, = chains
    except ValueError:
        message = 'ERROR: {} does not exist in FILTER table'.format(chain_name)
        collect_agent.send_log(syslog.LOG_ERR, message)
        exit(message)

    # Creation of the Rule
    rule = iptc.Rule(chain=chain)
    signal.signal(signal.SIGTERM, partial(signal_term_handler, chain, rule))

    # Add Matchs
    if source is not None:
        rule.src = source
    if destination is not None:
        rule.dst = destination
    if protocol is not None:
        rule.protocol = protocol
    if in_interface is not None:
        rule.in_interface = in_interface
    if out_interface is not None:
        rule.out_interface = out_interface
    if sport is not None:
        match = iptc.Match(rule, protocol)
        match.sport = sport
        rule.add_match(match)
    if dport is not None:
        match = iptc.Match(rule, protocol)
        match.dport = dport
        rule.add_match(match)

    # Add the Target
    rule.create_target('' if jump is None else jump)
    chain.insert_rule(rule)

    collect_agent.send_log(syslog.LOG_DEBUG, "Added iptables rule for monitoring")

    # Save the first stats for computing the rate
    mutex = threading.Lock()
    previous = [int(time.perf_counter() * 1000), rule.get_counters()[1]]

    # Monitoring
    sched = BlockingScheduler()
    sched.add_job(
            monitor, 'interval',
            seconds=interval,
            args=(chain, mutex, previous))
    sched.start()


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
            'interval', type=int,
            help='Time interval (in sec) use to calculate rate')
    parser.add_argument('chain', help='Chain to use (INPUT, OUPUT, FORWARD…)')
    parser.add_argument('-j', '--jump', help='target')
    parser.add_argument('-s', '--source', help='source ip address')
    parser.add_argument('-d', '--destination', help='destination ip address')
    parser.add_argument('-p', '--protocol', help='protocol of the rule')
    parser.add_argument('-i', '--in-interface', help='input interface')
    parser.add_argument('-o', '--out-interface', help='output interface')
    parser.add_argument('--dport', help='destination port')
    parser.add_argument('--sport', help='source port')

    # get args
    args = parser.parse_args()
    interval = args.interval
    chain_name = args.chain
    jump = args.jump
    source = args.source
    destination = args.destination
    protocol = args.protocol
    out_interface = args.out_interface
    in_interface = args.in_interface
    dport = None if protocol is None else args.dport
    sport = None if protocol is None else args.sport

    main(interval, chain_name, jump, source, destination,
         protocol, in_interface, out_interface, dport, sport)
