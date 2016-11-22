#!/usr/bin/python
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



   @file     traffic_monitor_http2_client.py
   @brief    Sources of the Job traffic_monitor_http2_client
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from threading import Thread
from Queue import Queue, Empty
import random
import time
import argparse
from sys import exit
import signal
import syslog
from subprocess import call
import collect_agent


def signal_term_handler(signal, frame):
    Running = False
    exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)


def worker_loop(q, server_address, simu_name, page):
    try:
        while Running:
            try:
                q.get(timeout=1)
                get_url(server_address, simu_name, page)
            except Empty:
                pass
    except:
        pass


def get_url(server_address, simu_name, page):
    try:
        start_time = time.time()
        if page == 0:
            url = '/index' + str(random.randint(1,3)) + '.html'
        else:
            url = '/index' + str(page) + '.html'
        call(["nghttp","-a","-n","-W 25","-w 20","http://"+server_address+url])
        conntime = round(time.time() - start_time,3)
        timestamp = int(round(time.time() * 1000))
        collect_agent.send_log(syslog.LOG_NOTICE, "NOTICE: Delai = " + str(conntime))
        try:
            # Envoie de la stat au collecteur
            statistics = {'value': conntime}
            r = collect_agent.send_stat(timestamp, **statistics)
        except Exception as ex: 
            print "Erreur: %s" % ex

    except:
        pass

def main(server_address, simu_name, lambd, sim_t, n_req, page):
    # Connexion au service de collecte de l'agent
    conffile = "/opt/openbach-jobs.traffic_monitor_http2_client/traffic_monitor_http2_client_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        quit()

    N_workers = 150
    Running = True
    # create queue
    q = Queue()
    # start workers
    thread_pool = []
    for i in range(N_workers):
        t = Thread(target=worker_loop,args=(q, server_address, simu_name, page))
        t.start()
        thread_pool.append(t)

    # calculate arrival times
    arriv_times = []
    while not (sum(arriv_times) > sim_t or (n_req and n_req <= len(arriv_times))):
        arriv_times.append(random.expovariate(lambd))
    try:
        for wait_time in arriv_times:
            time.sleep(wait_time)
            q.put(1)
            while q.qsize()>10:
                q.get()

    Running = False
    for t in thread_pool:
        t.join()


if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('server-address', metavar='server-address', type=str,
                        help='The IP address of the server')
    parser.add_argument('-s', '--simu-name', type=str,
                        default='traffic_monitor_http2_client',
                        help='Name of the generated statistic')
    parser.add_argument('-l', '--lambd', type=float, default=1.0,
                        help='Exponential law lambda')
    parser.add_argument('--sim-t', type=float, default=60.0,
                        help='Simulation time in seconds')
    parser.add_argument('-n', '--n-req', type=int, default=0,
                        help='Number of connections')
    parser.add_argument('-p', '--page', type=int, default=1,
                        help='Page number')

    # get args
    args = parser.parse_args()
    server_address = args.server_address
    simu_name = args.simu_name
    lambd = args.lambd
    sim_t = args.sim_t
    n_req = args.n_req
    page = args.page

    main(server_address, simu_name, lambd, sim_t, n_req, page)
