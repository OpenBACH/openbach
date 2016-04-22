#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
cwnd.py - Process congestion window
"""

import argparse
import socket
import syslog
import errno
import time
import os
import sys
import signal


def signal_term_handler(signal, frame):
    cmd = "PID=`cat /var/run/cwnd.pid`; kill -HUP $PID; rm "
    cmd += "/var/run/cwnd.pid"
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
    cmd = "insmod /opt/openbach-plugins/cwnd_monitoring/tcp_probe_new_fix.ko"
    cmd += " port=" + str(port) + " full=1 > /dev/null 2>&1"
    os.system(cmd)
    cmd = "chmod 444 /proc/net/tcpprobe"
    os.system(cmd)
    cmd = "PID=`cat /proc/net/tcpprobe > " + path + " & echo $!`; echo $PID >"
    cmd += " /var/run/cwnd.pid"
    os.system(cmd)

    # Contruction du nom de la stat
    f = open("/etc/hostname", "r")
    stat_name = f.readline().split('\n')[0]
    f.close()
    stat_name += ".cwnd." + str(port)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("", 1111))
    except socket.error as serr:
        if serr.errno == errno.ECONNREFUSED:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Connexion to rstats refused, maybe rstats service isn't started")
        raise serr
    s.send("1 /opt/openbach-plugins/cwnd_monitoring/cwnd_rstats_filter.conf")
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
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.connect(("", 1111))
                    cmd = "2 " + connection_id + " " + stat_name + " " + \
                    str(timestamp) + " value " + cwnd
                    s.send(cmd)
                    r = s.recv(9999)
                    s.close()
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

