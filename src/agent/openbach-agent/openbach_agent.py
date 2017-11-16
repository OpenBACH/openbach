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
import sys
import time
import shlex
import struct
import signal
import threading
import platform
import socketserver
from datetime import datetime
from subprocess import DEVNULL
from contextlib import suppress, contextmanager

import yaml
import psutil
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger

try:
    # Try importing unix stuff
    import syslog
    import resource  # TODO: remove it so we no longer need to run the agent as root
    resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))
    OS_TYPE = 'linux'
    JOBS_FOLDER = '/opt/openbach/agent/jobs/'
    INSTANCES_FOLDER = '/opt/openbach/agent/job_instances/'
except ImportError:
    # If we failed assure we’re on windows
    import syslog_viveris as syslog
    OS_TYPE = 'windows'
    JOBS_FOLDER = r'C:\openbach\jobs'
    INSTANCES_FOLDER = r'C:\openbach\instances'


def signal_term_handler(signal, frame):
    """Stop the Openbach Agent gracefully"""
    scheduler = JobManager().scheduler
    scheduler.remove_all_jobs()
    RestartAgent().action()
    while scheduler.get_jobs():
        time.sleep(0.5)
    scheduler.shutdown()
    exit(0)


class JobManager:
    """Context manager around job scheduling"""
    __shared_state = {
            'scheduler': None,
            'jobs': {},
            '_mutex': threading.RLock(),
    }

    def __init__(self):
        self.__dict__ = self.__class__.__shared_state
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler()
            self.scheduler.start()

    def __enter__(self):
        self._mutex.acquire()
        return self

    def __exit__(self, t, v, tr):
        self._mutex.release()

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
        def read_configuration():
            conf = JobConfiguration(name)
            return {
                    'command': conf.command,
                    'command_stop': conf.command_stop,
                    'required': conf.required,
                    'optional': conf.optional,
                    'persistent': conf.persistent,
            }

        with self._mutex:
            if name in self.jobs:
                self.jobs[name].update(read_configuration())
                raise BadRequest('OK A job {} is already installed'.format(name))
            conf = {'instances': {}}
            conf.update(read_configuration())
            self.jobs[name] = conf

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
            instance_infos = self.get_instance(name, instance_id)
            instance = self.jobs[name]['instances'][instance_id]
            del instance['pid']
            del instance['return_code']
            return instance_infos

    def get_instance(self, name, instance_id):
        with self._mutex:
            infos = self.get_job(name)
            infos.update(self.jobs[name]['instances'][instance_id])
            return infos

    def set_instance_status(self, name, instance_id, pid, return_code=None):
        with self._mutex:
            instance = self.jobs[name]['instances'][instance_id]
            if return_code is None or 'pid' in instance:
                instance.update({'pid': pid, 'return_code': return_code})

    def get_last_instance_id(self):
        with self._mutex:
            if not self.jobs:
                return 0

            return max(
                    max(map(int, job['instances']), default=0)
                    for job in self.jobs.values()
            )


class TruncatedMessageException(Exception):
    def __init__(self, expected_length, length):
        message = (
                'Message trunctated before '
                'reading the whole content. '
                'Expected {} bytes but read {}'
                .format(expected_length, length)
        )
        super().__init__(message)


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
            for system in content['platform_configuration']:
                if platform.system() != system['ansible_system']:
                    continue
                name, version, _ = platform.dist()
                if name == system['ansible_distribution'] and version == system['ansible_distribution_version']:
                    self.command = system['command']
                    self.command_stop = system['command_stop']
                    break
            else:
                raise BadRequest(
                        'KO Conf file {} does not contain a '
                        'os for {}'.format(filename, platform.system()))
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
        except KeyError as error:
            raise BadRequest(
                    'KO Conf file {} does not contain a '
                    'section \'{}\' for job {}'
                    .format(filename, error, job_name))


