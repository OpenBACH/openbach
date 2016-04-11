#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
frontend.py - <+description+>
"""

import requests, json


def add_agent(agent_ip, collector_ip, username, password, name, date):
    url = "http://localhost:8000/conductor/agents/add"

    payload = {'address': agent_ip, 'username': username, 'password':
               password, 'collector': collector_ip}
    if name != None:
        payload['name'] = name
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def add_job(job_name, path):
    url = "http://localhost:8000/conductor/jobs/add"

    payload = {'name': job_name, 'path': path}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def del_agent(agent_ip, date):
    url = "http://localhost:8000/conductor/agents/del"

    payload = {'address': agent_ip}
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def del_job(job_name):
    url = "http://localhost:8000/conductor/jobs/del"

    payload = {'name': job_name}
    
    return requests.post(url, data={'data': json.dumps(payload)})


def install_jobs(jobs_name, agents_ip, date):
    url = "http://localhost:8000/conductor/jobs/install"

    payload = {'addresses': agents_ip, 'names': jobs_name}
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def list_agents():
    url = "http://localhost:8000/conductor/agents/list"

    return requests.get(url)


def list_installed_jobs(agent_ip):
    url = "http://localhost:8000/conductor/" + agent_ip + "/jobs/list"

    return requests.get(url)


def list_instances(agent_ip):
    if agent_ip == None:
        url = ["http://localhost:8000/conductor/instances/list"]
    else:
        url = list()
        for i in agent_ip:
            url.append("http://localhost:8000/conductor/" + i +
                       "/instances/list")

    responses = []
    for i in range(len(url)):
        r = requests.get(url[i])
        responses.append(r)
    return responses


def list_jobs():
    url = "http://localhost:8000/conductor/jobs/list"

    return requests.get(url)


def restart_instance(instance_id, arguments, date, interval):
    url = "http://localhost:8000/conductor/instances/restart"

    payload = {'instance_id': instance_id}
    if arguments == None:
        payload['args'] = list()
    else:
        payload['args'] = arguments
    if interval != None:
        payload['interval'] = interval
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def start_instance(agent_ip, job_name, arguments, date, interval):
    url = "http://localhost:8000/conductor/instances/start"

    payload = {'agent_ip': agent_ip, 'job_name': job_name}
    if arguments == None:
        payload['args'] = list()
    else:
        payload['args'] = arguments
    if interval != None:
        payload['interval'] = interval
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def stop_instance(instance_id, date):
    url = "http://localhost:8000/conductor/instances/stop"

    payload = {'instance_id': instance_id}
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


def uninstall_jobs(jobs_name, agents_ip, date):
    url = "http://localhost:8000/conductor/jobs/uninstall"

    payload = {'addresses': agents_ip, 'names': jobs_name}
    if date != None:
        payload['date'] = date
    
    return requests.post(url, data={'data': json.dumps(payload)})


