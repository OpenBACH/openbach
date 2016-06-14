#!/usr/bin/python
# -*- coding: utf-8 -*-
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
