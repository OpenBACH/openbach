#!/usr/bin/env python3
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
   
   
   
   @file     http_server.py
   @brief    Sources of the Job http_server
   @author   David PRADAS <david.pradas@toulouse.viveris.com>
"""


#from http.server import BaseHTTPRequestHandler, HTTPServer
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn, TCPServer  
from concurrent.futures import ThreadPoolExecutor

import subprocess
import argparse
import os
import syslog
import collect_agent



class RandomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        os.chdir("/opt/openbach-jobs/http_server")
        try:
            return SimpleHTTPRequestHandler.do_GET(self)
        except IOError as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR receiving HTTP request from client: %s" + ex)

class PoolMixIn(ThreadingMixIn):
    def process_request(self, request, client_address):
        self.pool.submit(self.process_request_thread, request, client_address)

class ThreadedHTTPServer(ThreadingMixIn,HTTPServer):
    """ Threaded HTTP Server """

class ThreadedTCPServer(ThreadingMixIn,TCPServer):
    """ Threaded TCP Server """

class PoolHTTPServer(ThreadingMixIn,TCPServer):
    pool = ThreadPoolExecutor(max_workers = 200)


def main(port):
    # Connect to the agent collect service
    conffile = "/opt/openbach-jobs/http_server/http_server_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to collect-agent")
        quit()
    Handler = RandomHTTPRequestHandler
    ThreadedTCPServer.allow_reuse_address = True
    #httpd = ThreadedTCPServer(("", PORT), Handler)
    PoolHTTPServer.allow_reuse_address = True
    httpd = PoolHTTPServer(("", port), Handler)
    httpd.serve_forever()



if __name__ == "__main__":
    global chain
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('port', metavar='port', type=int,
                        help='Port where the server id available')

    # get args
    args = parser.parse_args()
    port = args.port

    main(port)

