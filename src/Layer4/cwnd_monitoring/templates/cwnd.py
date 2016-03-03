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
 
def main(path, stat_name, interval):
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
    parser.add_argument('stat_name', metavar='stat_name', type=str, nargs=1,
                        help='Name of the statistic')
    parser.add_argument('-p', '--path', type=str,
                        default='/tmp/tcpprobe.out',
                        help='path to result file')
    parser.add_argument('-i', '--interval', type=int, default=10,
                        help='get the cwnd of 1/interval packet')
    
    # get args
    args = parser.parse_args()
    stat_name = args.stat_name[0]
    path = args.path
    interval = args.interval
    
    main(path, stat_name, interval)

