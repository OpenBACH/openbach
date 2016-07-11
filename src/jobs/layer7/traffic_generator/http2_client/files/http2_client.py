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


"""
Created on Thu Nov  5 15:33:30 2015

@author: jmuguerza
"""

from threading import Thread
from Queue import Queue, Empty
import random
import time
import sys
from subprocess import call


N_workers = 150

# server IP
if len(sys.argv)>1:
    IP = sys.argv[1]
else:
    exit("You have to provide a server address")

# exponential law lambda
if len(sys.argv)>2:
    lambd = float(sys.argv[2])
else:
    lambd = 1.0

# sim time 
if len(sys.argv)>3:
    sim_t = float(sys.argv[3])
else:
    sim_t = 60

# number of connections
if len(sys.argv)>4:
    n_req = int(sys.argv[4])
else:
    n_req = 0

# page number
if len(sys.argv)>5:
    page = int(sys.argv[5])
else:
    page = 1

def worker_loop(q):
    try:
        while Running:
            try:
                q.get(timeout=1)
                get_url()
            except Empty:
                pass
    except:
        pass

def get_url():
    try:
        start_time = time.time()
        if page == 0:
            url = '/index' + str(random.randint(1,3)) + '.html'
        else:
            url = '/index' + str(page) + '.html'
        call(["nghttp","-a","-n","http://"+IP+url])
    except:
        pass

Running = True
# create queue
q = Queue()
# start workers
thread_pool = []
for i in range(N_workers):
    t = Thread(target=worker_loop,args=(q,))
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
        
except KeyboardInterrupt:
    Running = False
    print 'Exiting ...'

Running = False
for t in thread_pool:
    t.join()