class AgentAction:
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    def action(self):
        self.check_arguments()
        return self._action()

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
        with JobManager() as manager:
            for job_instance_id, _ in manager.get_instances(self.name):
                manager.scheduler.add_job(
                        stop_job, 'date', args=(self.name, job_instance_id),
                        id='{}{}_stop'.format(self.name, job_instance_id))


class StatusJobInstanceAgent(AgentAction):
    def __init__(self, name, instance_id):
        super().__init__(name=name, instance_id=instance_id)

    def check_arguments(self):
        JobManager().get_job(self.name)

    def _action(self):
        manager = JobManager()
        job = manager.scheduler.get_job(self.name + self.instance_id)
        try:
            infos = manager.get_instance(self.name, self.instance_id)
        except KeyError:
            assert job is None
            return 'Not Scheduled'

        try:
            pid = infos['pid']
            return_code = infos['return_code']
        except KeyError:
            return 'Stopped' if job is None else 'Scheduled'

        if return_code:
            return 'Error'

        if return_code is None:
            assert psutil.pid_exists(pid)
            return 'Running'

        assert return_code == 0
        if job:
            assert isinstance(job.trigger, IntervalTrigger)
            return 'Running'

        return 'Not Running'


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
        with JobManager() as manager:
            arguments = ' '.join(self.arguments)
            if self.date_type == 'date':
                date, _ = schedule_job_instance(
                        self.name, self.instance_id, self.scenario_id,
                        self.owner_id, arguments, self.date)
                if date is not None:
                    with recover_file(self.name, self.instance_id, 'start') as job_instance_prog:
                        print(self.name, self.instance_id, self.scenario_id,
                              self.owner_id, self.date, arguments,
                              sep='\n', file=job_instance_prog)
            elif self.date_type == 'interval':
                job_infos = manager.get_job(self.name)
                if job_infos['persistent']:
                    raise BadRequest(
                            'KO This job {} is persistent, you can\'t '
                            'start it with the "interval" option'
                            .format(self.name))
                try:
                    # Schedule the Job Instance
                    manager.scheduler.add_job(
                            launch_job, 'interval', seconds=self.date,
                            args=(self.name, self.instance_id, self.scenario_id,
                                  self.owner_id, job_infos['command'], arguments),
                            id=self.name + self.instance_id)
                except ConflictingIdError:
                    raise BadRequest(
                            'KO An instance {} with the id {} is already '
                            'scheduled'.format(self.name, self.instance_id))
            manager.add_instance(self.name, self.instance_id, arguments, self.date_type, self.date)


class StartJobInstanceAgentId(StartJobInstanceAgent):
    def __init__(self, name, date_type, date_value, *arguments):
        instance_id = str(JobManager().get_last_instance_id() + 1)
        super().__init__(
                name, instance_id, '0', '0',
                date_type, date_value, *arguments)

    def _action(self):
        super()._action()
        return self.instance_id


class RestartJobInstanceAgent(StartJobInstanceAgent):
    def _check_instance(self):
        pass

    def _action(self):
        stop_job(self.name, self.instance_id)
        super()._action()


class StopJobInstanceAgent(AgentAction):
    def __init__(self, name, instance_id, date_type, date_value):
        super().__init__(name=name, instance_id=instance_id, date_type=date_type, date=date_value)

    def check_arguments(self):
        JobManager().get_job(self.name)

        if self.date_type != 'date':
            raise BadRequest(
                    'KO To stop a job, only a date can be specified')

        if self.date == 'now':
            self.date = 0

        try:
            self.date = int(self.date) // 1000
        except ValueError:
            raise BadRequest(
                    'KO The date to stop should be '
                    'given as a timestamp in milliseconds')

    def _action(self):
        date = schedule_job_instance_stop(self.name, self.instance_id, self.date)
        if date is not None:
            with recover_file(self.name, self.instance_id, 'stop') as job_instance_stop:
                print(self.name, self.instance_id, self.date,
                      sep='\n', file=job_instance_stop)


