#!/usr/bin/env python3

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Sources of the Job http2_client_plt"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import time
import signal
import syslog
import random
import argparse
from sys import exit
from subprocess import call
from functools import partial
from Queue import Queue, Empty
from threading import Thread, Event

import collect_agent


def signal_term_handler(stop_event, signal, frame):
    stop_event.set()
    exit(0)


def worker_loop(q, server_address, page, stop_event):
    try:
        while not stop_event.is_set():
            try:
                q.get(timeout=0.2)
                get_url(server_address, page)
            except Empty:
                collect_agent.send_log(
                        syslog.LOG_ERR,
                        'ERROR on workers queue')
    except Exception as ex:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR on worker do get_url: {}'.format(ex))


def get_url(server_address, page):
    if not page:
        page = random.randint(1, 3)

    try:
        start_time = time.perf_counter()
        call(['nghttp', '-a', '-n', '-W 25', '-w 20',
              'http://{}/index{}.html'.format(server_address, page)])
    except Exception:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR getting url (the server might not be running)')

    conntime = round(time.perf_counter() - start_time, 3)
    timestamp = int(time.time() * 1000)
    collect_agent.send_log(
            syslog.LOG_NOTICE,
            'The Page Load Time (sec) is = {}'.format(conntime))
    try:
        # Send stat to rstats
        collect_agent.send_stat(timestamp, value=conntime)
    except Exception as ex:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR sending stat: {}'.format(ex))


def main(server_address, mode, lambd, sim_t, n_req, page):
    # Connexion au service de collecte de l'agent
    success = collect_agent.register_collect(
            '/opt/openbach/agent/jobs/http2_client_plt/'
            'http2_client_plt_rstats_filter.conf')
    if not success:
        message = 'ERROR connecting to collect-agent'
        collect_agent.send_log(syslog.LOG_ERR, message)
        exit(message)

    stop_event = Event()
    signal.signal(signal.SIGTERM, partial(signal_term_handler, stop_event))

    # mode with inter-arrivals (following an exponential law)
    if mode == 1:
        q = Queue()
        # start workers
        arguments = (q, server_address, page, stop_event)
        thread_pool = [
                Thread(target=worker_loop, args=arguments)
                for _ in range(150)
        ]
        for thread in thread_pool:
            thread.start()

        # calculate arrival times
        arriv_times = []
        while not (sum(arriv_times) > sim_t or (n_req and n_req <= len(arriv_times))):
            arriv_times.append(random.expovariate(lambd))

        # add arrivals to queue
        try:
            for wait_time in arriv_times:
                time.sleep(wait_time)
                q.put(1)
                while q.qsize() > 10:
                    q.get()
        except Exception as ex:
            collect_agent.send_log(
                    syslog.LOG_ERR,
                    'ERROR adding arrivals to queue: {}'.format(ex))
        finally:
            stop_event.set()

        for thread in thread_pool:
            thread.join()
    # in this mode, we perform one request once the
    # previous one has already been received
    elif mode == 0:
        init_time = time.perf_counter()
        for _ in range(n_req):
            if round(time.perf_counter() - init_time) > sim_t:
                break
            get_url(server_address, page)
    else:
        collect_agent.send_log(
                syslog.LOG_ERR,
                'ERROR: mode value not known (mode must be 0 or 1)')


if __name__ == '__main__':
    # Define Usage
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('server-address', help='The IP address of the server')
    parser.add_argument(
            '-m', '--mode', type=int, default=0,
            help='Two modes of performing requests (mode=0 for '
            'normal http requests one after another, mode=1 for '
            'requests following and exponential law')
    parser.add_argument(
            '-l', '--lambd', type=float, default=1.0,
            help='Exponential law lambda')
    parser.add_argument(
            '--sim-t', type=float, default=60.0,
            help='Simulation time in seconds')
    parser.add_argument(
            '-n', '--n-req', type=int, default=0,
            help='Number of connections')
    parser.add_argument(
            '-p', '--page', type=int, default=1,
            help='Page number')

    # get args
    args = parser.parse_args()
    server_address = args.server_address
    mode = args.mode
    lambd = args.lambd
    sim_t = args.sim_t
    n_req = args.n_req
    page = args.page

    main(server_address, mode, lambd, sim_t, n_req, page)
