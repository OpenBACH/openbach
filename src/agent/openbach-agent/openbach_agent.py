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
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""The Control-Agent (with the scheduling part)"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import time
import shlex
import struct
import signal
import threading
import socketserver
from datetime import datetime
from functools import partial
from subprocess import DEVNULL
from contextlib import suppress

import yaml
import psutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

import collect_agent

try:
    # Try importing unix stuff
    import syslog
    import resource
    resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))
    OS_TYPE = 'linux'
    PID_FOLDER = '/var/run/openbach'
    JOBS_FOLDER = '/opt/openbach/agent/jobs/'
    INSTANCES_FOLDER = '/opt/openbach/agent/job_instances/'
    COLLECT_AGENT_REGISTER_COLLECT = partial(
        collect_agent.register_collect,
        '/opt/openbach/agent/openbach_agent_filter.conf')
except ImportError:
    # If we failed assure we’re on windows
    import syslog_viveris as syslog
    OS_TYPE = 'windows'
    PID_FOLDER = r'C:\openbach\pids'
    JOBS_FOLDER = r'C:\openbach\jobs'
    INSTANCES_FOLDER = r'C:\openbach\instances'
    COLLECT_AGENT_REGISTER_COLLECT = partial(
        collect_agent.register_collect,
        r'C:\openbach\openbach_agent_filter.conf')


# Configure logger
syslog.openlog('openbach_agent', syslog.LOG_PID, syslog.LOG_USER)


def signal_term_handler(signal, frame):
    """ Function that handle the kill of the Openbach Agent """
    manager = JobManager()
    manager.scheduler.remove_all_jobs()
    RestartAgent().action()
    while manager.scheduler.get_jobs():
        time.sleep(0.5)
    manager.scheduler.shutdown()
    for root, _, filenames in os.walk(PID_FOLDER):
        for filename in filenames:
            os.remove(os.path.join(root, filename))
    exit(0)


class JobManager:
    """Context manager around job scheduling"""
    __shared_state = {
            'scheduler': None,
            'jobs': {},
            '_mutex': threading.Lock(),
    }

    def __init__(self):
        self.__dict__ = self.__class__.__shared_state
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()

    @property
    def job_names(self):
        with self._mutex:
            return list(self.jobs)

    def has_instance(self, name, instance_id):
        with self._mutex:
            try:
                job = self.jobs[name]
            except KeyError:
                return False
            else:
                return instance_id in job['instances']

    def add_job(self, name):
        with self._mutex:
            if name in self.jobs:
                raise BadRequest('OK A job {} is already installed'.format(name))
            conf = JobConfiguration(name)
            self.jobs[name] = {
                    'command': conf.command,
                    'command_stop': conf.command_stop,
                    'required': conf.required,
                    'optional': conf.optional,
                    'persistent': conf.persistent,
                    'instances': {},
            }

    def pop_job(self, name):
        with self._mutex:
            try:
                return self.jobs.pop(name)
            except KeyError:
                raise BadRequest('OK No job {} is installed'.format(name))

    def get_job(self, name):
        with self._mutex:
            try:
                job = self.jobs[name]
            except KeyError:
                raise BadRequest('KO No job {} is installed'.format(name))
            return {key: job[key] for key in (
                    'command',
                    'command_stop',
                    'required',
                    'optional',
                    'persistent')}

    def get_instances(self, name):
        with self._mutex:
            try:
                job = self.jobs[name]
            except KeyError:
                raise BadRequest('KO No job {} is installed'.format(name))
            yield from job['instances'].items()

    def add_instance(self, name, instance_id, arguments, date_type, date_value):
        with self._mutex:
            self.jobs[name]['instances'][instance_id] = {
                    'args': arguments,
                    'type': date_type,
                    'date': date_value,
            }

    def pop_instance(self, name, instance_id):
        with self._mutex:
            return self.jobs[name]['instances'].pop(instance_id)


class NoSuchJobException(Exception):
    pass


class TruncatedMessageException(Exception):
    def __init__(self, expected_length, length):
        message = (
                'Message trunctated before '
                'reading the whole content. '
                'Expected {} bytes but read {}'
                .format(expected_length, length)
        )
        super().__init__(message)