class StatusJobsAgent(AgentAction):
    def __init__(self):
        super().__init__()

    def _action(self):
        jobs = JobManager().job_names
        return ' '.join(map(shlex.quote, jobs))


class RestartAgent(AgentAction):
    def __init__(self):
        super().__init__()

    def _action(self):
        with JobManager() as manager:
            for job_name in manager.job_names:
                for job_instance_id, _ in manager.get_instances(job_name):
                    manager.scheduler.add_job(
                            stop_job, 'date', args=(job_name, job_instance_id),
                            id='{}{}_stop'.format(job_name, job_instance_id))


def popen(command, args, **kwargs):
    """Start a command with the provided arguments and
    return the associated process.

    Additional keywords arguments can be passed to the
    Popen constructor to manage the process creation.
    """
    return psutil.Popen(
            shlex.split(command) + shlex.split(args),
            stdout=DEVNULL, stderr=DEVNULL, **kwargs)


def schedule_job_instance(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, arguments, date_value,
                          reschedule=False):
    """Schedule a Job Instance at a later date.

    Do nothing if the scheduling date is passed and it is a
    reschedule (in case the agent restarted).
    """
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
        try:
            # Schedule the Job Instance
            manager.scheduler.add_job(
                    launch_job, 'date', run_date=date,
                    args=(job_name, job_instance_id, scenario_instance_id,
                          owner_scenario_instance_id, command, arguments),
                    id=job_name+job_instance_id)
        except ConflictingIdError:
            raise BadRequest('KO A job {} is already programmed'.format(job_name))
        # Register the arguments in the JobManager
        manager.add_instance(job_name, job_instance_id, arguments, 'date', date)

    return date, True


def launch_job(job_name, instance_id, scenario_instance_id,
               owner_scenario_instance_id, command, args):
    """Launch the Job Instance and wait for its termination"""
    # Add some environement variable for the Job Instance
    environ = os.environ.copy()
    environ.update({'JOB_NAME': job_name, 'JOB_INSTANCE_ID': instance_id,
                    'SCENARIO_INSTANCE_ID': scenario_instance_id,
                    'OWNER_SCENARIO_INSTANCE_ID': owner_scenario_instance_id})
    # Launch the Job Instance
    proc = popen(command, args, env=environ)
    pid = proc.pid
    JobManager().set_instance_status(job_name, instance_id, pid)
    return_code = proc.wait()
    JobManager().set_instance_status(job_name, instance_id, pid, return_code)


def schedule_job_instance_stop(job_name, job_instance_id, date_value,
                               reschedule=False):
    """ Function that schedules the stop of the Job Instance """
    date = None if date_value < time.time() else datetime.fromtimestamp(date_value)
    if not reschedule or date is not None:
        # Schedule the stop of the Job Instance
        with JobManager() as manager:
            try:
                manager.scheduler.add_job(
                        stop_job, 'date', run_date=date,
                        args=(job_name, job_instance_id),
                        id='{}{}_stop'.format(job_name, job_instance_id))
            except ConflictingIdError:
                manager.scheduler.reschedule_job(
                        '{}{}_stop'.format(job_name, job_instance_id),
                        trigger='date', run_date=date)
    return date


def stop_job(job_name, job_instance_id):
    """Cancels the execution of a job or stop the instance if
    it was already scheduled.
    """
    with JobManager() as manager:
        try:
            infos = manager.pop_instance(job_name, job_instance_id)
            args = infos['args']
            command = infos['command_stop']
        except KeyError:
            pass  # Job is already stopped
        else:
            stop_job_already_running(job_name, job_instance_id, infos)
            if command is not None:
                popen(command, args).wait()
        finally:
            with suppress(JobLookupError):
                manager.scheduler.remove_job(job_name + job_instance_id)


