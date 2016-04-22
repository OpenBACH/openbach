#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
rate.py - <+description+>
"""

import time
import argparse
import iptc
import threading
import socket
import syslog
import errno
import signal
import sys
from apscheduler.schedulers.blocking import BlockingScheduler



def signal_term_handler(signal, frame):
    chain.delete_rule(rule)
    sys.exit(0)
              
signal.signal(signal.SIGHUP, signal_term_handler)


def monitor():
    global chain
    global connection_id
    global mutex
    global previous_bytes_count
    global previous_timestamp
    
    # Contruction du nom de la stat
    f = open("/etc/hostname", "r")
    stat_name = f.readline().split('\n')[0]
    f.close()
    stat_name += ".rate"
    
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
    value_name = "rate"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("", 1111))
    cmd = "2 " + connection_id + " " + stat_name + " " + \
    str(timestamp) + " " + value_name + " " +  str(rate)
    s.send(cmd)
    r = s.recv(9999)
    s.close()
    
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
    
    # Connexion au service de collecte de l'agent
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("", 1111))
    except socket.error as serr:
        if serr.errno == errno.ECONNREFUSED:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Connexion to rstats refused, maybe rstats service isn't started")
        raise serr
    s.send("1 /opt/openbach-plugins/rate_monitoring/rate_monitoring_rstats_filter.conf")
    r = s.recv(9999)
    s.close()
    data = r.split(" ")
    if data[0] == 'OK':
        if len(data) != 2:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            quit()
        try:
            int(data[1])
        except:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            quit()
        connection_id = data[1]
        syslog.syslog(syslog.LOG_NOTICE, "NOTICE: Identifiant de connexion = " + connection_id)
    elif data[0] == 'KO':
        syslog.syslog(syslog.LOG_ERR, "ERROR: Something went wrong :")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
        quit()
    else:
        syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
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
    
