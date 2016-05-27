#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
frontend.py - <+description+>
"""

import requests
import datetime
import pprint
from functools import partial, wraps

try:
    import simplejson as json
except ImportError:
    import json


_URL = "http://localhost:8000/{}/{}/"


def _post_message(entry_point, verb, **kwargs):
    """Helper function to format a request and send it to
    the right URL.
    """

    url = _URL.format(entry_point, verb)

    # Why json.dumps here? Why not let requests encode the whole dict?
    return requests.post(url, data={'data': json.dumps(kwargs)})


def pretty_print(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        response = function(*args, **kwargs)
        print(response)
        pprint.pprint(response.json())
    return wrapper


def date_to_timestamp(date, fmt='%Y-%m-%d %H:%M:%S.%f'):
    timestamp = datetime.datetime.strptime(date, fmt).timestamp()
    return int(timestamp * 1000)


def add_agent(agent_ip, collector_ip, username, password, name):
    return _post_message('agents', 'add',
            address=agent_ip, username=username,
            password=password, collector=collector_ip,
            name=name)


def add_job(job_name, path):
    return _post_message('jobs', 'add', name=job_name, path=path)


def del_agent(agent_ip):
    return _post_message('agents', 'del', address=agent_ip)


def del_job(job_name):
    return _post_message('jobs', 'del', name=job_name)


def get_job_help(job_name):
    return _post_message('jobs', 'help', name=job_name)


def install_jobs(jobs_name, agents_ip):
    return _post_message('jobs', 'install',
            names=job_names, addresses=agents_ip)


def list_agents(update=None):
    return _post_message('agents', 'list', update=bool(update))


def list_installed_jobs(agent_ip, update=None):
    return _post_message('jobs', 'list',
            address=agent_ip, update=bool(update))


def list_instances(agents_ip, update=None):
    return _post_message('instances', 'list',
            addresses=agents_ip, update=bool(update))


def list_jobs():
    return requests.get(_URL.format('jobs', 'list'))


def push_file(local_path, remote_path, agent_ip):
    return _post_message('file', 'push',
            local_path=local_path, remote_path=remote_path,
            agent_ip=agent_ip)


def restart_instance(instance_id, arguments=None, date=None, interval=None):
    action = partial(_post_message, instance_id=instance_id,
            instance_args=[] if arguments is None else arguments)
    if interval is not None:
        action = partial(action, interval=interval)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)

    return action('instances', 'restart')


def start_instance(agent_ip, job_name, arguments=None, date=None,
                   interval=None):
    action = partial(_post_message, agent_ip=agent_ip, job_name=job_name,
            instance_args=[] if arguments is None else arguments)
    if interval is not None:
        action = partial(action, interval=interval)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)

    return action('instances', 'start')


def status_agents(agents_ip):
    return _post_message('agents', 'status', addresses=agents_ip)


def status_instance(instance_id, date=None, interval=None, stop=None, agent_ip=None,
                    job_name=None):
    action = partial(_post_message, instance_id=instance_id)
    if agent_ip is not None and job_name is not None:
        action = partial(action, agent_ip=agent_ip, job_name=job_name)
    if interval is not None:
        action = partial(action, interval=interval)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)
    if stop is not None:
        timestamp = date_to_timestamp('{} {}'.format(*stop))
        action = partial(action, stop=timestamp)

    return action('instances', 'status')


def status_jobs(agents_ip):
    return _post_message('jobs', 'status', addresses=agents_ip)


def stop_instance(instance_ids, date=None):
    action = partial(_post_message, instance_ids=instance_ids)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)

    return action('instances', 'stop')


def uninstall_jobs(jobs_name, agents_ip):
    return _post_message('jobs', 'uninstall',
            addresses=agents_ip, names=jobs_name)


def update_job_log_severity(agent_ip, job_name, severity, local_severity=None,
                            date=None):
    action = partial(_post_message, address=agent_ip,
            job_name=job_name, severity=severity)
    if local_severity is not None:
        action = partial(action, local_severity=local_severity)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)

    return action('jobs', 'log_severity')


def update_job_stat_policy(agent_ip, job_name, accept_stats, deny_stats,
                           default_policy=True, date=None):
    action = partial(_post_message, address=agent_ip,
            job_name=job_name, accept_stats=accept_stats,
            deny_stats=deny_stats, default_policy=default_policy)
    if date is not None:
        timestamp = date_to_timestamp('{} {}'.format(*date))
        action = partial(action, date=timestamp)

    return action('jobs', 'stat_policy')