def stop_job_already_running(job_name, job_instance_id, instance_infos):
    """Stop a running process that should be a child of the Agent"""

    # Get the process
    try:
        pid = instance_infos['pid']
    except KeyError:
        return
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
            handler = getattr(sys.modules[__name__], action)(*arguments)
        except TruncatedMessageException as e:
            self.send_response(str(e), syslog.LOG_WARNING)
        except struct.error as e:
            self.send_response(
                    'Error converting the message length to '
                    'an integer: {}'.format(e), syslog.LOG_CRIT)
        except AttributeError:
            self.send_response(
                    'Unknown action: {}'.format(action_name),
                    syslog.LOG_CRIT)
        except TypeError as e:
            self.send_response('Bad parameters: {}'.format(e), syslog.LOG_CRIT)
        except Exception as e:
            self.send_response(
                    'Error on request: {0.__class__.__name__} '
                    '{0}'.format(e), syslog.LOG_ERR)
        else:
            try:
                result = handler.action()
            except BadRequest as e:
                severity = syslog.LOG_ERR
                if e.reason.startswith('OK'):
                    severity = syslog.LOG_WARNING
                self.send_response(e.reason, severity, False)
            except Exception as e:
                self.send_response(
                        'Error on request: {0.__class__.__name__} '
                        '{0}'.format(e), syslog.LOG_ERR)
            else:
                response = 'OK' if result is None else 'OK {}'.format(result)
                self.send_response(response, add_ko=False)

    def send_response(self, message, severity=None, add_ko=True):
        if severity is not None:
            syslog.syslog(severity, message)
        if add_ko:
            message = 'KO {}'.format(message)
        result = message.encode()
        length = struct.pack('>I', len(result))
        self.request.sendall(length + result)


@contextmanager
def recover_file(job_name, job_instance_id, extension):
    """Context Manager providing a file opened in write mode
    aimed at saving informations in case the Agent restart.
    """
    filename = '{}{}.{}'.format(job_name, job_instance_id, extension)
    with open(os.path.join(INSTANCES_FOLDER, filename), 'w') as recover_file:
        yield recover_file


def list_jobs_in_dir(dirname):
    """Generate the filename for jobs configuration files in
    the given directory.
    """
    for filename in os.listdir(dirname):
        name, ext = os.path.splitext(filename)
        if ext == '.yml':
            yield name


def populate_installed_jobs():
    """Read configuration files of Installed Jobs and
    store them into the JobManager.
    """
    with JobManager() as manager:
        for job in list_jobs_in_dir(JOBS_FOLDER):
            try:
                manager.add_job(job)
            except BadRequest as e:
                syslog.syslog(syslog.LOG_ERR, e.reason)


def recover_old_state():
    """Read orders to start/stop jobs at a latter date and try to
    recover from a failure, depending of the current date.
    """
    for root, _, filenames in os.walk(INSTANCES_FOLDER):
        for filename in sorted(filenames):
            fullpath = os.path.join(root, filename)
            with open(fullpath) as f:
                basename, ext = os.path.splitext(filename)
                date = None
                if ext == 'start':
                    try:
                        job_name, instance_id, scenario_id, owner_id, date_value, arguments = f.readlines()
                        date_value = float(date_value)
                    except ValueError:
                        syslog.syslog(
                            syslog.LOG_ERR,
                            'Error with the reading of {}'.format(fullpath))
                        continue
                    date, result = schedule_job_instance(
                            job_name, instance_id, scenario_id,
                            owner_id, arguments, date_value,
                            reschedule=True)
                    if result:
                        JobManager().add_instance(job_name, instance_id, arguments, 'date', date)
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
            if date is None:
                os.remove(fullpath)


if __name__ == '__main__':
    syslog.openlog('openbach_agent', syslog.LOG_PID, syslog.LOG_USER)
    signal.signal(signal.SIGTERM, signal_term_handler)
    signal.signal(signal.SIGINT, signal_term_handler)

    populate_installed_jobs()
    recover_old_state()

    server = AgentServer(('', 1112), RequestHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
