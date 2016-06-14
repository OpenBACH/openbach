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
import syslog
from subprocess import call
sys.path.insert(0, "/opt/rstats/")
import rstats_api as rstats

# Configure logger
syslog.openlog("traffic_monitor_http2_client", syslog.LOG_PID, syslog.LOG_USER)


N_workers = 150

total_conn = 0
output = ''

conffile = "/home/opensand/filter.conf"

# Connexion au service de collecte de l'agent
connection_id = rstats.register_stat(conffile, 'traffic_monitor_http2_client')
if connection_id == 0:
    quit()

# server IP
if len(sys.argv)>1:
    IP = sys.argv[1]
else:
    syslog.syslog(syslog.LOG_ERROR, "ERROR: You have to provide a server address")
    exit("You have to provide a server address")

# Simulation name
if len(sys.argv)>2:
    simu_name = sys.argv[2]
else:
    # Contruction du nom de la stat
    simu_name = "traffic_monitoring_http2_client"
    
# exponential law lambda
if len(sys.argv)>3:
    lambd = float(sys.argv[3])
else:
    lambd = 1.0

# sim time 
if len(sys.argv)>4:
    sim_t = float(sys.argv[4])
else:
    sim_t = 60

# number of connections
if len(sys.argv)>5:
    n_req = int(sys.argv[5])
else:
    n_req = 0

# page number
if len(sys.argv)>6:
    page = int(sys.argv[6])
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

def exception_handler(request, exception):
    pass

def get_url():
    global total_conn
    global output
    try:
        start_time = time.time()
        #call(["nghttp","-a","-n","https://"+IP+"/index1.html"])
        if page == 0:
            url = '/index' + str(random.randint(1,3)) + '.html'
        else:
            url = '/index' + str(page) + '.html'
        call(["nghttp","-a","-n","-W 25","-w 20","http://"+IP+url])
        conntime = round(time.time() - start_time,3)
        output += str(conntime) + '\n'
        timestamp = int(round(time.time() * 1000))
        syslog.syslog(syslog.LOG_NOTICE, "NOTICE: Delai = " + str(conntime))
        try:
            # Envoie de la stat au collecteur
            r = rstats.send_stat(connection_id, simu_name, timestamp, "value",
                                 conntime)
        except Exception as ex: 
            print "Erreur: %s" % ex

        total_conn+=1
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
        #print q.qsize()
        q.put(1)
        while q.qsize()>10:
            q.get()    
        
except KeyboardInterrupt:
    Running = False
    print 'Exiting ...'

Running = False
for t in thread_pool:
    t.join()

print output[:-1]
syslog.closelog()
