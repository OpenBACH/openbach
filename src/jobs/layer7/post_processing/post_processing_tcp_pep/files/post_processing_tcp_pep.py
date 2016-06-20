#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
post_processing_tcp_pep.py - <+description+>
"""

import subprocess
import json
import argparse
import sys
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats


def main(collector, port, begin, end, simu_name, database_name, username,
         password):
    conffile = "/opt/openbach-jobs/post_processing_tcp_pep/post_processing_tcp_pep_rstats_filter.conf"

    cmd = "curl -G 'http://" + collector + ":" + str(port) + "/query' --data-url"
    cmd += "encode \"db=" + database_name + "\"" + " --data-urlencode \"epoch=m"
    cmd += "s\" --data-urlencode \"q=select status from \\\"" + simu_name + "\\"
    cmd += "\" where time >= " + str(begin) + "ms"
    if end != 0:
        cmd += " and time <= " + str(end) + "ms"
    cmd += "\""
    print cmd
    
    result = subprocess.check_output(cmd, shell=True)
    print result
    test = json.loads(result)
    
    started = []
    finished = []
    print test
    for e in test['results'][0]['series'][0]['values']:
        if e[1] == 'started':
            started.append(e[0])
        elif e[1] == 'finished':
            finished.append(e[0])
    
    print started
    print finished
    
    if len(started) != len(finished):
        exit()
    
    for i in range(len(started)):
        cmd = "curl -G 'http://" + collector + ":" + str(port) + "/query' --dat"
        cmd += "a-urlencode \"db=" + database_name + "\" --data-urlencode \"epo"
        cmd += "ch=ms\" --data-urlencode \"q=select value from \\\"" + simu_name
        cmd += "\\\" where time >= " + str(started[i]) + "ms AND time <= "
        cmd += str(finished[i]) + "ms\""
        
        result = subprocess.check_output(cmd, shell=True)
        
        test = json.loads(result)
        cpt = 0
        mean = 0
        for e in test['results'][0]['series'][0]['values']:
            cpt += 1
            mean += e[1]
        mean /= cpt
        print mean
        print cpt
        stat_name = test['results'][0]['series'][0]['name']
        
        connection_id = rstats.register_stat(conffile, 'post_processing_tcp_pep', database_name)
        if connection_id == 0:
            print "Connection to rstats failed"
            exit()
        
        rstats.send_stat(connection_id, stat_name, str(finished[i]),
                         ['mean', 'compteur'], [mean, cpt])
        #cmd = "curl -X POST 'http://" + collector + ":" + str(port) + "/write?d"
        #cmd += "b=" + database_name + "&precision=" + 'ms' + "&u=" + username
        #cmd += "&p=" + password +  "' --data-binary '" + stat_name + " mean="
        #cmd += str(mean) + ",compteur=" + str(cpt) + "i " + str(finished[i]) + "'"
        #
        #result = subprocess.check_output(cmd, shell=True)
        #print result


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='Calculation of mean interval for the simulation.',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('collector', metavar='collector', type=str, nargs=1,
                         help='IP address of the collector')
    parser.add_argument('-p', '--port', type=int, default=8086,
                        help='port of the collector')
    parser.add_argument('-b', '--begin', type=int, default=0,
                        help='timestamp of the begin to look in ms')
    parser.add_argument('-e', '--end', type=int, default=0,
                        help='timestamp of the end to look in ms')
    parser.add_argument('-s', '--simu-name', type=str, default='client',
                        help='name of the simulation')
    parser.add_argument('-d', '--database-name', type=str, default='openbach',
                        help='name of the database')
    parser.add_argument('-u', '--username', type=str, default='openbach',
                        help='name of the user')
    parser.add_argument('-pa', '--password', type=str, default='openbach',
                        help='password of the user')
    
    # get args
    args = parser.parse_args()
    collector = args.collector[0]
    port = args.port
    begin = args.begin
    end = args.end
    simu_name = args.simu_name
    database_name = args.database_name
    username = args.username
    password = args.password
    
    main(collector, port, begin, end, simu_name, database_name, username,
         password)