def popen(command, args, **kwargs):
    return psutil.Popen(
            shlex.split(command) + shlex.split(args),
            stdout=DEVNULL, stderr=DEVNULL, **kwargs)


def pid_filename(job_name, job_instance_id):
    """Contruct the filename of a file that should contain the
    PID for the given job.
    """
    filename = '{}{}.pid'.format(job_name, job_instance_id)
    return os.path.join(PID_FOLDER, filename)


def read_pid(job_name, job_instance_id):
    """Return the PID of the given job or raise NoSuchJobException
    if it can't be found.
    """
    try:
        with open(pid_filename(job_name, job_instance_id)) as pid_file:
            return int(pid_file.read())
    except (IOError, ValueError):
        raise NoSuchJobException from None


def list_jobs_in_dir(dirname):
    """Generate the filename for jobs configuration files in
    the given directory.
    """
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
    proc.wait()


def stop_job_already_running(job_name, job_instance_id):
    try:
        pid = read_pid(job_name, job_instance_id)
    except NoSuchJobException:
        return

    # Get the process
    os.remove(pid_filename(job_name, job_instance_id))
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    # Kill all its children
    children = proc.children(recursive=True)
    for child in children:
        child.terminate()
    _, still_alive = psutil.wait_procs(children, timeout=1)
    for child in still_alive:
        child.kill()

    # Kill the process
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except psutil.TimeoutExpired:
        proc.kill()


def stop_job(job_name, job_instance_id, command=None, args=None):
    """Cancels the execution of a job or stop the instance if
    it was already scheduled.
    """
    try:
        # Cancel the Job Instance
        JobManager().scheduler.remove_job(job_name + job_instance_id)
    except JobLookupError:
        stop_job_already_running(job_name, job_instance_id)
        if command is not None:
            popen(command, args).wait()

    # Remove the Job Instance to the JobManager
    with suppress(KeyError):
        JobManager().pop_instance(job_name, job_instance_id)


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
            status = 'Scheduled'  # 'Programmed on {}'.format(datetime_repr(job.trigger.run_date))
        elif isinstance(job.trigger, IntervalTrigger):
            status = 'Running'  # 'Programmed every {}'.format(job.trigger.interval_length)
    # Connection to the collect agent
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
    with suppress(JobLookupError):
        JobManager().scheduler.remove_job(job_id)


def schedule_job_instance(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, arguments, date_value,
                          reschedule=False):
    """ Function that schedules a Job Instance """
    manager = JobManager()
    timestamp = time.time()
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    try:
        infos = manager.get_job(job_name)
        command = infos['command']
        infos['command_stop']
    except KeyError:
        return date, False
    if not reschedule or date is not None:
        # Schedule the Job Instance
        try:
            manager.scheduler.add_job(
                    launch_job, 'date', run_date=date,
                    args=(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, command, arguments),
                    id=job_name+job_instance_id)
        except ConflictingIdError:
            raise BadRequest('KO A job {} is already programmed'.format(job_name))
        # Register the arguments in the JobManager
        # TODO: See if we should add it too for the non persistents jobs
        if infos['persistent']:
            manager.add_instance(job_name, job_instance_id, arguments, 'date', date)
    return date, True


def schedule_job_instance_stop(job_name, job_instance_id, date_value,
                               reschedule=False):
    """ Function that schedules the stop of the Job Instance """
    manager = JobManager()
    timestamp = time.time()
    date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
    infos = manager.get_job(job_name)
    command_stop = infos['command_stop']
    try:
        infos = manager.pop_instance(job_name, job_instance_id)
        arguments = infos['args']
    except KeyError:
        raise BadRequest('OK job {} with id {} is already '
                         'stopped'.format(job_name, job_instance_id))
    if not reschedule or date is not None:
        # Schedule the stop of the Job Instance
        try:
            manager.scheduler.add_job(
                    stop_job, 'date', run_date=date,
                    args=(job_name, job_instance_id, command_stop, arguments),
                    id='{}{}_stop'.format(job_name, job_instance_id))
        except ConflictingIdError:
            manager.scheduler.reschedule_job(
                    '{}{}_stop'.format(job_name, job_instance_id),
                    trigger='date', run_date=date)
    return date


