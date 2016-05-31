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
from django.utils import timezone
from openbach_django.models import Agent, Job, Installed_Job, Instance, Watch
from django.core.exceptions import ObjectDoesNotExist
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()


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
            print(key, value, file=extra_vars_file)

        if instance_type is not None:
            print('    - include: {}{}_instance.yml'
                      .format(self.path_src, instance_type),
                  file=playbook_file)

        return bool(instance_type)

    def playbook_filename(self, filename):
        return os.path.join(self.path_to_build, '{}.yml'.format(filename))

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
    
    def launch_playbook(self, cmd_ansible, send_status=True):
        p = subprocess.run(cmd_ansible, shell=True)
        status = not p.returncode
        if send_status:
            self.clientsocket.send(b'OK' if status else b'KO')
        return status
        
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
            
    
    def run(self): 
        try:
            data = self.parse_and_check(self.clientsocket.recv(2048))
        except BadRequest as error:
            self.clientsocket.send(error.reason.encode())
            self.clientsocket.close()
            return

        request_type = data[0]
        if request_type == 'add_agent':
            agent = Agent.objects.get(pk=data[1])
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            with open('/tmp/openbach_agents', 'w') as agents:
                print('agents:', file=agents)
                print('  -', agent.address, file=agents)
            with open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('local_username:', getpass.getuser(), file=extra_vars)
                print('agent_name:', agent.name)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_agents -e '
                '@/opt/openbach/configs/ips -e '
                '@/tmp/openbach_extra_vars -e @/opt/openbach/configs'
                '/all -e ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password}'
                ' /opt/openbach/agent.yml --tags install').format(agent=agent)
        elif request_type == 'del_agent':
            agent = Agent.objects.get(pk=data[1])
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            with open('/tmp/openbach_agents', 'w') as agents:
                print('agents:', file=agents)
                print('  -', agent.address, file=agents)
            with open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('local_username:', getpass.getuser(), file=extra_vars)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/opt/openbach/configs/all -e '
                '@/tmp/openbach_agents -e '
                '@/tmp/openbach_extra_vars -e ' 
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password}'
                ' /opt/openbach/agent.yml --tags uninstall'
            ).format(agent=agent)
        elif request_type == 'install_job':
            agent = Agent.objects.get(pk=data[1])
            job = Job.objects.get(pk=data[2])
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} '
                '{job.path}/install_{job.name}.yml'
            ).format(agent=agent, job=job)
        elif request_type == 'uninstall_job':
            agent = Agent.objects.get(pk=data[1])
            job = Job.objects.get(pk=data[2])
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} '
                '{job.path}/uninstall_{job.name}.yml'
            ).format(agent=agent, job=job)
        elif request_type == 'start_instance':
            watch_type = data[1]
            date = data[2] if watch_type == 'date' else None
            interval = data[2] if watch_type == 'interval' else None
            instance = Instance.objects.get(pk=data[3])
            job = instance.job.job
            agent = instance.job.agent
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            playbook_filename = self.playbook_builder.playbook_filename(
                    'start_{}'.format(job.name))
            with open(playbook_filename, 'w') as playbook,
                    open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
                print('  tasks:', file=playbook)
                self.playbook_builder.build_start(
                        job.name, instance.id,
                        instance.args, date, interval,
                        playbook, extra_vars)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
            ).format(playbook_filename, agent=agent)
        elif request_type == 'stop_instance':
            date = data[1]
            instance = Instance.objects.get(pk=data[2])
            job = instance.job.job
            agent = instance.job.agent
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            playbook_filename = self.playbook_builder.playbook_filename(
                    'stop_{}'.format(job.name))
            with open(playbook_filename, 'w') as playbook,
                    open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
                print('  tasks:', file=playbook)
                self.playbook_builder.build_stop(
                        job.name, instance.id, date,
                        playbook, extra_vars)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
            ).format(playbook_filename, agent=agent)
        elif request_type == 'restart_instance':
            watch_type = data[1]
            date = data[2] if watch_type == 'date' else None
            interval = data[2] if watch_type == 'interval' else None
            instance = Instance.objects.get(pk=data[3])
            job = instance.job.job
            agent = instance.job.agent
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            playbook_filename = self.playbook_builder.playbook_filename(
                    'restart_{}'.format(job.name))
            with open(playbook_filename, 'w') as playbook,
                    open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
                print('  tasks:', file=playbook)
                self.playbook_builder.build_restart(
                        job.name, instance.id,
                        instance.args, date, interval,
                        playbook, extra_vars)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
            ).format(playbook_filename, agent=agent)
        elif request_type == 'status_instance':
            watch_type = data[1]
            date = data[2] if watch_type == 'date' else None
            interval = data[2] if watch_type == 'interval' else None
            stop = data[2] if watch_type == 'stop' else None
            watch = Watch.objects.get(pk=data[3])
            job = watch.job.job
            agent = watch.job.agent
            with open('/tmp/openbach_hosts', 'w') as hosts:
                print('[Agents]', file=hosts)
                print(agent.address, file=hosts)
            playbook_filename = self.playbook_builder.playbook_filename(
                    'status_{}'.format(job.name))
            with open(playbook_filename, 'w') as playbook,
                    open('/tmp/openbach_extra_vars', 'w') as extra_vars:
                print('---', file=playbook)
                print(file=playbook)
                print('- hosts: Agents', file=playbook)
                print('  tasks:', file=playbook)
                self.playbook_builder.build_status(
                        job.name, instance.id,
                        date, interval, stop,
                        playbook, extra_vars)
            cmd_ansible = (
                'ansible-playbook -i /tmp/openbach_hosts -e '
                '@/tmp/openbach_extra_vars -e '
                'ansible_ssh_user={agent.username} -e '
                'ansible_sudo_pass={agent.password} -e '
                'ansible_ssh_pass={agent.password} {}'
            ).format(playbook_filename, agent=agent)
        elif request_type == 'status_agents':
            error_msg = ''
            for agent_ip in data[1:]:
                try:
                    agent = Agent.objects.get(pk=agent_ip)
                except ObjectDoesNotExist:
                    error_msg += agent_ip + ' '
                    continue
                with open('/tmp/openbach_hosts', 'w') as hosts:
                    print('[Agents]', file=hosts)
                    print(agent.address, file=hosts)
                playbook_filename =
                    self.playbook_builder.playbook_filename('status_agent')
                try:
                    subprocess.check_output(
                            ['ping', '-c1', '-w2', agent.address])
                except subprocess.CalledProcessError:
                    agent.reachable = False
                    agent.update_reachable = timezone.now()
                    agent.status = "Agent unreachable"
                    agent.update_status= timezone.now()
                    agent.save()
                    continue
                with open(playbook_filename, 'w') as playbook:
                    print('---', file=playbook)
                    print(file=playbook)
                    print('- hosts: Agents', file=playbook)
                cmd_ansible = (
                    'ansible-playbook -i /tmp/openbach_hosts -e ansib'
                    'le_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                ).format(playbook_filename, agent=agent)
                if not self.launch_playbook(cmd_ansible, False):
                    agent.reachable = False
                    agent.update_reachable = timezone.now()
                    agent.status = "Agent reachable but connection impossible"
                    agent.update_status= timezone.now()
                    agent.save()
                    continue
                agent.reachable = True
                agent.update_reachable = timezone.now()
                agent.save()
                with open(playbook_filename, 'w') as playbook:
                    print('---', file=playbook)
                    print(file=playbook)
                    print('- hosts: Agents', file=playbook)
                    print('  tasks:', file=playbook)
                    self.playbook_builder.build_status_agent(playbook) 
                cmd_ansible = (
                    'ansible-playbook -i /tmp/openbach_hosts -e ansib'
                    'le_ssh_user={agent.username} -e '
                    'ansible_ssh_pass={agent.password} {}'
                ).format(playbook_filename, agent=agent)
                self.launch_playbook(cmd_ansible, False)
            if error_msg:
                self.clientsocket.send(error_msg.encode())
            self.clientsocket.close()
            return
        elif request_type == 'update_agent':
            agent_ip = data_recv[1]
            agent = Agent.objects.get(pk=agent_ip)
            url = "http://" + agent.collector + ":8086/query?db=openbach&epoch="
            url += "ms&q=SELECT+last(\"status\")+FROM+\"" + agent.name + "\""
            r = requests.get(url)
            if 'series' not in r.json()['results'][0]:
                self.clientsocket.send("KO Required Stats doesn't exist in"
                                       " the Database")
                self.clientsocket.close()
                return
            columns = r.json()['results'][0]['series'][0]['columns']
            for i in range(len(columns)):
                if columns[i] == 'time':
                    timestamp = r.json()['results'][0]['series'][0]['values'][0][i]/1000.
                elif columns[i] == 'last':
                    status = r.json()['results'][0]['series'][0]['values'][0][i]
            date = datetime.fromtimestamp(timestamp,
                                          timezone.get_current_timezone())
            if date > agent.update_status:
                agent.update_status = date
                agent.status = status
                agent.save()
                return_msg = "OK Status Updated"
            else:
                return_msg = "OK Status Not Updated"
            self.clientsocket.send(return_msg)
            self.clientsocket.close()
            return
        elif request_type == 'status_jobs':
            agents_ip = data_recv[1:]
            agents = []
            error_msg = ''
            for agent_ip in agents_ip:
                try:
                    agents.append(Agent.objects.get(pk=agent_ip))
                except ObjectDoesNotExist:
                    error_msg += agent_ip + ' '
                for agent in agents:
                    hosts = open('/tmp/openbach_hosts', 'w')
                    hosts.write("[Agents]\n" + agent.address + "\n")
                    hosts.close()
                    playbook_filename = self.playbook_builder.path_to_build
                    playbook_filename += "status_job.yml"
                    playbook = open(playbook_filename, 'w')
                    playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
                    self.playbook_builder.build_ls_jobs(playbook) 
                    playbook.close()
                    cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansib"
                    cmd_ansible += "le_ssh_user=" + agent.username + " -e "
                    cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
                    cmd_ansible += playbook_filename
                    p = subprocess.Popen(cmd_ansible, shell=True)
                    p.wait()
                    if p.returncode != 0:
                        continue
            if error_msg != '':
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return
        elif request_type == 'update_jobs':
            agent_ip = data_recv[1]
            agent = Agent.objects.get(pk=agent_ip)
            stat_name = agent.name + ".jobs_list"
            url = "http://" + agent.collector + ":8086/query?db=openbach&epoch="
            url += "ms&q=SELECT+*+FROM+\"" + stat_name + "\"+LIMIT+1"
            r = requests.get(url)
            if 'series' not in r.json()['results'][0]:
                self.clientsocket.send("KO 1 " + r.json()['results'][0]['error'])
                self.clientsocket.close()
                return
            jobs_list = []
            results = r.json()['results'][0]['series'][0]
            for i in range(len(results['columns'])):
                if results['columns'][i] == "time":
                    timestamp = results['values'][0][i]/1000.
                    continue
                if results['columns'][i] == "nb":
                    continue
                jobs_list.append(results['values'][0][i])
            date = datetime.fromtimestamp(timestamp,
                                          timezone.get_current_timezone())
            installed_jobs = agent.installed_job_set
            for job in installed_jobs.iterator():
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
                    error_msg += ' ' + job_name
                    continue
                installed_job = Installed_Job(agent=agent, job=job)
                installed_job.set_name()
                installed_job.update_status = date
                installed_job.severity = 4
                installed_job.local_severity = 4
                installed_job.stats_default_policy=True
                installed_job.save()
            if error_msg != 'KO 2':
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return
        elif request_type == 'update_instance':
            instance_id = data_recv[1]
            instance = Instance.objects.get(pk=instance_id)
            agent = instance.job.agent
            url = "http://" + agent.collector + ":8086/query?db=openbach&epoch="
            url += "ms&q=SELECT+last(\"status\")+FROM+\"" + agent.name + "."
            url += instance.job.job.name + instance_id + "\""
            r = requests.get(url)
            if 'series' not in r.json()['results'][0]:
                if 'error' in r.json()['results'][0]:
                    self.clientsocket.send("KO " + r.json()['results'][0]['error'])
                else:
                    self.clientsocket.send("KO No data available")
                self.clientsocket.close()
                return
            columns = r.json()['results'][0]['series'][0]['columns']
            for i in range(len(columns)):
                if columns[i] == 'time':
                    timestamp = r.json()['results'][0]['series'][0]['values'][0][i]/1000.
                elif columns[i] == 'last':
                    status = r.json()['results'][0]['series'][0]['values'][0][i]
            date = datetime.fromtimestamp(timestamp,
                                          timezone.get_current_timezone())
            instance.update_status = date
            instance.status = status
            instance.save()
        elif request_type == 'update_job_log_severity':
            date = data_recv[1]
            instance_id = data_recv[2]
            severity = data_recv[3]
            local_severity = data_recv[4]
            instance = Instance.objects.get(pk=instance_id)
            agent = instance.job.agent
            logs_job_path = instance.job.job.path
            job_name = instance.args.split()[0]
            syslogseverity = convert_severity(int(severity))
            syslogseverity_local = convert_severity(int(local_severity))
            disable = 0
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            if syslogseverity != 8:
                collector_ip = agent.collector
                extra_vars.write("collector_ip: " + collector_ip +
                                 "\nsyslogseverity: " + str(syslogseverity) +
                                 "\n")
            else:
                disable = 1
            if syslogseverity_local != 8:
                extra_vars.write("syslogseverity_local: " +
                                 str(syslogseverity_local) + "\n")
            else:
                if disable == 1:
                    disable = 3
                else:
                    disable = 2
            extra_vars.write("job: " + job_name + "\ninstance_id: " +
                             str(instance.id))
            instance.args += " " + str(disable)
            instance.save()
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "logs.yml"
            playbook = open(playbook_filename, 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_enable_log(playbook, syslogseverity,
                                                   syslogseverity_local,
                                                   logs_job_path)
            self.playbook_builder.build_start(playbook, 'rsyslog_job',
                                              instance_id, instance.args, date,
                                              None, extra_vars)
            extra_vars.close()
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "@/opt/openbach/configs/all -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password
            cmd_ansible += " " + playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'update_job_stat_policy':
            date = data_recv[1]
            instance_id = data_recv[2]
            instance = Instance.objects.get(pk=instance_id)
            agent = instance.job.agent
            rstats_job_path = instance.job.job.path
            job_name = instance.args.split()[0]
            installed_job = Installed_Job.objects.get(pk=job_name + " on " +
                                                      agent.address)
            rstats_filter_filename = '/tmp/openbach_rstats_filter'
            rstats_filter = open(rstats_filter_filename, 'w')
            rstats_filter.write("[default]\nenabled=" +
                                str(installed_job.stats_default_policy) + "\n")
            for stats in installed_job.accept_stats.split():
                rstats_filter.write("[" + stats + "]\nenabled=True\n")
            for stats in installed_job.deny_stats.split():
                rstats_filter.write("[" + stats + "]\nenabled=False\n")
            rstats_filter.close()
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "rstats.yml"
            playbook = open(playbook_filename, 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            remote_path = "/opt/openbach-jobs/" + job_name + "/" + job_name
            remote_path += instance_id + "_rstats_filter.conf.locked"
            self.playbook_builder.build_push_file(playbook,
                                                     rstats_filter_filename,
                                                     remote_path)
            self.playbook_builder.build_start(playbook, 'rstats_job',
                                              instance_id, instance.args, date,
                                              None, extra_vars)
            extra_vars.close()
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "@/opt/openbach/configs/all -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password
            cmd_ansible += " " + playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'push_file':
            local_path = data_recv[1]
            remote_path = data_recv[2]
            agent_ip = data_recv[3]
            agent = Agent.objects.get(pk=agent_ip)
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "push_file.yml"
            playbook = open(playbook_filename, 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_push_file(playbook, local_path,
                                                     remote_path)
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password
            cmd_ansible += " " + playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
 
        self.launch_playbook(cmd_ansible)
        self.clientsocket.close()
    
    
if __name__ == '__main__':
    # Ouverture de la socket d'ecoute
    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_socket.bind(('', 1113))
    
    num_connexion_max = 10
    tcp_socket.listen(num_connexion_max)
    while True:
        client_socket, _ = tcp_socket.accept()
        ClientThread(client_socket).start()

