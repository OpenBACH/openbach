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



   @file     openbach-agent.py
   @brief    The Control-Agent (with the scheduling part)
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import os
import time
import socket
import threading
import syslog
import signal
import shutil
import subprocess
import yaml
from functools import partial
from datetime import datetime

import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import datetime_repr

import sys
sys.path.insert(0, '/opt/rstats/')
import rstats_api as rstats



PID_FOLDER = '/var/run/openbach'
RSTAT_REGISTER_STAT = partial(
        rstats.register_stat,
        '/opt/openbach-agent/openbach-agent_filter.conf',
        'openbach-agent')

class ArgsManager:
    """Context manager around args of Job Instance """
    __shared_state = {}  # Borg pattern

    def __init__(self, job_name=None, job_instance_id=None, init=False):
        self.__dict__ = self.__class__.__shared_state

        if init:
            self.args = {}
            self.mutex = threading.Lock()
        if job_name is None:
            self._required_args = self.args
        else:
            try:
                required_args = self.args[job_name]
            except KeyError:
                self.args[job_name] = {}
                required_args = self.args[job_name]
            if job_instance_id is None:
                self._required_args = required_args
            else:
                try:
                    self._required_args = required_args[job_instance_id]
                except KeyError:
                    required_args[job_instance_id] = {}
                    self._required_args = required_args[job_instance_id]

    def __enter__(self):
        self.mutex.acquire()
        return self._required_args

    def __exit__(self, t, v, tb):
        self.mutex.release()

class JobManager:
    """Context manager around job scheduling"""
    __shared_state = {}  # Borg pattern

    def __init__(self, job=None, init=False):
        self.__dict__ = self.__class__.__shared_state

        if init:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            self.jobs = {}
            self.mutex = threading.Lock()
        self._required_job = self.jobs if job is None else self.jobs[job]

    def __enter__(self):
        self.mutex.acquire()
        return self._required_job

    def __exit__(self, t, v, tb):
        self.mutex.release()


def list_jobs_in_dir(dirname):
    for filename in os.listdir(dirname):
        name, ext = os.path.splitext(filename)
        if ext == '.yml':
            yield name


def signal_term_handler(signal, frame):
    scheduler = JobManager().scheduler
    scheduler.remove_all_jobs()
    with JobManager() as all_jobs:
        for name, job in all_jobs.items():
            command_stop = job['command_stop']
            for job_instance_id in job['set_id']:
                with ArgsManager(name, job_instance_id) as args:
                    arguments = args['args']
                    del args
                    scheduler.add_job(stop_job, 'date', args=(name, job_instance_id,
                                                              command_stop,
                                                              arguments),
                                     id='{}{}_stop'.format(job_name, job_instance_id))

    while scheduler.get_jobs():
        time.sleep(0.5)
    scheduler.shutdown()
    for root, _, filenames in os.walk(PID_FOLDER):
        for filename in filenames:
            os.remove(os.path.join(root, filename))
    exit(0)


def launch_job(job_name, job_instance_id, command, args):
    proc = subprocess.Popen(
            'PID=`{} {} > /dev/null 2>&1 & echo $!`; echo'
            ' $PID > {}/{}{}.pid'.format(command, args, PID_FOLDER, job_name,
                                         job_instance_id),
            shell=True)


def stop_job(job_name, job_instance_id, command, args):
    try:
        JobManager().scheduler.remove_job(job_name + job_instance_id)
    except JobLookupError:
        pid_filename = '{}/{}{}.pid'.format(PID_FOLDER, job_name, job_instance_id)
        try:
            with open(pid_filename) as f:
                pid = int(f.read())
        except FileNotFoundError:
            return

        p = subprocess.Popen('pkill -TERM -P {0}; kill -TERM {0}'.format(pid), shell=True)
        p.wait()
        os.remove(pid_filename)

        if command:
            subprocess.Popen('{} {}'.format(command, args), shell=True)

    with JobManager(job_name) as job:
        if job_instance_id in job['set_id']:
            with JobManager(job_name) as job:
                job['set_id'].remove(job_instance_id)



