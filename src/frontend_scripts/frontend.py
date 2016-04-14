#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
frontend.py - <+description+>
"""

import requests, json
from datetime import datetime
import time
from calendar import timegm


def date_to_timestamp(date):
    t = time.localtime()
    utc_offset = timegm(t) - timegm(time.gmtime(time.mktime(t)))
    date_object = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    timestamp = (date_object - datetime(1970,1,1)).total_seconds() - utc_offset
    return timestamp


def add_agent(agent_ip, collector_ip, username, password, name=None):
    url = "http://localhost:8000/agents/add"

    payload = {'address': agent_ip, 'username': username, 'password':
               password, 'collector': collector_ip}
    if name != None:
        payload['name'] = name
    
    return requests.post(url, data={'data': json.dumps(payload)})


def add_job(job_name, path):
    url = "http://localhost:8000/jobs/add"

    payload = {'name': job_name, 'path': path}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def del_agent(agent_ip):
    url = "http://localhost:8000/agents/del"

    payload = {'address': agent_ip}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def del_job(job_name):
    url = "http://localhost:8000/jobs/del"

    payload = {'name': job_name}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def install_jobs(jobs_name, agents_ip):
    url = "http://localhost:8000/jobs/install"

    payload = {'addresses': agents_ip, 'names': jobs_name}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def list_agents(update=None):
    url = "http://localhost:8000/agents/list"

    payload = {}
    if update != None:
        payload['update'] = update

    return requests.post(url, data={'data': json.dumps(payload)})


def list_installed_jobs(agent_ip):
    url = "http://localhost:8000/" + agent_ip + "/jobs/list"

    return requests.get(url)


def list_instances(agents_ip, update=False):
    url = "http://localhost:8000/instances/list"
    
    payload = {'agents_ip': agents_ip}
    if update:
        payload['update'] = True
    
    return requests.post(url, data={'data': json.dumps(payload)})


def list_jobs():
    url = "http://localhost:8000/jobs/list"

    return requests.get(url)


def restart_instance(instance_id, arguments=None, date=None, interval=None):
    url = "http://localhost:8000/instances/restart"

    payload = {'instance_id': instance_id}
    if arguments == None:
        payload['args'] = list()
    else:
        payload['args'] = arguments
    if interval != None:
        payload['interval'] = interval
    elif date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def start_instance(agent_ip, job_name, arguments=None, date=None,
                   interval=None):
    url = "http://localhost:8000/instances/start"

    payload = {'agent_ip': agent_ip, 'job_name': job_name}
    if arguments == None:
        payload['args'] = list()
    else:
        payload['args'] = arguments
    if interval != None:
        payload['interval'] = interval
    elif date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def status_agents(agents_ip):
    url = "http://localhost:8000/agents/status"
    
    payload = {'addresses': agents_ip}
        
    return requests.post(url, data={'data': json.dumps(payload)})


def status_instance(instance_id, date=None, interval=None, stop=None, agent_ip=None,
                    job_name=None):
    url = "http://localhost:8000/instances/status"

    payload = {'instance_id': instance_id}
    if interval != None:
        payload['interval'] = interval
    elif date != None:
        payload['date'] = date
    elif stop != None:
        payload['stop'] = stop
    if agent_ip != None and job_name != None:
        payload['agent_ip'] = agent_ip
        payload['job_name'] = job_name
        
    return requests.post(url, data={'data': json.dumps(payload)})


def stop_instance(instance_id, date=None):
    url = "http://localhost:8000/instances/stop"

    payload = {'instance_id': instance_id}
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def uninstall_jobs(jobs_name, agents_ip):
    url = "http://localhost:8000/jobs/uninstall"

    payload = {'addresses': agents_ip, 'names': jobs_name}
    
    return requests.post(url, data={'data': json.dumps(payload)})


