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



   @file     http_client_plt.py
   @brief    Sources of the Job http_client_plt
   @author   David PRADAS <david.pradas@toulouse.viveris.com>
"""


from threading import Thread
from Queue import Queue, Empty
import random
import time
import requests
import grequests
from lxml import html
import argparse
import urlparse
from sys import exit
import signal

import syslog
from subprocess import call
import collect_agent


def worker_loop(q, server_address, page):
    global Running
    try:
        while Running:
            try:
                q.get(timeout=1)
                get_url(server_address, port, page)
            except Empty:
                collect_agent.send_log(syslog.LOG_DEBUG, "No more workers on queue")
    except Exception as ex:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR on worker do get_url: %s" + ex)


def get_url(server_address, port, page):
    try:
        start_time = time.time()
        if page == 0:
            url = '/index' + str(random.randint(1,3)) + '.html'
        else:
            url = '/index' + str(page) + '.html'
        response = requests.get("http://" + server_address + ":" +  str(port) + url)
        parsed_body = html.fromstring(response.text)
        
        # Grab links to all images
        images = parsed_body.xpath('//img/@src')
        scripts = parsed_body.xpath('//script/@src')
        css = parsed_body.xpath("//link[@rel='stylesheet']/@href")
        icons = parsed_body.xpath("//link[@rel='shortcut icon']/@href")
        
        # Convert any relative urls to absolute urls
        images = [urlparse.urljoin(response.url, url) for url in images]
        scripts = [urlparse.urljoin(response.url, url) for url in scripts]
        css = [urlparse.urljoin(response.url, url) for url in css]
        icons = [urlparse.urljoin(response.url, url) for url in icons]
        
        rs = (grequests.get(u) for u in images+scripts+css+icons if u.startswith("http://" + server_address))
        grequests.map(rs)

        conntime = round(time.time() - start_time,3)
        collect_agent.send_log(syslog.LOG_NOTICE, "The Page Load Time is= " + str(conntime))
        timestamp = int(round(time.time() * 1000))
        try:
            # Send the stat to the Collector
            statistics = {'load_time': conntime}
            r = collect_agent.send_stat(timestamp, **statistics)
        except Exception as ex: 
            collect_agent.send_log(syslog.LOG_ERR, "ERROR sending stat: %s" + ex)

    except Exception as ex:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR getting url (the server might not be running)")

def main(server_address, port, mode, lambd, sim_t, n_req, page):
    # Connect to the collect-agent service
    conffile = "/opt/openbach-jobs/http_client_plt/http_client_plt_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to collect-agent")
        quit()
    
    #mode with inter-arrivals (following an exponential law) 
    if mode == 1:
        global Running
        Running = True
    
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
    
        #add arrivals to queue
        try:
            for wait_time in arriv_times:
                time.sleep(wait_time)
                q.put(1)
                while q.qsize()>10:
                    q.get()
        except Exception as ex:
            Running = False
            collect_agent.send_log(syslog.LOG_ERR, "ERROR adding arrivals to queue: " + str(ex))
            
        
        Running = False
        for t in thread_pool:
            t.join()
    
    #in this mode, we perform one request once the previous one has already been received
    elif mode == 0:
        init_time = time.time()
        n=0
        while (round(time.time() - init_time,3) < sim_t) or (n_req > n):
            get_url(server_address, port, page)
            n += 1
            
    else:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR: mode value not known (mode must be 0 or 1")
            
            
if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('server_address', metavar='server_address', type=str, help='The IP address of the web server')
    parser.add_argument('port', metavar='port', type=int, help='The port of the web server')
    
    parser.add_argument('-m', '--mode', type=int, default=0, help='Two modes of performing requests (mode=0 for normal'
                        'http requests one after another, mode=1 for requests following and exponential law')
    parser.add_argument('-l', '--lambd', type=float, default=1.0, help='Inter-arrivals: Exponential law lambda')
    parser.add_argument('--sim-t', type=float, default=60.0, help='Simulation time in seconds')
    parser.add_argument('-n', '--n-req', type=int, default=0, help='Number of connections')
    parser.add_argument('-p', '--page', type=int, default=1, help='Page number')

    # get args
    args = parser.parse_args()
    server_address = args.server_address
    port = args.port
    mode = args.mode    
    lambd = args.lambd
    sim_t = args.sim_t
    n_req = args.n_req
    page = args.page

    main(server_address, port, mode, lambd, sim_t, n_req, page)
