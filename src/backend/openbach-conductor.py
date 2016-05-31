#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
conductor.py - <+description+>
"""

import os
import socket
import shlex
import threading
import subprocess
import getpass
import requests
from datetime import datetime
from contextlib import contextmanager

from django.utils import timezone
from openbach_django.models import Agent, Job, Installed_Job, Instance, Watch
from django.core.exceptions import ObjectDoesNotExist
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()


_UPDATE_AGENT_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}"'
_UPDATE_JOB_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+*+FROM+"{agent.name}.jobs_list"+LIMIT+1'
_UPDATE_INSTANCE_URL = 'http://{agent.collector}:8086/query?db=openbach&epoch=ms&q=SELECT+last("status")+FROM+"{agent.name}.{}{}"'
_SEVERITY_MAPPING = {
    0: 3,   # Error
    1: 4,   # Warning
    2: 6,   # Informational
    3: 7,   # Debug
}


def convert_severity(severity):
    return _SEVERITY_MAPPING.get(severity, 8)


class PlaybookBuilder():
    def __init__(self, path_to_build, path_src):
        self.path_to_build = path_to_build
        self.path_src = path_src

    def _build_helper(self, instance_type, playbook, extra_vars, extra_vars_filename):
        for key, value in extra_vars.items():
            print(key, value, file=extra_vars_filename)

        if instance_type is not None:
            print('    - include: {}{}_instance.yml'
                      .format(self.path_src, instance_type),
                  file=playbook)

        return bool(instance_type)

    def write_hosts(self, address, host_filename='/tmp/openbach_hosts'):
        with open(host_filename, 'w') as hosts:
            print('[Agents]', file=hosts)
            print(address, file=hosts)

    def write_agent(self, address, agent_filename='/tmp/openbach_agents'):
        with open(agent_filename, 'w') as agents:
            print('agents:', file=agents)
            print('  -', address, file=agents)

    @contextmanager
    def playbook_file(self, filename):
        file_name = os.path.join(self.path_to_build, '{}.yml'.format(filename))
        with open(file_name, 'w') as playbook:
            print('---', file=playbook)
            print(file=playbook)
            print('- hosts: Agents', file=playbook)
            print('  tasks:', file=playbook)
            yield playbook

    @contextmanager
    def extra_vars_file(self, filename='/tmp/openbach_extra_vars'):
        with open(filename, 'w') as extra_vars:
            yield extra_vars

    def build_start(self, job_name, instance_id, job_args, date, interval,
                    playbook_handle, extra_vars_handle):
        instance = 'start'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'job_options:': job_args,
        }

        if date is not None:
            variables['date_interval: date'] = date
        elif interval is not None:
            variables['date_interval: interval'] = interval
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_status(self, job_name, instance_id, date, interval, stop,
                     playbook_handle, extra_vars_handle):
        instance = 'status'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
        }

        if date is not None:
            variables['date_interval_stop: date'] = date
        elif interval is not None:
            variables['date_interval_stop: interval'] = interval
        elif stop is not None:
            variables['date_interval_stop: stop'] = stop
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_restart(self, job_name, instance_id, job_args, date, interval,
                      playbook_handle, extra_vars_handle):
        instance = 'restart'
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'job_options:': job_args,
        }
        if date is not None:
            variables['date_interval: date'] = date
        elif interval is not None:
            variables['date_interval: interval'] = interval
        else:
            instance = None

        return self._build_helper(instance, playbook_handle,
                                  variables, extra_vars_handle)

    def build_stop(self, job_name, instance_id, date, playbook, extra_vars):
        variables = {
                'job_name:': job_name,
                'id:': instance_id,
                'date:': date,
        }
        return self._build_helper('stop', playbook, variables, extra_vars)

    def build_status_agent(self, playbook_file):
        print('    - name: Get status of openbach-agent', file=playbook_file)
        print('    - shell: /etc/init.d/openbach-agent status', file=playbook_file)
        return True
    
    def build_ls_jobs(self, playbook_file):
        print('    - name: Get the list of the installed jobs', file=playbook_file)
        print('      shell: /opt/openbach-agent/openbach-baton ls_jobs', file=playbook_file)
        return True
    
    def build_enable_log(self, syslogseverity, syslogseverity_local, job_path,
            playbook_file):
        if syslogseverity != 8 or syslogseverity_local != 8:
            src_file = 'src={}/template/{{{{ item.src }}}}'.format(job_path)
            print('    - name: Push new rsyslog conf files', file=playbook_file)
            print('      template:', src_file,
                  'dest=/etc/rsyslog.d/{{ job }}{{ instance_id }}'
                  '{{ item.dst }}.locked owner=root group=root',
                  file=playbook_file)
            print('      with_items:', file=playbook_file)
            if syslogseverity != 8:
                print("         - { src: 'job.j2', dst: '.conf' }", file=playbook_file)
            if syslogseverity_local != 8:
                print("         - { src: 'job_local.j2', dst: '_local.conf' }", file=playbook_file)
            print(file=playbook_file)
            print('      become: yes', file=playbook_file)
        return True
    
    def build_push_file(self, local_path, remote_path, playbook_file):
        print('    - name: Push file', file=playbook_file)
        print('      copy: src={} dest={}'.format(local_path, remote_path), file=playbook_file)
        print('      become: yes', file=playbook_file)
        return True


class BadRequest(Exception):
    """Custom exception raised when parsing of a request failed"""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class ClientThread(threading.Thread):
    REQUESTS_CHECKER = {
            'add_agent': (2, 'the ip address of the agent'),
            'del_agent': (2, 'the ip address of the agent'),
            'update_agent': (2, 'the ip address of the agent'),
            'update_jobs': (2, 'the ip address of the agent'),
            'install_job':
                (3, 'the ip address of the agent and the name of the job'),
            'uninstall_job':
                (3, 'the ip address of the agent and the name of the job'),
            'start_instance': (4, 'the id of the instance'),
            'restart_instance': (4, 'the id of the instance'),
            'status_instance': (4, 'the id of the instance'),
            'stop_instance': (3, 'the id of the instance'),
            'update_job_stat_policy': (3, 'the id of the instance'),
            'status_agents': (2, 'at least one ip address of an agent'),
            'status_jobs': (2, 'at least one ip address of an agent'),
            'update_instance': (2, 'the id of the instance'),
            'update_job_log_severity':
                (5, 'the instance id of the log jobs, the log '
                'severity and the local log severity to set'),
            'push_file':
                (4, 'the local path of the file you want to send, '
                'the remote path where you want to put the file and '
                'the ip address of the agent'),
    }

    NO_UPPER_LENGTH_CHECK = {
            'status_agents', 'status_jobs'
    }

    NO_DATE_REQUESTS = {
            'add_agent', 'del_agent', 'install_job',
            'uninstall_job', 'status_agents', 'update_agent',
            'status_jobs', 'update_jobs', 'update_instance',
            'push_file',
    }
    ONLY_DATE_REQUESTS = {
            'stop_instance', 'update_job_log_severity', 'update_job_stat_policy',
    }
    DATE_INTERVAL_REQUESTS = {
            'start_instance', 'restart_instance', 'status_instance',
    }

    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.playbook_builder = PlaybookBuilder('/tmp/', '/opt/openbach/roles/backend/tasks/')
    
    def launch_playbook(self, cmd_ansible)
        p = subprocess.run(cmd_ansible, shell=True)
        if not p.returncode:
            raise BadRequest('KO')

    def check_date_interval(self, data_recv):
        try:
            request_type, *date_params = data_recv
        except ValueError:
            raise BadRequest('KO Message not formed well. '
                             'You should provide a request')

        for length, commands in enumerate((
                self.NO_DATE_REQUESTS,
                self.ONLY_DATE_REQUESTS,
                self.DATE_INTERVAL_REQUESTS)):
            if request_type in commands:
                if len(date_params) == length:
                    return
                raise BadRequest('KO Message not formed well. '
                        'Expected {} date parameters to execute the order'
                        ' but got {}.'.format(length, len(date_params)))

        raise BadRequest('KO Message not formed well. Request not knwown.')

    def parse_and_check(self, message):
        data_received = shlex.split(message)
        self.check_date_interval(data_received):

        request_type = data_received[0]
        try:
            length, error_message = self.REQUESTS_CHECKER[request_type]
        except KeyError:
            raise BadRequest('KO Request type not defined')

        actual_length = len(data_received)
        if actual_length < length:
            raise BadRequest('KO Message not formed well. You should '
                    'provide {}'.format(error_message))

        if (actual_length > length and
                request_type not in self.NO_UPPER_LENGTH_CHECK):
            raise BadRequest(
                    'KO Message not formed well. Too much arguments given')

        return data_received

    def execute_request(self, data):
        request, *args = self.parse_and_check(data)

        # From this point on, request should contain the
        # name of one of the following method: call it
        getattr(self, request)(*args)

    def add_agent(self, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        self.playbook_builder.write_hosts(agent.address)
        self.playbook_builder.write_agent(agent.address)
        with self.playbook_builder.extra_vars_file():
            print('local_username:', getpass.getuser(), file=extra_vars)
            print('agent_name:', agent.name)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_agents -e '
            '@/opt/openbach/configs/ips -e '
            '@/tmp/openbach_extra_vars -e @/opt/openbach/configs'
            '/all -e ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password}'
            ' /opt/openbach/agent.yml --tags install'
            .format(agent=agent))

    def del_agent(self, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        self.playbook_builder.write_hosts(agent.address)
        self.playbook_builder.write_agent(agent.address)
        with self.playbook_builder.extra_vars_file() as extra_vars:
            print('local_username:', getpass.getuser(), file=extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/opt/openbach/configs/all -e '
            '@/tmp/openbach_agents -e '
            '@/tmp/openbach_extra_vars -e ' 
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password}'
            ' /opt/openbach/agent.yml --tags uninstall'
            .format(agent=agent))

    def install_job(self, agent_id, job_id):
        agent = Agent.objects.get(pk=agent_id)
        job = Job.objects.get(pk=job_id)
        self.playbook_builder.write_hosts(agent.address)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} '
            '{job.path}/install_{job.name}.yml'
            .format(agent=agent, job=job))

    def uninstall_job(self, agent_id, job_id):
        agent = Agent.objects.get(pk=agent_id)
        job = Job.objects.get(pk=job_id)
        self.playbook_builder.write_hosts(agent.address)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} '
            '{job.path}/uninstall_{job.name}.yml'
            .format(agent=agent, job=job))

    def start_instance(self, watch_type, time_value, instance_id):
            date = time_value if watch_type == 'date' else None
            interval = time_value if watch_type == 'interval' else None
            instance = Instance.objects.get(pk=instance_id)
            job = instance.job.job
            agent = instance.job.agent
            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file(
                    'start_{}'.format(job.name)) as playbook,
            self.playbook_builder.extra_vars_file() as extra_vars:
                self.playbook_builder.build_start(
                        job.name, instance.id,
                        instance.args, date, interval,
                        playbook, extra_vars)
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))

    def stop_instance(self, date, instance_id):
        instance = Instance.objects.get(pk=instance_id)
        job = instance.job.job
        agent = instance.job.agent
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file(
                'stop_{}'.format(job.name)) as playbook,
        self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_stop(
                    job.name, instance.id, date,
                    playbook, extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_extra_vars -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))

    def restart_instance(self, watch_type, time_value, instance_id):
            date = time_value if watch_type == 'date' else None
            interval = time_value if watch_type == 'interval' else None
            instance = Instance.objects.get(pk=instance_id)
            job = instance.job.job
            agent = instance.job.agent
            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file(
                    'restart_{}'.format(job.name)) as playbook,
            self.playbook_builder.extra_vars_file() as extra_vars:
                self.playbook_builder.build_restart(
                        job.name, instance.id,
                        instance.args, date, interval,
                        playbook, extra_vars)
            self.launch_playbook(
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
                .format(playbook.name, agent=agent))

    def status_instance(self, watch_type, time_value, watch_id):
        date = time_value if watch_type == 'date' else None
        interval = time_value if watch_type == 'interval' else None
        stop = time_value if watch_type == 'stop' else None
        watch = Watch.objects.get(pk=watch_id)
        job = watch.job.job
        agent = watch.job.agent
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file(
                'status_{}'.format(job.name)) as playbook,
        self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_status(
                    job.name, instance.id,
                    date, interval, stop,
                    playbook, extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_extra_vars -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))

    def status_agents(self, *agents_ips):
        error_msg = ''
        for agent_ip in agents_ips:
            try:
                agent = Agent.objects.get(pk=agent_ip)
            except ObjectDoesNotExist:
                error_msg += agent_ip + ' '
                continue
            self.playbook_builder.write_hosts(agent.address)
            try:
                subprocess.check_output(
                        ['ping', '-c1', '-w2', agent.address])
            except subprocess.CalledProcessError:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent unreachable'
                agent.update_status= timezone.now()
                agent.save()
                continue
            with self.playbook_builder.playbook_file('status_agent') as playbook:
                playbook_name = playbook.name
            # [Ugly hack] Reset file to remove the last line
            with open(playbook_name, 'w') as playbook:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook_name, agent=agent))
            except BadRequest:
                agent.reachable = False
                agent.update_reachable = timezone.now()
                agent.status = 'Agent reachable but connection impossible'
                agent.update_status= timezone.now()
                agent.save()
                continue
            agent.reachable = True
            agent.update_reachable = timezone.now()
            agent.save()
            with self.playbook_builder.playbook_file('status_agent') as playbook:
                self.playbook_builder.build_status_agent(playbook) 
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook.name, agent=agent))
            except BadRequest:
                pass
        if error_msg:
            raise BadRequest(error_msg)

    def update_agent(self, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        url = _UPDATE_AGENT_URL.format(agent=agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            raise BadRequest('KO Required Stats doesn\'t exist in the Database')

        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value/1000,
                        timezone.get_current_timezone())
            elif column == 'last':
                status = value
        if date > agent.update_status:
            agent.update_status = date
            agent.status = status
            agent.save()
            raise BadRequest('OK Status Updated')
        raise BadRequest('OK Status Not Updated')

    def status_job(self, *agents_ips):
        error_msg = ''
        for agent_ip in agents_ips:
            try:
                agents.append(Agent.objects.get(pk=agent_ip))
            except ObjectDoesNotExist:
                error_msg += agent_ip + ' '
                continue

            self.playbook_builder.write_hosts(agent.address)
            with self.playbook_builder.playbook_file('status_job') as playbook:
                self.playbook_builder.build_ls_jobs(playbook) 
            try:
                self.launch_playbook(
                    'ansible-playbook -i /tmp/openbach_hosts -e '
                    'ansible_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                    .format(playbook.name, agent=agent))
            except BadRequest:
                pass
        if error_msg:
            raise BadRequest(error_msg)

    def update_jobs(self, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        url = _UPDATE_JOB_URL.format(agent=agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            try:
                raise BadRequest('KO 1 {}'.format(result['results'][0]['error']))
            except KeyError:
                raise BadRequest('KO No data available')

        jobs_list = []
        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value / 1000,
                        timezone.get_current_timezone())
            elif column != 'nb':
                jobs_list.append(value)

        for job in agent.installed_job_set.all():
            job_name = job.job.name
            if job_name not in jobs_list:
                job.delete()
            else:
                jobs_list.remove(job_name)

        error_msg = 'KO 2'
        for job_name in jobs_list:
            try:
                job = Job.objects.get(pk=job_name)
            except ObjectDoesNotExist:
                error_msg = '{} {}'.format(error_msg, job_name)
                continue
            installed_job = Installed_Job(agent=agent, job=job)
            installed_job.set_name()
            installed_job.update_status = date
            installed_job.severity = 4
            installed_job.local_severity = 4
            installed_job.stats_default_policy = True
            installed_job.save()

        if error_msg != 'KO 2':
            raise BadRequest(error_msg)

    def update_instance(self, instance_id):
        instance = Instance.objects.get(pk=instance_id)
        url = _UPDATE_INSTANCE_URL.format(
                instance.job.job.name, instance.id, agent=instance.job.agent)
        result = requests.get(url).json()
        try:
            columns = result['results'][0]['series'][0]['columns']
            values = result['results'][0]['series'][0]['values'][0]
        except KeyError:
            try:
                raise BadRequest('KO {}'.format(result['results'][0]['error']))
            except KeyError:
                raise BadRequest('KO No data available')

        for column, value in zip(columns, values):
            if column == 'time':
                date = datetime.fromtimestamp(value / 1000,
                        timezone.get_current_timezone())
            elif column == 'last':
                status = value
        instance.update_status = date
        instance.status = status
        instance.save()

    def update_job_log_severity(self, date, instance_id, severity, local_severity):
        instance = Instance.objects.get(pk=instance_id)
        agent = instance.job.agent
        logs_job_path = instance.job.job.path
        job_name = instance.args.split()[0]
        syslogseverity = convert_severity(int(severity))
        syslogseverity_local = convert_severity(int(local_severity))
        disable = 0
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file('logs') as playbook,
        self.playbook_builder.extra_vars_file() as extra_vars:
            if syslogseverity == 8:
                disable += 1
            else:
                print('collector_ip:', agent.collector, file=extra_vars)
                print('syslogseverity:', syslogseverity, file=extra_vars)
            if syslogseverity_local == 8:
                disable += 2
            else:
                print('syslogseverity_local:', syslogseverity_local, file=extra_vars)
            print('job:', job_name, file=extra_vars)
            print('instance_id:', instance.id, file=extra_vars)

            instance.args = '{} {}'.format(instance.args, disable)
            instance.save()

            self.playbook_builder.build_enable_log(
                    syslogseverity, syslogseverity_local,
                    logs_job_path, playbook)
            self.playbook_builder.build_start(
                    'rsyslog_job', instance_id, instance.args,
                    date, None, playbook, extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_extra_vars -e '
            '@/opt/openbach/configs/all -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))

    def update_job_stat_policy(self, date, instance_id):
        instance = Instance.objects.get(pk=instance_id)
        agent = instance.job.agent
        rstats_job_path = instance.job.job.path
        job_name = instance.args.split()[0]
        installed_name = '{} on {}'.format(job_nam, agent.address)
        installed_job = Installed_Job.objects.get(pk=installed_name)
        with open('/tmp/openbach_rstats_filter', 'w') as rstats_filter:
            print('[default]', file=rstats_filter)
            print('enabled =', installed_job.stats_default_policy,
                    file=rstats_filter)
            for stats in installed_job.accept_stats.split():
                print('[{}]'.format(stats), file=rstats_filter)
                print('enabled = True', file=rstats_filter)
            for stats in installed_job.deny_stats.split():
                print('[{}]'.format(stats), file=rstats_filter)
                print('enabled = False', file=rstats_filter)
        self.playbook_builder.write_hosts(agent.address)
        remote_path = ('/opt/openbach-jobs/{0}/{0}{1}'
                '_rstats_filter.conf.locked').format(job_name, instance.id)
        with self.playbook_builder.playbook_file('rstats') as playbook,
        self.playbook_builder.extra_vars_file() as extra_vars:
            self.playbook_builder.build_push_file(
                    rstats_filter.name, remote_path, playbook)
            self.playbook_builder.build_start(
                    'rstats_job', instance_id, instance.args,
                    date, None, playbook, extra_vars)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            '@/tmp/openbach_extra_vars -e '
            '@/opt/openbach/configs/all -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))

    def push_file(self, local_path, remote_path, agent_id):
        agent = Agent.objects.get(pk=agent_id)
        self.playbook_builder.write_hosts(agent.address)
        with self.playbook_builder.playbook_file('push_file') as playbook:
            self.playbook_builder.build_push_file(
                    local_path, remote_path, playbook)
        self.launch_playbook(
            'ansible-playbook -i /tmp/openbach_hosts -e '
            'ansible_ssh_user={agent.username} -e '
            'ansible_sudo_pass={agent.password} -e '
            'ansible_ssh_pass={agent.password} {}'
            .format(playbook.name, agent=agent))

    def run(self):
        request = self.clientsocket.recv(2048)
        try:
            self.execute_request(request.decode())
        except BadRequest as e:
            self.clientsocket.send(e.reason.encode())
        except UnicodeError:
            self.clientsocket.send(b'KO Undecypherable request')
        else:
            self.clientsocket.send(b'OK')
        finally:
            self.clientsocket.close()


if __name__ == '__main__':
    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 1113))
    tcp_socket.listen(10)

    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()