def status_job(job_name, job_instance_id):
    # Construction du nom de la stat
    stat_name = job_name + job_instance_id
    timestamp = round(time.time() * 1000)

    # Récupération du status
    job = JobManager().scheduler.get_job(stat_name)
    if job is None:
        pid_filename = '{}/{}{}.pid'.format(PID_FOLDER, job_name, job_instance_id)
        try:
            with open(pid_filename) as f:
                pid = int(f.read())
        except (IOError, ValueError):
            status = '"Not Running"'
        else:
            if os.path.exists('/proc/{}'.format(pid)):
                status = 'Running'
            else:
                status = '"Not Running"'
                os.remove(pid_filename)
    else:
        if isinstance(job.trigger, DateTrigger):
            status = '"Programmed on {}"'.format(datetime_repr(job.trigger.run_date))
        elif isinstance(job.trigger, IntervalTrigger):
            status = '"Programmed every {}"'.format(job.trigger.interval_length)

    # Connexion au service de collecte de l'agent
    connection = RSTAT_REGISTER_STAT()
    if not connection:
        return

    # Envoie de la stat à Rstats
    rstats.send_stat(connection, stat_name, timestamp, 'status', status)


def stop_watch(job_id):
    try:
        JobManager().scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def schedule_job_instance(job_name, job_instance_id, arguments, date_value,
                          reschedule=False):
    timestamp = time.time()
    with JobManager(job_name) as job:
        command = job['command']
        command_stop = job['command_stop']
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    if not reschedule or date != None:
        try:
            JobManager().scheduler.add_job(
                    launch_job, 'date', run_date=date,
                    args=(job_name, job_instance_id, command, arguments),
                    id=job_name+job_instance_id)
        except ConflictingIdError:
            raise BadRequest('KO A job {} is already programmed'.format(job_name))

        with JobManager(job_name) as job:
            # TODO: Voir si il faudrait pas l'ajouter aussi pour les jobs non
            # persistents
            if job['persistent']:
                job['set_id'].add(job_instance_id)
    return date


def schedule_job_instance_stop(job_name, job_instance_id, date_value,
                               reschedule=False):
    timestamp = time.time()
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    with JobManager(job_name) as job:
        command_stop = job['command_stop']
    if command_stop:
        with ArgsManager(job_name, job_instance_id) as args:
            arguments = args['args']
            del args
    else:
        arguments = ''
    if not reschedule or date != None:
        try:
            JobManager().scheduler.add_job(stop_job, 'date', run_date=date,
                                           args=(job_name, job_instance_id,
                                                 command_stop, arguments),
                              id='{}{}_stop'.format(job_name, job_instance_id))
        except ConflictingIdError:
            JobManager().scheduler.reschedule_job('{}{}_stop'.format(job_name, job_instance_id),
                                                  trigger='date', run_date=date)
    return date


def schedule_watch(job_name, job_instance, date_type, date_value):
    timestamp = time.time()
    date = True
    if date_type == 'date':
        date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
        try:
            JobManager().scheduler.add_job(
                    status_job, 'date', run_date=date,
                    args=(job_name, job_instance_id),
                    id='{}{}_status'.format(job_name, job_instance_id))
        except ConflictingIdError:
            raise BadRequest('KO A watch on instance {} with '
                    'id {} is already programmed'
                    .format(job_name, job_instance_id))
    # Programmer de regarder le status régulièrement
    elif date_type == 'interval':
        try:
            JobManager().scheduler.add_job(
                    status_job, 'interval', seconds=date_value,
                    args=(job_name, job_instance_id),
                    id='{}{}_status'.format(job_name, job_instance_id))
        except ConflictingIdError:
            raise BadRequest('KO A watch on instance {} with '
                    'id {} is already programmed'
                    .format(job_name, job_instance_id))
    # Déprogrammer
    elif date_type == 'stop':
        date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
        status_job_id = '{}{}_status'.format(job_name, job_instance_id)

        # TODO get_job doesn't raise JobLookupError when the job
        # isn't found. We have to found a function that does it
        # [Mathias] maybe like that:
        if JobManager().scheduler.get_job(status_job_id) is None:
            raise BadRequest('KO No watch on the status '
                    'of the instance {} '
                    'with the id {} was programmed'
                    .format(job_name, job_instance_id))
        JobManager().scheduler.add_job(
                stop_watch, 'date', args=(status_job_id,),
                run_date=date, id='stop_watch_{}'.format(status_job_id))
    return date