def schedule_watch(job_name, job_instance_id, date_type, date_value):
    """ Function that schedules the Watch on the Job Instance """
    scheduler = JobManager().scheduler
    timestamp = time.time()
    date = True
    if date_type == 'date':
        date = None if date_value < timestamp else datetime.fromtimestamp(date_value)
        try:
            scheduler.add_job(
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
            scheduler.add_job(
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
        if scheduler.get_job(status_job_id) is None:
            raise BadRequest('KO No watch on the status '
                    'of the instance {} '
                    'with the id {} was programmed'
                    .format(job_name, job_instance_id))
        scheduler.add_job(
                stop_watch, 'date', args=(status_job_id,),
                run_date=date, id='stop_watch_{}'.format(status_job_id))
    return date


def ls_jobs():
    """ Function that sends to the Collector the lists of the Installed Jobs on
    the Agent """
    timestamp = round(time.time() * 1000)
    # Get the Installed Jobs
    jobs = JobManager().job_names
    count = len(jobs)
    job_names = {'job{}'.format(i): job for i, job in enumerate(jobs, 1)}
    # Connection to collect agent
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
    def __init__(self, job_name):
        # Get the configuration filename
        filename = '{}.yml'.format(job_name)
        conf_file = os.path.join(JOBS_FOLDER, filename)
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
            if isinstance(args, list):
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
            self.optional = isinstance(content['arguments']['optional'], list)
            self.persistent = content['general']['persistent']
        except KeyError:
            raise BadRequest(
                    'KO Conf file {} does not contain a '
                    'section for job {}'.format(filename, job_name))


class AgentAction:
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def action(self):
        self.check_arguments()
        self._action()

    def check_arguments(self):
        pass

    def _action(self):
        raise NotImplementedError


class AddJobAgent(AgentAction):
    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        JobManager().add_job(self.name)


class DelJobAgent(AgentAction):
    def __init__(self, name):
        super().__init__(name=name)

    def _action(self):
        manager = JobManager()
        job = manager.pop_job(self.name)
        command_stop = job['command_stop']
        jobs_to_stop = [
                (job_instance_id, command_stop and parameters['args'] or '')
                for job_instance_id, parameters in job['instances'].items()
        ]
        for job_instance_id, arguments in jobs_to_stop:
            manager.scheduler.add_job(
                    stop_job, 'date',
                    args=(self.name, job_instance_id, command_stop, arguments),
                    id='{}{}_stop'.format(self.name, job_instance_id))


class StatusJobInstanceAgent(AgentAction):
    def __init__(self, name, instance_id, date_type, date_value):
        super().__init__(name=name, instance_id=instance_id,
                         date_type=date_type, date=date_value)

    def check_arguments(self):
        JobManager().get_job(self.name)

        if self.date_type in ('date', 'stop'):
            if self.date == 'now':
                self.date = 0
            else:
                try:
                    self.date = int(self.date) // 1000
                except ValueError:
                    raise BadRequest(
                            'KO The {} to watch the status should '
                            'be given as a timestamp in milliseconds'
                            .format(self.date_type))
        elif self.date_type == 'interval':
            try:
                self.date = int(self.date)
            except ValueError:
                raise BadRequest(
                        'KO The interval to execute the job '
                        'should be given in seconds')
        else:
            raise BadRequest(
                    'KO Only "date", "interval" and "stop" '
                    'are allowed with the status action')

    def _action(self):
        schedule_watch(self.name, self.instance_id, self.date_type, self.date)
        # Register the schedule in a file in case the openbach-agent restarts
        filename = '{}{}.status'.format(self.name, self.instance_id)
        filename = os.path.join(INSTANCES_FOLDER, filename)
        if self.date_type == 'stop':
            filename += '_stop'
        with open(filename, 'w') as job_instance_status:
            print(self.name, self.instance_id, self.date_type, self.date,
                  sep='\n', file=job_instance_status)


class StartJobInstanceAgent(AgentAction):
    def __init__(self, name, instance_id, scenario_id, owner_id, date_type, date_value, *arguments):
        super().__init__(
                name=name, instance_id=instance_id, scenario_id=scenario_id,
                owner_id=owner_id, date_type=date_type, date=date_value,
                arguments=arguments)

    def _check_instance(self):
        if JobManager().has_instance(self.name, self.instance_id):
            raise BadRequest(
                    'KO Instance {} with id {} is already '
                    'started'.format(self.name, self.instance_id))

    def check_arguments(self):
        self._check_instance()

        if self.date_type == 'date':
            if self.date == 'now':
                self.date = 0
            else:
                try:
                    self.date = int(self.date) // 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to begin should be '
                            'given as a timestamp in milliseconds')
        elif self.date_type == 'interval':
            try:
                self.date = int(self.date)
            except ValueError:
                raise BadRequest(
                        'KO The interval to execute the '
                        'job should be given in seconds')
        else:
            raise BadRequest(
                    'KO Only "date" and "interval" are allowed '
                    'to be specified when executing the job')

        infos = JobManager().get_job(self.name)
        nb_args = len(infos['required'])
        optional = infos['optional']
        if len(self.arguments) < nb_args:
            raise BadRequest(
                    'KO Job {} requires at least {} arguments'
                    .format(self.name, nb_args))
        if not optional and len(self.arguments) > nb_args:
            raise BadRequest(
                    'KO Job {} does not require more than {} '
                    'arguments'.format(self.name, nb_args))

    def _action(self):
        infos = JobManager().get_job(self.name)
        command = infos['command']
        arguments = ' '.join(self.arguments)
        if self.date_type == 'date':
            date, _ = schedule_job_instance(
                    self.name, self.instance_id, self.scenario_id,
                    self.owner_id, arguments, self.date)
            # If date has not occur yet, register the schedule
            # in a file in case the openbach-agent restarts
            if date is not None:
                filename = '{}{}.start'.format(self.name, self.instance_id)
                filename = os.path.join(INSTANCES_FOLDER, filename)
                with open(filename, 'w') as job_instance_prog:
                    print(self.name, self.instance_id, self.scenario_id,
                          self.owner_id, self.date, arguments,
                          sep='\n', file=job_instance_prog)
        elif date_type == 'interval':
            date = None
            if infos['persistent']:
                raise BadRequest(
                        'KO This job {} is persistent, you can\'t '
                        'start it with the "interval" option'
                        .format(self.name))
            for inst_id, job_args in JobManager().get_instances(self.name):
                if job_args['type'] == 'interval':
                    # [Mathias] Maybe check that instance_id != inst_id ?
                    raise BadRequest('KO A job {} is already '
                                     'programmed. It instance_id is {}.'
                                     ' Please stop it before trying to '
                                     'programme regulary this job '
                                     'again'.format(self.name, inst_id))
            # Schedule the Job Instance
            try:
                JobManager().scheduler.add_job(
                        launch_job, 'interval', seconds=self.date,
                        args=(self.name, self.instance_id, self.scenario_id,
                              self.owner_id, command, arguments),
                        id=self.name + self.instance_id)
            except ConflictingIdError:
                raise BadRequest(
                        'KO An instance {} with the id {} is already '
                        'programmed'.format(self.name, self.instance_id))
        # Register the Job Instance in the JobManager
        JobManager().add_instance(self.name, self.instance_id, arguments, self.date_type, self.date)


class RestartJobInstanceAgent(StartJobInstanceAgent):
    def _check_instance(self):
        pass

    def _action(self):
        with suppress(KeyError):
            job = JobManager().pop_instance(self.name, self.instance_id)
            infos = JobManager().get_job(self.name)
            command_stop = infos['command_stop']
            arguments = job['args']
            stop_job(self.name, self.instance_id, command_stop, arguments)

        super()._action()


class StopJobInstanceAgent(AgentAction):
    def __init__(self, name, instance_id, date_type, date_value):
        super().__init__(name=name, instance_id=instance_id, date_type=date_type, date=date_value)

    def check_arguments(self):
        JobManager().get_job(self.name)

        if self.date_type == 'date':
            if self.date == 'now':
                self.date = 0
            else:
                try:
                    self.date = int(self.date) // 1000
                except ValueError:
                    raise BadRequest(
                            'KO The date to stop should be '
                            'given as a timestamp in milliseconds')
        else:
            raise BadRequest(
                    'KO To stop a job, only a date can be specified')

    def _action(self):
        date = schedule_job_instance_stop(self.name, self.instance_id, self.date)
        # If date has not occur yet, register the schedule in
        # a file in case the openbach-agent restarts
        if date is not None:
            filename = '{}{}.stop'.format(self.name, self.instance_id)
            filename = os.path.join(INSTANCES_FOLDER, filename)
            with open(filename, 'w') as job_instance_stop:
                print(self.name, self.instance_id, self.date,
                      sep='\n', file=job_instance_stop)


class StatusJobsAgent(AgentAction):
    def __init__(self):
        super().__init__()

    def _action(self):
        JobManager().scheduler.add_job(ls_jobs, 'date', id='ls_jobs')


class RestartAgent(AgentAction):
    def __init__(self):
        super().__init__()

    def _action(self):
        manager = JobManager()

        # Stop watches
        for job in manager.scheduler.get_jobs():
            if job.id.endswith('_status'):
                job.remove()

        # Stop actual jobs
        for job_name in manager.job_names:
            job = manager.get_job(job_name)
            command_stop = job['command_stop']
            jobs_to_stop = [
                    (job_instance_id, command_stop and parameters['args'] or '')
                    for job_instance_id, parameters in manager.get_instances(job_name)
            ]
            for job_instance_id, arguments in jobs_to_stop:
                manager.scheduler.add_job(
                        stop_job, 'date',
                        args=(job_name, job_instance_id, command_stop, arguments),
                        id='{}{}_stop'.format(self.name, job_instance_id))


class AgentServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Choose the underlying technology for our sockets servers"""
    allow_reuse_address = True


class RequestHandler(socketserver.BaseRequestHandler):
    def _read_all(self, amount):
        expected = amount
        buffer = bytearray(amount)
        view = memoryview(buffer)
        while amount > 0:
            received = self.request.recv_into(view[-amount:])
            if not received:
                raise TruncatedMessageException(expected, expected - amount)
            amount -= received
        return buffer

    def finish(self):
        self.request.close()

    def handle(self):
        """Handle message comming from the conductor"""
        try:
            message_length = self._read_all(4)
            message_length, = struct.unpack('>I', message_length)
            message = self._read_all(message_length).decode()
            syslog.syslog(syslog.LOG_INFO, message)
            action_name, *arguments = shlex.split(message)
            action = ''.join(map(str.title, action_name.split('_')))
            handler = globals()[action](*arguments)
        except TruncatedMessageException as e:
            self.send_response(str(e), syslog.LOG_WARNING)
        except struct.error as e:
            self.send_response('Error converting the message length to an integer: {}'.format(e), syslog.LOG_CRIT)
        except KeyError:
            self.send_response('Unknown action: {}'.format(action_name), syslog.LOG_CRIT)
        except TypeError as e:
            self.send_response('Bad parameters: {}'.format(e), syslog.LOG_CRIT)
        except Exception as e:
            self.send_response('Error on request: {0.__class__.__name__} {0}'.format(e), syslog.LOG_ERR)
        else:
            try:
                handler.action()
            except BadRequest as e:
                self.send_response(e.reason, syslog.LOG_WARNING if e.reason.startswith('OK') else syslog.LOG_ERR, False)
            except Exception as e:
                self.send_response('Error on request: {0.__class__.__name__} {0}'.format(e), syslog.LOG_ERR)
            else:
                self.send_response('OK', add_ko=False)

    def send_response(self, message, severity=None, add_ko=True):
        if severity is not None:
            syslog.syslog(severity, message)
        if add_ko:
            message = 'KO {}'.format(message)
        result = message.encode()
        length = struct.pack('>I', len(result))
        self.request.sendall(length + result)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGINT, signal_term_handler)

    # Add all the Job already installed
    for job in list_jobs_in_dir(JOBS_FOLDER):
        try:
            JobManager().add_job(job)
        except BadRequest as e:
            syslog.syslog(syslog.LOG_ERR, e.reason)
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
                        JobManager().add_instance(job_name, job_instance_id, arguments, 'date', date)
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

    server = AgentServer(('', 1112), RequestHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
