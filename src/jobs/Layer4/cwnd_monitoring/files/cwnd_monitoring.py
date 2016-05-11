#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
cwnd_monitoring.py - Process congestion window
"""

import argparse
import time
import os
import sys
import signal
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats


def signal_term_handler(signal, frame):
    cmd = "PID=`cat /var/run/cwnd_monitoring.pid`; kill -HUP $PID; rm "
    cmd += "/var/run/cwnd_monitoring.pid"
    os.system(cmd)
    cmd = "rmmod tcp_probe_new_fix > /dev/null 2>&1"
    os.system(cmd)
    sys.exit(0)
                 
signal.signal(signal.SIGHUP, signal_term_handler)
signal.signal(signal.SIGTERM, signal_term_handler)


def watch(fn):
    fp = open(fn, 'r')
    while True:
        new = fp.readline()
        # TODO: (Piste 2) Indiquer la ligne en cour de lecture
        # Once all lines are read this just returns ''
        # until the file changes and a new line appears
                                        
        if new:
            yield new
        else:
            # TODO: (Piste1) Indiquer au script stop qu'il peut stopper le
            # processus
            time.sleep(0.5)
            # TODO: (Piste1) Ne plus l'indiquer
 
def main(path, port, interval):
    # Mise en place du monitoring
    cmd = "insmod /opt/openbach-jobs/cwnd_monitoring/tcp_probe_new_fix.ko"
    cmd += " port=" + str(port) + " full=1 > /dev/null 2>&1"
    os.system(cmd)
    cmd = "chmod 444 /proc/net/tcpprobe"
    os.system(cmd)
    cmd = "PID=`cat /proc/net/tcpprobe > " + path + " & echo $!`; echo $PID >"
    cmd += " /var/run/cwnd_monitoring.pid"
    os.system(cmd)

    # Contruction du nom de la stat
    stat_name = "cwnd_monitoring." + str(port)
    
    conffile = "/opt/openbach-jobs/cwnd_monitoring/cwnd_monitoring_rstats_filter.conf"

    # Connexion au service de collecte de l'agent
    connection_id = rstats.register_stat(conffile)
    if connection_id == 0:
        quit()

    i = 1
    for row in watch(path):
        if i == interval:
            data = row.split(' ')
            if len(data) == 11:
                timestamp = data[0]
                timestamp_sec = timestamp.split('.')[0]
                timestamp_nsec = timestamp.split('.')[1]
                timestamp = timestamp_sec + timestamp_nsec[:3]
                cwnd = data[6]
                try:
                    # Envoie de la stat au collecteur
                    r = rstats.send_stat(connection_id, stat_name, timestamp,
                                         "value", cwnd)
                except Exception as ex: 
                    print "Erreur: %s" % ex
            i = 1
        else:
            i += 1


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='Active/Deactive cwnd monitoring.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('port', metavar='port', type=int, nargs=1,
                        help='Port to monitor')
    parser.add_argument('-p', '--path', type=str,
                        default='/tmp/tcpprobe.out',
                        help='path to result file')
    parser.add_argument('-i', '--interval', type=int, default=10,
                        help='get the cwnd of 1/interval packet')
    
    # get args
    args = parser.parse_args()
    port = args.port[0]
    path = args.path
    interval = args.interval
    
    main(path, port, interval)