def ls_jobs():
    timestamp = int(round(time.time() * 1000))

    # Récupération des jobs disponibles
    with JobManager() as jobs:
        count = len(jobs)
        # TODO send_stat(..., **kwargs)
        # job_names = {'nb': count}
        # job_names.update({'job{}'.format(i): job for i, job in enumerate(jobs, 1)})
        values = [count] + list(jobs)
        header = ['job{}'.format(i) for i in range(count)]
        header.insert(0, 'nb')

    # Construction du nom de la stat
    stat_name = "jobs_list"

    # Connexion au service de collecte de l'agent
    connection = RSTAT_REGISTER_STAT()
    if not connection:
        quit()  # [Mathias] same than status_job

    # Envoie de la stat à Rstats
    rstats.send_stat(connection, 'jobs_list', timestamp, header, values)
    # TODO send_stat(..., **kwargs)
    # rstats.send_stat(connection, 'jobs_list', timestamp, **job_names)


class BadRequest(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class JobConfiguration:
    def __init__(self, conf_path, job_name):
        filename = '{}.yml'.format(job_name)
        conf_file = os.path.join(conf_path, filename)

        try:
            with open(conf_file, 'r') as stream:
                try:
                    content = yaml.load(stream)
                except yaml.YAMLError:
                    raise BadRequest(
                            'KO Conf file {} not well formed'.format(filename))
        except FileNotFoundError:
            raise BadRequest(
                    'KO Conf file {} does not exist'.format(filename))

        try:
            self.command = content['os']['linux']['command']
            self.command_stop = content['os']['linux']['command_stop']
            self.required = []
            for arg in content['arguments']['default']:
                self.required.append(arg['name'])
            self.optional = True if type(content['arguments']['optionnal']) == list else False
            self.persistent = content['general']['persistent']
        except KeyError:
            raise BadRequest(
                    'KO Conf file {} does not contain a '
                    'section for job {}'.format(filename, job_name))


    @staticmethod
    def parse(job, option, name, boolean=False):
        if boolean:
            try:
                value = job.getboolean(option)
            except ValueError:
                raise BadRequest(
                        'KO Conf "{}" for job {} should be '
                        'a boolean'.format(option, name))
            else:
                # [Mathias] You can replace the next 3 lines with
                # `return bool(value)` if it's OK to _not_ have
                # 'persistent' or 'optional' in the conf file
                # It will be considered False when value is missing
                if value is None:
                    raise BadRequest(
                            'KO Conf file for job {} doesn\'t '
                            'contain the "{}" option'.format(name, option))
                return value
        else:
            try:
                return job[option]
            except KeyError:
                raise BadRequest(
                        'KO Conf file for job {} doesn\'t '
                        'contain the "{}" option'.format(name, option))


class ClientThread(threading.Thread):
    REQUIREMENTS = {
            'status_jobs_agent': (0, ''),
            'add_job_agent': (1, 'You should provide the job name'),
            'del_job_agent': (1, 'You should provide the job name'),
            'status_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value'),
            'start_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value. '
                'Optional arguments may follow'),
            'restart_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value. '
                'Optional arguments may follow'),
            'stop_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value'),
    }

    def __init__(self, client_socket, path_jobs, path_scheduled_instances_job):
        super().__init__()
        self.socket = client_socket
        self.path_jobs = path_jobs
        self.path_scheduled_instances_job = path_scheduled_instances_job

    def start_job_instance(self, name, job_instance_id, date_type, date_value, args):
        with JobManager(name) as job:
            command = job['command']
            command_stop = job['command_stop']

        arguments = ' '.join(args)
        if date_type == 'date':
            date = schedule_job_instance(name, job_instance_id, arguments, date_value)
            if date != None:
                filename = '{}{}{}.start'.format(self.path_scheduled_instances_job,
                                                 name, job_instance_id)
                with open(filename, 'w') as job_instance_prog:
                    print('{}\n{}\n{}\n{}'.format(name, job_instance_id,
                                                  date_value, arguments),
                          file=job_instance_prog)

        elif date_type == 'interval':
            date = ''
            with JobManager(name) as job:
                if job['persistent']:
                    raise BadRequest(
                            'KO This job {} is persistent, you can\'t '
                            'start it with the "interval" option'
                            .format(name))
            if command_stop:
                with ArgsManager(name) as dict_args:
                    for (id, job_args) in dict_args.items():
                        if job_args['type'] == 'interval':
                            # Pour ce genre de job (non persistent avec une
                            # command_stop), un seul interval est autorisé
                            # Pour l'instant on renvoie un message d'erreur quand on
                            # en demande un 2eme mais on pourrait très bien
                            # remplacer l'un par l'autre à la place
                            raise BadRequest('KO A job {} is already '
                                             'programmed. It instance_id is {}.'
                                             ' Please stop it before trying to '
                                             'programme regulary this job '
                                             'again'.format(job_name, id))
            try:
                JobManager().scheduler.add_job(
                        launch_job, 'interval', seconds=date_value,
                        args=(name, job_instance_id, command, arguments),
                        id=name+job_instance_id)
            except ConflictingIdError:
                raise BadRequest(
                        'KO An instance {} with the id {} '
                        'is already programmed'.format(name, job_instance_id))

            with JobManager(name) as job:
                job['set_id'].add(job_instance_id)
        with ArgsManager(name) as args:
            args[job_instance_id] = {
                    'args': arguments,
                    'type': date_type,
                    'date': date,
            }

    def parse(self, request):
        try:
            # Récupération du type de la requete et du nom du job
            request, *args = request.split()
        except ValueError:
            raise BadRequest('KO Message not formed well. It '
                    'should have at least an action')

        try:
            required_args, error_msg = self.REQUIREMENTS[request]
        except KeyError:
            raise BadRequest(
                    'KO Action not recognize. Actions possibles are : {}'
                    .format(' '.join(self.REQUIREMENTS.keys())))

        provided_args = len(args)
        if provided_args < required_args:
            raise BadRequest('KO Message not formed well. {}.'.format(error_msg))

        if provided_args > required_args and request not in ('start_job_instance_agent', 'restart_job_instance_agent'):
            raise BadRequest('KO Message not formed well. Too much arguments.')

        if request == 'add_job_agent':
            job_name = args[0]
            # On vérifie si le job est déjà installé
            with JobManager() as jobs:
                if job_name in jobs:
                    raise BadRequest(
                            'OK A job {} is already installed'
                            .format(job_name))
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            conf = JobConfiguration(self.path_jobs, job_name)
            args.append(conf.command)
            if conf.command_stop:
                args.append(conf.command_stop)
            else:
                args.append('')
            args.append(conf.required)
            args.append(conf.optional)
            args.append(conf.persistent)

        elif request == 'del_job_agent':
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                            'OK No job {} is installed'.format(job_name))

        elif request == 'status_job_instance_agent':
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                            'KO No job {} is installed'.format(job_name))

            # On récupère la date ou l'interval
            if args[2] in ('date', 'stop'):
                try:
                    # [Mathias] warning, will put floats in here use // instead of / if integers are required
                    args[3] = 0 if args[3] == 'now' else int(args[3]) / 1000
                except ValueError:
                    raise BadRequest(
                            'KO The {} to watch the status should '
                            'be given as a timestamp in milliseconds'
                            .format(args[2]))
            elif args[2] == 'interval':
                try:
                    args[3] = int(args[3])
                except ValueError:
                    raise BadRequest(
                            'KO The interval to execute the job '
                            'should be given in seconds')
            else:
                # TODO Gérer le 'cron' ?
                raise BadRequest(
                        'KO Only "date", "interval" and "stop" '
                        'are allowed with the status action')

        elif request in ('start_job_instance_agent', 'restart_job_instance_agent'):
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest('KO No job {} is installed'.format(job_name))

            job_instance_id = args[1]
            # On vérifie si il n'est pas déjà demarré
            # (seulement dans le cas 'start')
            if request == 'start':
                with JobManager(job_name) as job:
                    if job_instance_id in job['set_id']:
                        raise BadRequest(
                                'KO Instance {} with id {} is '
                                'already started'.format(job_name, job_instance_id))

            # On récupère la date ou l'interval
            if args[2] == 'date':
                try:
                    # [Mathias] warning, will put floats in here use // instead of / if integers are required
                    args[3] = 0 if args[3] == 'now' else int(args[3]) / 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to begin should be '
                            'given as a timestamp in milliseconds')
            elif args[2] == 'interval':
                try:
                    args[3] = int(args[3])
                except ValueError:
                    raise BadRequest(
                            'KO The interval to execute the '
                            'job should be given in seconds')
            else:
                # TODO Gérer le 'cron' ?
                raise BadRequest(
                        'KO Only "date" and "interval" are allowed '
                        'to be specified when executing the job')
            # On vérifie si il au moins autant d'arguments
            # qu'exigé pour lancer la commande
            with JobManager(job_name) as job:
                nb_args = len(job['required'])
                optional = job['optional']

            if len(args) < required_args + nb_args:
                raise BadRequest(
                        'KO Job {} requires at least {} arguments'
                        .format(job_name, nb_args))

            # On vérifié qu'il n'y ait pas trop d'arguments
            if not optional and len(args) > required_args + nb_args:
                raise BadRequest(
                        'KO Job {} does not require more than {} arguments'
                        .format(job_name, nb_args))

        elif request == 'stop_job_instance_agent':
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest('KO No job {} installed'.format(job_name))

            # On récupère la date
            if args[2] == 'date':
                try:
                    # [Mathias] warning, will put floats in here use // instead of / if integers are required
                    args[3] = 0 if args[3] == 'now' else int(args[3]) / 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to stop should be '
                            'given as a timestamp in milliseconds')
            else:
                raise BadRequest(
                        'KO To stop a job, only a date can be specified')

        return request, args

    def execute_request(self, request):
        request, extra_args = self.parse(request)
        scheduler = JobManager().scheduler

        if request == 'status_jobs_agent':
            scheduler.add_job(ls_jobs, 'date', id='ls_jobs')

        if request == 'add_job_agent':
            job_name, command, command_stop, required, optional, persistent = extra_args
            # TODO Vérifier que l'appli a bien été installé ?
            with JobManager() as jobs:
                jobs[job_name] = {
                        'command': command,
                        'command_stop': command_stop,
                        'required': required,
                        'optional': optional,
                        'persistent': persistent,
                        'set_id': set(),
                }

        elif request == 'del_job_agent':
            job_name, = extra_args
            # On vérifie si le job n'est pas en train de tourner
            with JobManager(job_name) as job:
                command_stop = job['command_stop']
                for job_instance_id in job['set_id']:
                    if command_stop:
                        with ArgsManager(job_name, job_instance_id) as args:
                            arguments = args['args']
                            del args
                    else:
                        arguments = ''
                    scheduler.add_job(stop_job, 'date', args=(job_name,
                                                              job_instance_id,
                                                              command_stop,
                                                              arguments),
                                      id='{}{}_stop'.format(job_name, job_instance_id))

            # TODO Vérifier que l'appli a bien été désinstallé ?
            with JobManager() as jobs:
                del jobs[job_name]

        elif request == 'start_job_instance_agent':
            job, job_instance_id, date, value, *args = extra_args
            self.start_job_instance(job, job_instance_id, date, value, args)

        elif request == 'stop_job_instance_agent':
            job_name, job_instance_id, _, value = extra_args
            date = schedule_job_instance_stop(job_name, job_instance_id, value)
            if date != None:
                filename = '{}{}{}.stop'.format(self.path_scheduled_instances_job,
                                                job_name, job_instance_id)
                with open(filename, 'w') as job_instance_stop:
                    print('{}\n{}\n{}'.format(job_name, job_instance_id, value),
                          file=job_instance_stop)

        elif request == 'status_job_instance_agent':
            job_name, job_instance_id, date_type, date_value = extra_args
            # Récupérer le status actuel
            date = schedule_watch(job_name, job_instance_id, date_type,
                                  date_value)
            if date_type == 'stop':
                filename = '{}{}{}.status_stop'.format(self.path_scheduled_instances_job,
                                                       job_name, job_instance_id)
            else:
                filename = '{}{}{}.status'.format(self.path_scheduled_instances_job,
                                                  job_name, job_instance_id)
            with open(filename, 'w') as job_instance_status:
                print('{}\n{}\n{}\n{}'.format(job_name, job_instance_id,
                                              date_type, date_value),
                      file=job_instance_status)

        elif request == 'restart_job_instance_agent':
            job_name, job_instance_id, date, value, *args = extra_args
            # Stoppe le job si il est lancé
            with JobManager(job_name) as job:
                if job_instance_id in job['set_id']:
                    command_stop = job['command_stop']
                    with ArgsManager(job_name, job_instance_id) as args:
                        arguments = args['args']
                        del args
                    scheduler.add_job(
                            stop_job, 'date', args=(job_name, job_instance_id,
                                                    command_stop, arguments),
                            id='{}{}_stop'.format(job_name, job_instance_id))

            try:
                scheduler.remove_job(job_name + job_instance_id)
            except JobLookupError:
                pass

            with JobManager(job_name) as job:
                job['set_id'].remove(job_instance_id)

            # Le relancer avec les nouveaux arguments (éventuellement les mêmes)
            self.start_job_instance(job_name, job_instance_id, date, value, args)

    def run(self):
        request = self.socket.recv(2048)
        try:
            self.execute_request(request.decode())
        except BadRequest as e:
            syslog.syslog(syslog.LOG_ERR, e.reason)
            self.socket.send(e.reason.encode())
        except Exception as e:
            msg = 'Error on request: {} {}'.format(e.__class__.__name__, e)
            syslog.syslog(syslog.LOG_ERR, msg)
            self.socket.send('KO {}'.format(msg).encode())
        else:
            self.socket.send(b'OK')
        finally:
            self.socket.close()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_term_handler)

    # TODO Syslog bug : seulement le 1er log est envoyé, les autres sont ignoré
    # Configure logger
    syslog.openlog('openbach-agent', syslog.LOG_PID, syslog.LOG_USER)

    # On ajoute tous les jobs déjà présent
    path_jobs = '/opt/openbach-agent/jobs/'
    with JobManager(init=True) as jobs:
        for job in list_jobs_in_dir(path_jobs):
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            try:
                conf = JobConfiguration(path_jobs, job)
            except BadRequest as e:
                syslog.syslog(syslog.LOG_ERR, e.reason)
                continue

            # On ajoute le job a la liste des jobs disponibles
            jobs[job] = {
                    'command': conf.command,
                    'command_stop': conf.command_stop,
                    'required': conf.required,
                    'optional': conf.optional,
                    'set_id': set(),
                    'persistent': conf.persistent,
            }

    # On initialise l'ArgsManager
    ArgsManager(init=True)

    # On programme les instances de job deja programmee
    path_scheduled_instances_job = '/opt/openbach-agent/job_instances/'
    for root, _, filenames in os.walk(path_scheduled_instances_job):
        for filename in sorted(filenames):
            with open(root + filename, 'r') as f:
                if filename.endswith('.start'):
                    try:
                        job_name = f.readline().rstrip('\n')
                        job_instance_id = f.readline().rstrip('\n')
                        date_value = float(f.readline().rstrip('\n'))
                        arguments = f.readline().rstrip('\n')
                    except ValueError:
                        print('Error with the reading of {}{}'.format(root,
                                                                      filename))
                        continue
                    date = schedule_job_instance(job_name, job_instance_id, arguments,
                                        date_value, reschedule=True)
                    with ArgsManager(job_name) as args:
                        args[job_instance_id] = {
                                'args': arguments,
                                'type': 'date',
                                'date': date,
                        }
                elif filename.endswith('.stop'):
                    try:
                        job_name = f.readline().rstrip('\n')
                        job_instance_id = f.readline().rstrip('\n')
                        date_value = float(f.readline().rstrip('\n'))
                    except ValueError:
                        print('Error with the reading of {}{}'.format(root,
                                                                      filename))
                        continue
                    date = schedule_job_instance_stop(job_name, job_instance_id,
                                                      date_value, reschedule=True)
                elif filename.endswith('.status'):
                    try:
                        job_name = f.readline().rstrip('\n')
                        job_instance_id = f.readline().rstrip('\n')
                        date_type = f.readline().rstrip('\n')
                        date_value = float(f.readline().rstrip('\n'))
                    except ValueError:
                        print('Error with the reading of {}{}'.format(root,
                                                                      filename))
                        continue
                    date = schedule_watch(job_name, job_instance_id, date_type,
                                          date_value)
                elif filename.endswith('.status_stop'):
                    try:
                        job_name = f.readline().rstrip('\n')
                        job_instance_id = f.readline().rstrip('\n')
                        date_type = f.readline().rstrip('\n')
                        date_value = float(f.readline().rstrip('\n'))
                    except ValueError:
                        print('Error with the reading of {}{}'.format(root,
                                                                      filename))
                        continue
                    date = schedule_watch(job_name, job_instance_id, date_type,
                                          date_value)
                    if date == None:
                        os.remove(os.path.join(root, filename[:len(filename)-5]))
                else:
                    date = None
            if date == None:
                os.remove(os.path.join(root, filename))


    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('',1112))
    tcp_socket.listen(1000)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket, path_jobs, path_scheduled_instances_job).start()

