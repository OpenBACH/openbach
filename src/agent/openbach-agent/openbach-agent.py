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
import signal
import yaml
import shlex
from subprocess import DEVNULL
from functools import partial
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
#from apscheduler.util import datetime_repr
import psutil
import collect_agent

try:
    # Try importing unix stuff
    import syslog
    import resource
    resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))
    OS_TYPE = 'linux'
    PID_FOLDER = '/var/run/openbach'
    JOBS_FOLDER = '/opt/openbach-agent/jobs/'
    INSTANCES_FOLDER = '/opt/openbach-agent/job_instances/'
    COLLECT_AGENT_REGISTER_COLLECT = partial(
        collect_agent.register_collect,
        '/opt/openbach-agent/openbach-agent_filter.conf')
except ImportError:
    # If we failed assure we’re on windows
    import syslog_viveris as syslog
    OS_TYPE = 'windows'
    PID_FOLDER = r'C:\openbach\pid'
    JOBS_FOLDER = r'C:\openbach\jobs'
    INSTANCES_FOLDER = r'C:\openbach\instances'
    COLLECT_AGENT_REGISTER_COLLECT = partial(
        collect_agent.register_collect,
        r'C:\openbach\openbach-agent_filter.conf')


# Configure logger
syslog.openlog('openbach-agent', syslog.LOG_PID, syslog.LOG_USER)


def signal_term_handler(signal, frame):
    """ Function that handle the kill of the Openbach Agent """
    scheduler = JobManager().scheduler
    scheduler.remove_all_jobs()
    with JobManager() as all_jobs:
        for name, job in all_jobs.items():
            command_stop = job['command_stop']
            for job_instance_id, parameters in job['instances'].items():
                arguments = parameters['args']
                scheduler.add_job(stop_job, 'date',
                        args=(name, job_instance_id, command_stop, arguments),
                        id='{}{}_stop'.format(name, job_instance_id))
    while scheduler.get_jobs():
        time.sleep(0.5)
    scheduler.shutdown()
    for root, _, filenames in os.walk(PID_FOLDER):
        for filename in filenames:
            os.remove(os.path.join(root, filename))
    exit(0)


signal.signal(signal.SIGTERM, signal_term_handler)


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
            #self.rstats_connection = COLLECT_AGENT_REGISTER_COLLECT()  # [Mathias] Maybe open only one connection to rstats like this
        self._required_job = self.jobs if job is None else self.jobs[job]

    def __enter__(self):
        self.mutex.acquire()
        return self._required_job

    def __exit__(self, t, v, tb):
        self.mutex.release()


def popen(command, args, **kwargs):
    return psutil.Popen(
            shlex.split(command) + shlex.split(args),
            stdout=DEVNULL, stderr=DEVNULL, **kwargs)


def pid_filename(job_name, job_instance_id):
    """ Function that contructs the filename of the pid file """
    # Return the pid filename
    filename = '{}{}.pid'.format(job_name, job_instance_id)
    return os.path.join(PID_FOLDER, filename)


def list_jobs_in_dir(dirname):
    """ Function that lists all the Jobs in the directory """
    for filename in os.listdir(dirname):
        name, ext = os.path.splitext(filename)
        if ext == '.yml':
            yield name


def launch_job(job_name, job_instance_id, scenario_instance_id,
               owner_scenario_instance_id, command, args):
    """ Function that launches the Job Instance """
    # Add some environement variable for the Job Instance
    environ = os.environ.copy()
    environ.update({'JOB_NAME': job_name, 'JOB_INSTANCE_ID': job_instance_id,
                    'SCENARIO_INSTANCE_ID': scenario_instance_id,
                    'OWNER_SCENARIO_INSTANCE_ID': owner_scenario_instance_id})
    # Launch the Job Instance
    proc = popen(command, args, env=environ)
    # Write the pid in the pid file
    with open(pid_filename(job_name, job_instance_id), 'w') as pid_file:
        print(proc.pid, file=pid_file)


