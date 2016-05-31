#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
openbach-agent.py - <+description+>
"""

import os
import time
import socket
import threading
import syslog
import signal
import shutil
import subprocess
from configparser import ConfigParser
from functools import partial
from datetime import datetime

import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import datetime_repr

import sys.path
sys.path.insert(0, '/opt/rstats/')
import rstats_api as rstats


PID_FOLDER = '/var/run/openbach'
RSTAT_REGISTER_STAT = partial(
        rstat.register_stat,
        '/opt/openbach-agent/openbach-agent_filter.conf',
        'openbach-agent')


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
        if ext == '.cfg':
            yield name


def signal_term_handler(signal, frame):
    scheduler = JobManager().scheduler
    scheduler.remove_all_jobs()
    with JobManager() as all_jobs:
        for name, job in all_jobs.items():
            for instance in job['set_id']:
                scheduler.add_job(stop_job, 'date', args=(name, instance))

    while scheduler.get_jobs():
        time.sleep(0.5)
    scheduler.shutdown()
    shutil.rmtree(PID_FOLDER, ignore_errors=True)
    exit(0)


def launch_job(job_name, instance_id, command, args):
    proc = subprocess.Popen(
            [command, args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    with open('{}/{}{}.pid'.format(PID_FOLDER, job_name, instance_id), 'w') as f:
        print(proc.pid, file=f)

    
def stop_job(job_name, instance_id):
    pid_filename = '{}/{}{}.pid'.format(PID_FOLDER, job_name, instance_id)
    with open(pid_filename) as f:
        pid = int(f.read())

    subprocess.run('pkill -TERM -P {0}; kill -TERM {0}'.format(pid), shell=True)
    os.remove(pid_filename)

    
def status_job(job_name, instance_id):
    # Construction du nom de la stat
    stat_name = job_name + instance_id
    timestamp = round(time.time() * 1000)

    # Récupération du status
    job = JobManager().scheduler.get_job(stat_name)
    if job is None:
        pid_filename = '{}/{}{}.pid'.format(PID_FOLDER, job_name, instance_id)
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
        quit()  # [Mathias] quit()?? not return??

    # Envoie de la stat à Rstats
    rstats.send_stat(connection, stat_name, timestamp, 'status', status)
    

def stop_watch(job_id)
    try:
        JobManager().scheduler.remove_job(job_id)
    except JobLookupError:
        pass

 
def ls_jobs():
    timestamp = int(round(time.time() * 1000))
    
    # Récupération des jobs disponibles
    with JobManager() as jobs:
        count = len(jobs)
        values = [count] + list(jobs)
        header = ['job{}'.format(i) for i in range(count)]
        header[0] = 'nb'
    
    # Construction du nom de la stat
    stat_name = "jobs_list"
    
    # Connexion au service de collecte de l'agent
    connection = RSTAT_REGISTER_STAT()
    if not connection:
        quit()  # [Mathias] same than status_job
        
    # Envoie de la stat à Rstats
    rstats.send_stat(connection, 'jobs_list', timestamp, header, values)
        

class BadRequest(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason
    
    
class JobConfiguration:
    def __init__(self, conf_path, job_name):
        filename = '{}.cfg'.format(job_name)
        conf_file = os.path.join(conf_path, filename)

        config = ConfigParser()
        config.read(conf_file)

        try:
            job = config[job_name]
        except KeyError:
            raise BadRequest(
                    'KO Conf file {} does not contain a '
                    'section for job {}'.format(filename, job_name))

        self.command = self.parse(job, 'command', job_name)
        self.required = self.parse(job, 'required', job_name).split()
        self.optional = self.parse(job, 'optional', job_name, True)
        self.persistent = self.parse(job, 'persistent', job_name, True)

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
            'ls_job': (0, ''),
            'add': (1, 'You should provide the job name'),
            'del': (1, 'You should provide the job name'),
            'status':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value'),
            'start':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value. '
                'Optional arguments may follow'),
            'restart':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value. '
                'Optional arguments may follow'),
            'stop':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value'),
    }

    def __init__(self, client_socket, path):
        super().__init__()
        self.socket = client_socket
        self.path = path
        
    def start_job(self, name, instance, date_type, date_value, args):
        with JobManager(name) as job:
            command = job['command']

        arguments = ' '.join(args)
        timestamp = time.time()
        if date_type == 'date':
            date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
            try:
                JobManager().scheduler.add_job(
                        launch_job, 'date', run_date=date,
                        args=(name, instance, command, arguments), id=name+instance)
            except ConflictingIdError:
                raise BadRequest('KO A job {} is already programmed'.format(name))

            with JobManager(name) as job:
                if job['persistent']:
                    job['set_id'].add(instance)

        elif date_type == 'interval':
            with JobManager(name) as job:
                if job['persistent']:
                    raise BadRequest(
                            'KO This job {} is persistent, you can\'t '
                            'start it with the "interval" option'
                            .format(name))

            try:
                JobManager().scheduler.add_job(
                        launch_job, 'interval', seconds=date_value,
                        args=(name, instance, command, arguments), id=name+instance)
            except ConflictingIdError:
                raise BadRequest(
                        'KO An instance {} with the id {} '
                        'is already programmed'.format(name, instance))

            with JobManager(name) as job:
                job['set_id'].add(instance)

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

        if provided_args > required_args and request not in ('start', 'restart'):
            raise BadRequest('KO Message not formed well. Too much arguments.')

        if request == 'add':
            job_name = args[0]
            # On vérifie si le job est déjà installé
            with JobManager() as jobs:
                if job_name in jobs:
                    raise BadRequest(
                            'OK A job {} is already installed'
                            .format(job_name))
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            conf = JobConfiguration(self.path, job_name)
            args.append(conf.command)
            args.append(conf.required)
            args.append(conf.optional)
            args.append(conf.persistent)

        elif request == 'del':
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                            'OK No job {} is installed'.format(job_name))

        elif request == 'status':
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

        elif request in ('start', 'restart'):
            job_name = args[0]
            # On vérifie que le job soit bien installé
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest('KO No job {} is installed'.format(job_name))

            instance = args[1]
            # On vérifie si il n'est pas déjà demarré
            # (seulement dans le cas 'start')
            if request == 'start':
                with JobManager(job_name) as job:
                    if instance in job['set_id']:
                        raise BadRequest(
                                'KO Instance {} with id {} is '
                                'already started'.format(job_name, instance)) 

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

        elif request == 'stop':
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
        request, *extra_args = self.parse(request)
        scheduler = JobManager().scheduler

        if request == 'ls_jobs':
            scheduler.add_job(ls_jobs, 'date')

        if request == 'add':
            job_name, command, required, optional, persistent = extra_args
            # TODO Vérifier que l'appli a bien été installé ?
            with JobManager() as jobs:
                jobs[job_name] = {
                        'command': command,
                        'required': required,
                        'optional': optional,
                        'persistent': persistent,
                        'set_id': set(),
                }

        elif request == 'del':
            job_name, = extra_args
            # On vérifie si le job n'est pas en train de tourner
            with JobManager(job_name) as job:
                for instance in job['set_id']:
                    scheduler.add_job(stop_job, 'date', args=(job_name, instance))

            # TODO Vérifier que l'appli a bien été désinstallé ?
            with JobManager() as jobs:
                del jobs[job_name]

        elif request == 'start':
            job, instance, date, value, *args = extra_args
            self.start_job(job, instance, date, value, args)

        elif request == 'stop':
            job_name, instance, _, value = extra_args
            timestamp = time.time()
            date = None if value < timestamp else datetime.fromtimestamp(value)
            scheduler.add_job(stop_job, 'date', run_date=date, args=(job_name, instance))
            try:
                scheduler.remove_job(job_name + instance_id)
            except JobLookupError:
                # On vérifie si il n'est pas déjà stoppé
                with JobManager(job_name) as job:
                    if instance not in job['set_id']:
                        raise BadRequest('OK job {} with id {} is already stopped'.format(job_name, instance))

            with JobManager(job_name) as job:
                job['set_id'].remove(instance)

        elif request == 'status':
            job_name, instance, date_type, date_value = extra_args
            timestamp = time.time()

            # Récupérer le status actuel
            if date_type == 'date':
                date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
                try:
                    scheduler.add_job(
                            status_job, 'date', run_date=date,
                            args=(job_name, instance),
                            id='{}{}_status'.format(job_name, instance))
                except ConflictingIdError:
                    raise BadRequest('KO A watch on instance {} with '
                            'id {} is already programmed'
                            .format(job_name, instance))
            # Programmer de regarder le status régulièrement
            elif date_type == 'interval':
                try:
                    scheduler.add_job(
                            status_job, 'interval', seconds=date_value,
                            args=(job_name, instance_id),
                            id='{}{}_status'.format(job_name, instance))
                except ConflictingIdError:
                    raise BadRequest('KO A watch on instance {} with '
                            'id {} is already programmed'
                            .format(job_name, instance_id))
            # Déprogrammer
            elif date_type == 'stop':
                date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
                status_job = '{}{}_status'.format(job_name, instance)

                # TODO get_job doesn't raise JobLookupError when the job
                # isn't found. We have to found a function that does it
                # [Mathias] maybe like that:
                if scheduler.get_job(status_job) is None:
                    raise BadRequest('KO No watch on the status '
                            'of the instance {} '
                            'with the id {} was programmed'
                            .format(job_name, instance))
                scheduler.add_job(
                        stop_watch, 'date', args=(status_job,), run_date=date)

        elif request == 'restart':
            job_name, instance, date, value, *args = extra_args
            # Stoppe le job si il est lancé
            with JobManager(job_name) as job:
                if instance in job['set_id']:
                    scheduler.add_job(
                            stop_job, 'date', args=(job_name, instance))

            try:
                scheduler.remove_job(job_name + instance_id)
            except JobLookupError:
                pass

            with JobManager(job_name) as job:
                job['set_id'].remove(instance)

            # Le relancer avec les nouveaux arguments (éventuellement les mêmes)
            self.start_job(job_name, instance, date, value, args)

    def run(self):
        request = self.socket.recv(2048)
        try:
            self.execute_request(request.decode())
        except BadRequest as e:
            syslog.syslog(syslog.LOG_ERR, e.reason)
            self.socket.send(e.reason.encode())
        except Exception:
            syslog.syslog(syslog.LOG_ERR, 'Can\'t decode request')
            self.socket.send(b'KO Can\'t decode request')
        else:
            self.socket.send('OK')
        finally:
            self.socket.close()


if __name__ == '__main__':
    signal.signal(signal.SIGHUP, signal_term_handler)

    # TODO Syslog bug : seulement le 1er log est envoyé, les autres sont ignoré
    # Configure logger
    syslog.openlog('openbach-agent', syslog.LOG_PID, syslog.LOG_USER)

    # On ajoute tous les jobs déjà présent
    path = '/opt/openbach-agent/jobs/'
    with JobManager(init=True) as jobs:
        for job in list_jobs_in_dir(path):
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            try:
                conf = JobConfiguration(path, job)
            except BadRequest as e:
                syslog.syslog(syslog.LOG_ERR, e.reason)
                continue

            # On ajoute le job a la liste des jobs disponibles
            jobs[job] = {
                    'command': conf.command,
                    'required': conf.required,
                    'optional': conf.optional,
                    'set_id': set(),
                    'persistent': conf.persistent,
            }

    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('',1112))
    tcp_socket.listen(1000)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket, path).start()

