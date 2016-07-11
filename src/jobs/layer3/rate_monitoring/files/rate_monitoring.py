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
import sys
from apscheduler.schedulers.blocking import BlockingScheduler
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats



def signal_term_handler(signal, frame):
    chain.delete_rule(rule)
    sys.exit(0)
              
signal.signal(signal.SIGTERM, signal_term_handler)


def monitor():
    global chain
    global connection_id
    global mutex
    global previous_bytes_count
    global previous_timestamp
    
    # Contruction du nom de la stat
    stat_name = "rate_monitoring"
    
    # Refresh de la table (pour avoir des stats a jour)
    table = iptc.Table(iptc.Table.FILTER)
    table.refresh()
    
    # Recuperation de la rule (Attention, il faut qu'elle soit en 1ere position)
    rule = chain.rules[0]
    
    # Recuperation des stats
    timestamp = int(round(time.time() * 1000))
    bytes_count = rule.get_counters()[1]
    
    # Calcul du debit
    mutex.acquire()
    diff_timestamp = float(timestamp - previous_timestamp) / 1000 # in seconds
    rate = float(bytes_count - previous_bytes_count)/diff_timestamp
    mutex.release()
    
    # Envoie de la stat au collecteur
    r = rstats.send_stat(connection_id, stat_name, timestamp, "rate", rate)
    
    # Mise a jour des vieilles stats pour le prochain calcul de debit
    mutex.acquire()
    previous_bytes_count = bytes_count
    previous_timestamp = timestamp
    mutex.release()


def main(rule, interval):
    global chain
    global connection_id
    global mutex
    global previous_bytes_count
    global previous_timestamp
    
    conffile = "/opt/openbach-jobs/rate_monitoring/rate_monitoring_rstats_filter.conf"
    
    # Connexion au service de collecte de l'agent
    connection_id = rstats.register_stat(conffile, 'rate_monitoring')
    if connection_id == 0:
        quit()
    

    # On insere la règle
    chain.insert_rule(rule)
    
    # On enregistre les premieres stats pour le calcul du debit
    mutex = threading.Lock()
    previous_timestamp = int(round(time.time() * 1000))
    previous_bytes_count = rule.get_counters()[1]
    
    # On monitor
    sched = BlockingScheduler()
    sched.add_job(monitor, 'interval', seconds=interval)
    sched.start()


if __name__ == "__main__":
    global chain
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

    # Recuperation de la Table (ce sera toujours 'filter')
    table = iptc.Table(iptc.Table.FILTER)
    
    # Recuperation de la Chain
    chain = None
    for c in table.chains:
        if c.name == chain_name:
            chain = c
            continue
    if chain == None:
        syslog.syslog(syslog.LOG_ERR, "ERROR: " + chain_name + " does not exist in FILTER table")
        exit(1)

    # Creation de la Rule
    rule = iptc.Rule(chain=chain)
    
    # Ajout des Matchs
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

    # Ajout de la Target
    if jump != None:
        rule.create_target(jump)
    else:
        rule.create_target("")

    main(rule, interval)
    