def stop_job(job_name, job_instance_id, command=None, args=None):
    """ Function that stops the Job Instance """
    try:
        # Cancel the Job Instance
        JobManager().scheduler.remove_job(job_name + job_instance_id)
    except JobLookupError:
        # Get the pid filename
        filename = pid_filename(job_name, job_instance_id)
        # Get the pid
        try:
            with open(filename) as f:
                pid = int(f.read())
        except FileNotFoundError:
            return
        # Get the process
        proc = psutil.Process(pid)
        # Kill all its childs
        for child in proc.children(recursive=True):
            child.terminate()
        # Kill the process
        proc.terminate()
        proc.wait()
        # Delate the pid file
        os.remove(filename)
        # Launch the command stop if there is one
        if command:
            popen(command, args).wait()
    # Remove the Job Instance to the JobManager
    try:
        with JobManager(job_name) as job:
            del job['instances'][job_instance_id]
    except KeyError:
        pass


def status_job(job_name, job_instance_id):
    """ Function that send the status of the Job Instance to the Collector """
    timestamp = round(time.time() * 1000)
    # Get the status of the Job Instance
    job = JobManager().scheduler.get_job(job_name + job_instance_id)
    if job is None:
        filename = pid_filename(job_name, job_instance_id)
        try:
            with open(filename) as f:
                pid = int(f.read())
        except (IOError, ValueError):
            status = 'Not Running'
        else:
            if psutil.pid_exists(pid):
                status = 'Running'
            else:
                status = 'Not Running'
                os.remove(filename)
    else:
        if isinstance(job.trigger, DateTrigger):
            status = 'Scheduled' #'Programmed on {}'.format(datetime_repr(job.trigger.run_date))
        elif isinstance(job.trigger, IntervalTrigger):
            status = 'Running' #'Programmed every {}'.format(job.trigger.interval_length)
    # Connection to the collect agent
    os.environ['JOB_NAME'] = 'openbach-agent'
    success = COLLECT_AGENT_REGISTER_COLLECT()
    if not success:
        syslog.syslog(syslog.LOG_ERR, 'Unable the connect to rstats')
        return
    # Send the stat
    statistics = {'job_name': job_name, 'job_instance_id': job_instance_id,
                  'status': status}
    collect_agent.send_stat(timestamp, **statistics)


def stop_watch(job_id):
    """ Function that stops the watch of the Job Instance """
    try:
        JobManager().scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def schedule_job_instance(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, arguments, date_value,
                          reschedule=False):
    """ Function that schedules a Job Instance """
    # Get the current time
    timestamp = time.time()
    # Get the date
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    try:
        # Get the command and command_stop
        with JobManager(job_name) as job:
            command = job['command']
            command_stop = job['command_stop']
    except KeyError:
        return date, False
    if not reschedule or date != None:
        # Schedule the Job Instance
        try:
            JobManager().scheduler.add_job(
                    launch_job, 'date', run_date=date,
                    args=(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, command, arguments),
                    id=job_name+job_instance_id)
        except ConflictingIdError:
            raise BadRequest('KO A job {} is already programmed'.format(job_name))
        # Register the arguments in the JobManager
        with JobManager(job_name) as job:
            # TODO: See if we should add it too for the non persistents jobs
            if job['persistent']:
                job['instances'][job_instance_id] = {'args': arguments, 'type':
                                                     'date', 'date': date}
    return date, True


def schedule_job_instance_stop(job_name, job_instance_id, date_value,
                               reschedule=False):
    """ Function that schedules the stop of the Job Instance """
    # Get the current time
    timestamp = time.time()
    # Get the date
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    with JobManager(job_name) as job:
        try:
            # Get the command and command_stop
            command_stop = job['command_stop']
            arguments = job['instances'][job_instance_id]['args']
        except KeyError:
            raise BadRequest('OK job {} with id {} is already '
                             'stopped'.format(job_name, job_instance_id))
        else:
            # Remove the Job Instance to the JobManager
            del job['instances'][job_instance_id]
    if not reschedule or date != None:
        # Schedule the stop of the Job Instance
        try:
            JobManager().scheduler.add_job(stop_job, 'date', run_date=date,
                                           args=(job_name, job_instance_id,
                                                 command_stop, arguments),
                              id='{}{}_stop'.format(job_name, job_instance_id))
        except ConflictingIdError:
            JobManager().scheduler.reschedule_job('{}{}_stop'.format(
                job_name, job_instance_id), trigger='date', run_date=date)
    return date


