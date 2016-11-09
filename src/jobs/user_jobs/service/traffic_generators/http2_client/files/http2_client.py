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
   
   
   
   @file     http2_client.py
   @brief    Sources of the Job http2_client
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


from threading import Thread
from Queue import Queue, Empty
import random
import time
import argparse
import signal
import sys
from subprocess import call


def signal_term_handler(signal, frame):
    global Running
    Running = False
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)

Running = True

def worker_loop(q, server_address, page):
    global Running
    try:
        while Running:
            try:
                q.get(timeout=1)
                get_url(server_address, page)
            except Empty:
                pass
    except:
        pass


def get_url(server_address, page):
    try:
        start_time = time.time()
        if page == 0:
            url = '/index' + str(random.randint(1,3)) + '.html'
        else:
            url = '/index' + str(page) + '.html'
        call(["nghttp","-a","-n","http://"+server_address+url])
    except:
        pass


def main(server_address, lambd, sim_t, n_req, page):
    global Running
    N_workers = 150
    Running = True
    # create queue
    q = Queue()
    # start workers
    thread_pool = []
    for i in range(N_workers):
        t = Thread(target=worker_loop,args=(q, server_address, page))
        t.start()
        thread_pool.append(t)

    # calculate arrival times
    arriv_times = []
    while not (sum(arriv_times) > sim_t or (n_req and n_req <= len(arriv_times))):
        arriv_times.append(random.expovariate(lambd))
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
    parser.add_argument('server_address', metavar='server_address', type=str,
                        help='The IP address of the server')
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
    lambd = args.lambd
    sim_t = args.sim_t
    n_req = args.n_req
    page = args.page

    main(server_address, lambd, sim_t, n_req, page)

