#!/usr/bin/env python3

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
   
   
   
   @file     status-manager.py
   @brief    The Status Manager
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import socket
import threading
import json
import requests
from datetime import datetime
from django.utils import timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
import os
import sys
sys.path.insert(0, '/opt/openbach-controller/backend')
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()
from openbach_django.models import Job_Instance


class ScenarioManager:
    __shared_state = {}  # Borg pattern

    def __init__(self, scenario_instance_id=None, init=False):
        self.__dict__ = self.__class__.__shared_state

        if init:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            self.scenarios = {}
            self.mutex = threading.Lock()
        if scenario_instance_id is None:
            self._required_scenario = self.scenarios
        else:
            if scenario_instance_id not in self.scenarios:
                self.scenarios[scenario_instance_id] = set()
            self._required_scenario = self.scenarios[scenario_instance_id]

    def __enter__(self):
        self.mutex.acquire()
        return self._required_scenario

    def __exit__(self, t, v, tb):
        self.mutex.release()


class ClientThread(threading.Thread):
    UPDATE_INSTANCE_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}.{}{}"'

    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket

    def update_job_instance(self, job_instance_id, scenario_instance_id):
        job_instance = Job_Instance.objects.get(pk=job_instance_id)
        url = ClientThread.UPDATE_INSTANCE_URL.format(
                job_instance.job.job.name, job_instance.id,
            agent=job_instance.job.agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            return

        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value / 1000,
                        timezone.get_current_timezone())
            elif column == 'last':
                status = value
        job_instance.update_status = date
        job_instance.status = status
        job_instance.save()
        if status == 'Not Running':
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(('', 2846))
            except socket.error as serr:
                # TODO status manager injoignable, arrete le scenario ?
                print('error de connexion')
                return
            message = { 'type': 'Finished', 'scenario_instance_id':
                        scenario_instance_id, 'job_instance_id': job_instance_id
                      }
            sock.send(json.dumps(message).encode())
            sock.close()
            scheduler = ScenarioManager().scheduler
            try:
                scheduler.remove_job('watch_{}'.format(job_instance_id))
            except JobLookupError:
                pass
            with ScenarioManager(scenario_instance_id) as scenario:
                scenario.remove(job_instance_id)

    def run(self):
        request = self.clientsocket.recv(2048)
        self.clientsocket.close()
        message = json.loads(request.decode())
        type_ = message['type']
        scenario_instance_id = message['scenario_instance_id']
        scheduler = ScenarioManager().scheduler
        if type_ == 'watch':
            job_instance_id = message['job_instance_id']
            scheduler.add_job(self.update_job_instance, 'interval',
                              seconds=2, args=(job_instance_id,
                                               scenario_instance_id),
                              id='watch_{}'.format(job_instance_id))
            with ScenarioManager(scenario_instance_id) as scenario:
                scenario.add(job_instance_id)
        elif type_ == 'cancel':
            with ScenarioManager(scenario_instance_id) as scenario:
                for job_instance_id in scenario:
                    scheduler.remove_job('watch_{}'.format(job_instance_id))
                del scenario


if __name__ == '__main__':
    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 2845))
    tcp_socket.listen(10)

    # Initialisation du Scheduler
    ScenarioManager(init=True)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()