def schedule_watch(job_name, job_instance_id, date_type, date_value):
    """ Function that schedules the Watch on the Job Instance """
    # Get the current time
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
    # Schedule to watch the status regularly
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
    # Cancel
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
    """ Function that sends to the Collector the lists of the Installed Jobs on
    the Agent """
    timestamp = round(time.time() * 1000)
    # Get the Installed Jobs
    with JobManager() as jobs:
        count = len(jobs)
        job_names = {'job{}'.format(i): job for i, job in enumerate(jobs, 1)}
    # Connection to collect agent
    os.environ['JOB_NAME'] = 'openbach-agent'
    success = COLLECT_AGENT_REGISTER_COLLECT()
    if not success:
        syslog.syslog(syslog.LOG_ERR, 'Unable the connect to rstats')
        return
    # Send the stat
    statistics = {'_type': 'job_list', 'nb': count, **job_names}
    collect_agent.send_stat(timestamp, **statistics)


class BadRequest(ValueError):
    """Custom exception raised when parsing of a request failed"""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class JobConfiguration:
    """ Class that represents the configuration of a Job """
    def __init__(self, conf_path, job_name):
        # Get the configuration filename
        filename = '{}.yml'.format(job_name)
        conf_file = os.path.join(conf_path, filename)
        # Load the configuration in content
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
        # Register the configuration
        try:
            self.command = content['os'][OS_TYPE]['command']
            self.command_stop = content['os'][OS_TYPE]['command_stop']
            self.required = []
            args = content['arguments']['required']
            if type(args) == list:
                for arg in args:
                    count = arg['count']
                    if count == '+':
                        self.required.append(arg['name'])
                    else:
                        if not isinstance(count, int):
                            counts = count.split('-')
                            count = int(counts[0])
                        for i in range(count):
                            self.required.append(arg['name'])
            self.optional = True if type(content['arguments']['optional']) == list else False
            self.persistent = content['general']['persistent']
        except KeyError:
            raise BadRequest(
                    'KO Conf file {} does not contain a '
                    'section for job {}'.format(filename, job_name))


class ClientThread(threading.Thread):
    """ Class that represents the main thread of the program """
    REQUIREMENTS = {
            'status_jobs_agent': (0, ''),
            'add_job_agent': (1, 'You should provide the job name'),
            'del_job_agent': (1, 'You should provide the job name'),
            'status_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a watch type and its value'),
            'start_job_instance_agent':
                (6, 'You should provide a job name, an '
                'owner_scenario_instance_id, a scenario_instance_id, a '
                'job_instance_id, the type of start (date or interval) and its value. '
                'Optional arguments may follow (arguments of the Job)'),
            'restart_job_instance_agent':
                (6, 'You should provide a job name, an '
                'owner_scenario_instance_id, a scenario_instance_id, a '
                'job_instance_id, the type of start (date or interval) and its value. '
                'Optional arguments may follow (arguments of the Job)'),
            'stop_job_instance_agent':
                (4, 'You should provide a job name, an '
                'instance id, a stop type (date) and its value'),
    }

    def __init__(self, client_socket, path_jobs, path_scheduled_instances_job):
        super().__init__()
        self.socket = client_socket
        self.path_jobs = path_jobs
        self.path_scheduled_instances_job = path_scheduled_instances_job

    def start_job_instance(self, name, job_instance_id, scenario_instance_id,
                           owner_scenario_instance_id, date_type, date_value,
                           args):
        """ Function that starts a Job Instance """
        # Get the command and command_stop
        with JobManager(name) as job:
            command = job['command']
            command_stop = job['command_stop']
        # Build the arguments
        arguments = ' '.join(args)
        if date_type == 'date':
            # Schedule the Job Instance
            date, _ = schedule_job_instance(
                name, job_instance_id, scenario_instance_id,
                owner_scenario_instance_id, arguments, date_value)
            # If date has not occur yet, register the schedule in a file in case
            # the openbach-agent restarts
            if date is not None:
                filename = '{}{}{}.start'.format(
                    self.path_scheduled_instances_job, name, job_instance_id)
                with open(filename, 'w') as job_instance_prog:
                    print(name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, date_value, arguments,
                          sep='\n', file=job_instance_prog)
        elif date_type == 'interval':
            date = None
            # Performe some check
            with JobManager(name) as job:
                if job['persistent']:
                    raise BadRequest(
                            'KO This job {} is persistent, you can\'t '
                            'start it with the "interval" option'
                            .format(name))
                for inst_id, job_args in job['instances'].items():
                    if job_args['type'] == 'interval':
                        # [Mathias] Maybe check that instance_id != inst_id ?
                        raise BadRequest('KO A job {} is already '
                                         'programmed. It instance_id is {}.'
                                         ' Please stop it before trying to '
                                         'programme regulary this job '
                                         'again'.format(job_name, inst_id))
            # Schedule the Job Instance
            try:
                JobManager().scheduler.add_job(
                        launch_job, 'interval', seconds=date_value,
                        args=(name, job_instance_id, scenario_instance_id,
                              owner_scenario_instance_id, command, arguments),
                        id=name+job_instance_id)
            except ConflictingIdError:
                raise BadRequest(
                        'KO An instance {} with the id {} '
                        'is already programmed'.format(name, job_instance_id))
        # Register the Job Instance in the JobManager
        with JobManager(name) as job:
            job['instances'][job_instance_id] = {
                'args': arguments,
                'type': date_type,
                'date': date,
            }

    def parse(self, request):
        """ Function that checks if the request is known and well formed and
        parse the arguments """
        try:
            # Get the type of the request and the name of the job
            request, *args = request.split()
        except ValueError:
            raise BadRequest('KO Message not formed well. It '
                    'should have at least an action')
        # Get the requirements
        try:
            required_args, error_msg = self.REQUIREMENTS[request]
        except KeyError:
            raise BadRequest(
                    'KO Action not recognize. Actions possibles are : {}'
                    .format(' '.join(self.REQUIREMENTS.keys())))
        # Check is the requirements are fulfiled
        provided_args = len(args)
        if provided_args < required_args:
            raise BadRequest('KO Message not formed well. {}.'.format(error_msg))
        if provided_args > required_args and request not in ('start_job_instance_agent', 'restart_job_instance_agent'):
            raise BadRequest('KO Message not formed well. Too much arguments.')
        # Parse the arguments
        if request == 'add_job_agent':
            job_name = args[0]
            # Check if this Job is already installed
            with JobManager() as jobs:
                if job_name in jobs:
                    raise BadRequest(
                            'OK A job {} is already installed'
                            .format(job_name))
            # Check if the conf file is well formed
            conf = JobConfiguration(self.path_jobs, job_name)
            args.append(conf.command)
            args.append(conf.command_stop)
            args.append(conf.required)
            args.append(conf.optional)
            args.append(conf.persistent)
        elif request == 'del_job_agent':
            job_name = args[0]
            # Check that the Job is installed
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                            'OK No job {} is installed'.format(job_name))
        elif request == 'status_job_instance_agent':
            job_name = args[0]
            # Check that the Job is installed
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                            'KO No job {} is installed'.format(job_name))
            # Get the date or the interval
            if args[2] in ('date', 'stop'):
                try:
                    args[3] = 0 if args[3] == 'now' else int(args[3]) // 1000
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
                raise BadRequest(
                        'KO Only "date", "interval" and "stop" '
                        'are allowed with the status action')
        elif request in ('start_job_instance_agent', 'restart_job_instance_agent'):
            job_name = args[0]
            # Check that the Job is installed
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest(
                        'KO No job {} is installed'.format(job_name))
            job_instance_id = args[1]
            # Check if the job instance is not already started (only for the
            # 'start')
            if request == 'start':
                with JobManager(job_name) as job:
                    if job_instance_id in job['instances']:
                        raise BadRequest(
                                'KO Instance {} with id {} is '
                                'already started'.format(job_name,
                                                         job_instance_id))
            # Get the date or the interval
            if args[4] == 'date':
                try:
                    args[5] = 0 if args[5] == 'now' else int(args[5]) // 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to begin should be '
                            'given as a timestamp in milliseconds')
            elif args[4] == 'interval':
                try:
                    args[5] = int(args[5])
                except ValueError:
                    raise BadRequest(
                            'KO The interval to execute the '
                            'job should be given in seconds')
            else:
                raise BadRequest(
                        'KO Only "date" and "interval" are allowed '
                        'to be specified when executing the job')
            # Check that there is enough arguments
            with JobManager(job_name) as job:
                nb_args = len(job['required'])
                optional = job['optional']
            if len(args) < required_args + nb_args:
                raise BadRequest(
                        'KO Job {} requires at least {} arguments'
                        .format(job_name, nb_args))
            # Check that there is not to much arguments
            if not optional and len(args) > required_args + nb_args:
                raise BadRequest(
                        'KO Job {} does not require more than {} arguments'
                        .format(job_name, nb_args))
        elif request == 'stop_job_instance_agent':
            job_name = args[0]
            # Check that the Job is installed
            with JobManager() as jobs:
                if job_name not in jobs:
                    raise BadRequest('KO No job {} installed'.format(job_name))
            # Get the date
            if args[2] == 'date':
                try:
                    args[3] = 0 if args[3] == 'now' else int(args[3]) // 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to stop should be '
                            'given as a timestamp in milliseconds')
            else:
                raise BadRequest(
                        'KO To stop a job, only a date can be specified')
        return request, args

    def execute_request(self, request):
        """ Function that execute the request """
        request, extra_args = self.parse(request)
        getattr(self, request)(*extra_args)

    def status_jobs_agent(self):
        """ Function that sends the lists of the Installed Jobs to the Collector
        """
        JobManager().scheduler.add_job(ls_jobs, 'date', id='ls_jobs')

    def add_job_agent(self, job_name, command, command_stop, required, optional,
                      persistent):
        """ Function that adds this Job to the list of Jobs """
        with JobManager() as jobs:
            jobs[job_name] = {
                    'command': command,
                    'command_stop': command_stop,
                    'required': required,
                    'optional': optional,
                    'persistent': persistent,
                    'instances': {},
            }

    def del_job_agent(self, job_name):
        """ Function that deletes this Job from the Jobs list"""
        # Check if an instance of this Job is running
        with JobManager(job_name) as job:
            command_stop = job['command_stop']
            for job_instance_id, parameters in job['instances'].items():
                if command_stop:
                    arguments = parameters['args']
                else:
                    arguments = ''
                JobManager().scheduler.add_job(
                    stop_job, 'date', args=(job_name, job_instance_id,
                                            command_stop, arguments),
                    id='{}{}_stop'.format(job_name, job_instance_id))
        # Delete the Job from the JobManager
        with JobManager() as jobs:
            del jobs[job_name]

    def start_job_instance_agent(self, job, job_instance_id,
                                 scenario_instance_id,
                                 owner_scenario_instance_id, date, value,
                                 *args):
        """ Function that starts a Job Instance """
        self.start_job_instance(job, job_instance_id, scenario_instance_id,
                                owner_scenario_instance_id, date, value, args)

    def stop_job_instance_agent(self, job_name, job_instance_id, _, value):
        """ Function that stops a Job Instance """
        # Schedule the stop of the Job Instance
        date = schedule_job_instance_stop(job_name, job_instance_id, value)
        # If date has not occur yet, register the schedule in a file in case
        # the openbach-agent restarts
        if date is not None:
            filename = '{}{}{}.stop'.format(self.path_scheduled_instances_job,
                                            job_name, job_instance_id)
            with open(filename, 'w') as job_instance_stop:
                print(job_name, job_instance_id, value, sep='\n',
                      file=job_instance_stop)

    def status_job_instance_agent(self, job_name, job_instance_id, date_type,
                                  date_value):
        """ Function that schedule a watch on the Job Instance """
        # Schedule the watch of the Job Instance
        date = schedule_watch(job_name, job_instance_id, date_type, date_value)
        # Register the schedule in a file in case the openbach-agent restarts
        filename = '{}{}{}.status'.format(
            self.path_scheduled_instances_job, job_name, job_instance_id)
        if date_type == 'stop':
            filename += '_stop'
        with open(filename, 'w') as job_instance_status:
            print(job_name, job_instance_id, date_type, date_value, sep='\n',
                  file=job_instance_status)

    def restart_job_instance_agent(self, job_name, job_instance_id,
                                   scenario_instance_id,
                                   owner_scenario_instance_id, date, value,
                                   *args):
        """ Function that restarts a Job Instance """
        # Stop the Job Instance if it is running
        with JobManager(job_name) as job:
            try:
                job_params = job['instances'][job_instance_id]
            except KeyError:
                pass
            else:
                command_stop = job['command_stop']
                arguments = job_params['args']
                stop_job(job_name, job_instance_id, command_stop, arguments)
        # Start the Job Instance with the new arguments
        self.start_job_instance(job_name, job_instance_id, scenario_instance_id,
                                owner_scenario_instance_id, date, value, args)

    def run(self):
        """ Main function """
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
    # Add all the Job already installed
    with JobManager(init=True) as jobs:
        for job in list_jobs_in_dir(JOBS_FOLDER):
            # Check the format of the conf file
            try:
                conf = JobConfiguration(JOBS_FOLDER, job)
            except BadRequest as e:
                syslog.syslog(syslog.LOG_ERR, e.reason)
            else:
                # add the Job to the Jobs list
                jobs[job] = {
                        'command': conf.command,
                        'command_stop': conf.command_stop,
                        'required': conf.required,
                        'optional': conf.optional,
                        'instances': {},
                        'persistent': conf.persistent,
                }
    # Schedule the Job Instance to schedule
    for root, _, filenames in os.walk(INSTANCES_FOLDER):
        for filename in sorted(filenames):
            fullpath = os.path.join(root, filename)
            with open(fullpath) as f:
                basename, ext = os.path.splitext(filename)
                if ext == 'start':
                    try:
                        job_name, job_instance_id, scenario_instance_id, owner_scenario_instance_id, date_value, arguments = f.readlines()
                        date_value = float(date_value)
                    except ValueError:
                        syslog.syslog(
                            syslog.LOG_ERR,
                            'Error with the reading of {}'.format(fullpath))
                        continue
                    date, result = schedule_job_instance(
                            job_name, job_instance_id, scenario_instance_id,
                            owner_scenario_instance_id, arguments, date_value,
                            reschedule=True)
                    if result:
                        with JobManager(job_name) as job:
                            job['instances'][job_instance_id] = {
                                    'args': arguments,
                                    'type': 'date',
                                    'date': date,
                            }
                elif ext == 'stop':
                    try:
                        job_name, job_instance_id, date_value = f.readlines()
                        date_value = float(date_value)
                    except ValueError:
                        syslog.syslog(
                            syslog.LOG_ERR,
                            'Error with the reading of {}'.format(fullpath))
                        continue
                    date = schedule_job_instance_stop(
                            job_name, job_instance_id,
                            date_value, reschedule=True)
                elif ext == 'status':
                    try:
                        job_name, job_instance_id, date_type, date_value = f.readlines()
                        date_value = float(date_value)
                    except ValueError:
                        syslog.syslog(
                            syslog.LOG_ERR,
                            'Error with the reading of {}'.format(fullpath))
                        continue
                    date = schedule_watch(job_name, job_instance_id, date_type,
                                          date_value)
                elif ext == 'status_stop':
                    try:
                        job_name, job_instance_id, date_type, date_value = f.readlines()
                        date_value = float(date_value)
                    except ValueError:
                        syslog.syslog(
                            syslog.LOG_ERR,
                            'Error with the reading of {}'.format(fullpath))
                        continue
                    date = schedule_watch(job_name, job_instance_id, date_type,
                                          date_value)
                    if date is None:
                        os.remove(os.path.join(root, basename+'.status'))
                else:
                    date = None
            if date is None:
                os.remove(fullpath)

    # Open the listening socket
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 1112))
    tcp_socket.listen(1000)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket, JOBS_FOLDER, INSTANCES_FOLDER).start()
