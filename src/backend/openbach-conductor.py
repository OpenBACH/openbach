#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
conductor.py - <+description+>
"""

import socket
import shlex
import threading
import os
import subprocess
import getpass
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()
from openbach_django.models import Agent, Job, Installed_Job, Instance, Watch
from django.core.exceptions import ObjectDoesNotExist
import requests
from datetime import datetime
from django.utils import timezone

def convert_severity(severity):
    error = 0
    warning = 1
    informational = 2
    debug = 3
    if severity == error:
        return 3
    elif severity == warning:
        return 4
    elif severity == informational:
        return 6
    elif severity == debug:
        return 7
    else:
        return 8

class PlaybookBuilder():
    def __init__(self, path_to_build, path_src):
        self.path_to_build = path_to_build
        self.path_src = path_src

    def build_start(self, playbook, job_name, instance_id, job_args, date,
                    interval, extra_vars):
        extra_vars.write("\njob_name: " + job_name + "\nid: " + instance_id +
                         "\njob_options: " + job_args + "\ndate_interval: ")
        if date != None:
            extra_vars.write("date " + date)
        elif interval != None:
            extra_vars.write("interval " + interval)
        else:
            return False
        playbook.write("    - include: " + self.path_src +
                       "start_instance.yml\n")
        return True

    def build_status(self, playbook, job_name, instance_id, date, interval,
                     stop, extra_vars):
        extra_vars.write("\njob_name: " + job_name + "\nid: " + instance_id +
                         "\ndate_interval_stop: ")
        if date != None:
            extra_vars.write("date " + date )
        elif interval != None:
            extra_vars.write("interval " + interval)
        elif stop != None:
            extra_vars.write("stop " + stop)
        else:
            return False
        playbook.write("\n\n    - include: " + self.path_src +
                       "status_instance.yml\n")
        return True

    def build_restart(self, playbook, job_name, instance_id, job_args, date,
                      interval, extra_vars):
        extra_vars.write("\njob_name: " + job_name + "\nid: " + instance_id +
                         "\njob_options: " + job_args + "\ndate_interval: ")
        if date != None:
            extra_vars.write("date " + date)
        elif interval != None:
            extra_vars.write("interval " + interval)
        else:
            return False
        playbook.write("\n\n    - include: " + self.path_src +
                       "restart_instance.yml\n")
        return True

    def build_stop(self, playbook, job_name, instance_id, date, extra_vars):
        extra_vars.write("\njob_name: " + job_name + "\nid: " + instance_id +
                         "\ndate: date " + date)
        playbook.write("\n\n    - include: " + self.path_src +
                       "stop_instance.yml\n")
        return True

    def build_status_agent(self, playbook):
        playbook.write("    - name: Get status of openbach-agent\n      shell:"
                       + "/etc/init.d/openbach-agent status\n")
        return True
    
    def build_ls_jobs(self, playbook):
        playbook.write("    - name: Get the list of the installed jobs\n" +
                       "shell: /opt/openbach-agent/openbach-baton ls_jobs\n")
        return True
    
    def build_enable_log(self, playbook, syslogseverity, syslogseverity_local,
                         job_path):
        if syslogseverity != 8 or syslogseverity_local != 8:
            playbook.write("    - name: Push new rsyslog conf files\n      template:" +
                           " src=" + job_path + "templates/{{ item.src }} " +
                           "dest=/etc/rsyslog.d/{{ job }}{{ instance_id }}{{" +
                           " item.dst }}.locked owner=root group=root\n" +
                           "      with_items:\n   ")
        if syslogseverity != 8:
            playbook.write("     - { src: 'job.j2', dst: '.conf' }\n   ")
        if syslogseverity_local != 8:
            playbook.write("     - { src: 'job_local.j2', dst: '_local.conf' }")
        if syslogseverity != 8 or syslogseverity_local != 8:
            playbook.write("\n      become: yes\n\n")
        return True
    
    def build_enable_stats(self, playbook, rstats_filter_filename, job_name,
                           instance_id):
        playbook.write("    - name: Push new rstats conf file\n      copy: src="
                       + rstats_filter_filename + " dest=" +
                       "/opt/openbach-jobs/" + job_name + "/" + job_name +
                       instance_id + "_rstats_filter.conf.locked\n      become:"
                       + " yes\n\n")
        return True

class ClientThread(threading.Thread):
    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.playbook_builder = PlaybookBuilder("/tmp/",
                                                "/opt/openbach/roles/backend/tasks/")
    
    def launch_playbook(self, cmd_ansible):
        p = subprocess.Popen(cmd_ansible, shell=True)
        p.wait()
        if p.returncode != 0:
            self.clientsocket.send('KO')
            self.clientsocket.close()
            return False
        return True
        

    def check_date_interval(self, data_recv):
        request_type = data_recv[0]
        no_date = ['add_agent', 'del_agent', 'install_job', 'uninstall_job',
                   'status_agents', 'update_agent', 'status_jobs',
                   'update_jobs', 'update_instance']
        only_date = ['stop_instance', 'update_job_log_severity',
                     'update_job_stat_policy']
        date_interval = ['start_instance', 'restart_instance', 'status_instance']
        if request_type in no_date:
            pass
        elif request_type in only_date:
            if len(data_recv) < 2:
                error_msg = "KO Message not formed well. You should provide a "
                error_msg += "date when to execute the order"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return False
        elif request_type in date_interval:
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide a "
                error_msg += "date or an interval in order to execute the order"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return False
        else:
            error_msg = "KO Message not formed well. Request not knwown"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return False
        return True

    def parse_and_check(self, r):
        data_recv = shlex.split(r)
        if len(data_recv) < 1:
            error_msg = "KO Message not formed well. You should provide a "
            error_msg += "request"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return []
        if not self.check_date_interval(data_recv):
            return []
        request_type = data_recv[0]
        if request_type == 'add_agent' or request_type == 'del_agent' or request_type == 'update_agent' or request_type == 'update_jobs':
            if len(data_recv) < 2:
                error_msg = "KO Message not formed well. You should provide the"
                error_msg += " ip address of the agent"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 2:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'install_job' or request_type == 'uninstall_job':
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the ip address of the agent and the name of the job"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 3:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'start_instance' or request_type == 'restart_instance' or request_type == 'status_instance':
            if len(data_recv) < 4:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the id of the instance"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 4:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'stop_instance' or request_type == 'update_job_stat_policy':
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the id of the instance"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 3:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'status_agents' or request_type == 'status_jobs':
            if len(data_recv) < 2:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "at least one ip address of an agent"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'update_instance':
            if len(data_recv) < 2:
                error_msg = "KO Message not formed well. You should provide the"
                error_msg += " id of the instance"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 2:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'update_job_log_severity':
            if len(data_recv) < 5:
                error_msg = "KO Message not formed well. You should provide the"
                error_msg += " instance id of the logs Job, the"
                error_msg += " log severity and the local log severity to set"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 5:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        else:
            error_msg = "KO Request type not defined"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return []
        return data_recv
            
    
    def run(self): 
        r = self.clientsocket.recv(2048)

        data_recv = self.parse_and_check(r)
        if len(data_recv) == 0:
            return
        request_type = data_recv[0]
        if request_type == 'add_agent':
            agent_ip = data_recv[1]
            agent = Agent.objects.get(pk=agent_ip)
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            agents = open('/tmp/openbach_agents', 'w')
            agents.write("agents:\n  - " + agent.address)
            agents.close()
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            extra_vars.write("local_username: " + getpass.getuser())
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_agents -e "
            cmd_ansible += "@/opt/openbach/configs/ips -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e @/opt/openbach/configs"
            cmd_ansible += "/all -e ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password
            cmd_ansible += " /opt/openbach/agent.yml --tags install"
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'del_agent':
            agent_ip = data_recv[1]
            agent = Agent.objects.get(pk=agent_ip)
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            agents = open('/tmp/openbach_agents', 'w')
            agents.write("agents:\n  - " + agent.address)
            agents.close()
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            extra_vars.write("local_username: " + getpass.getuser())
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/opt/openbach/configs/all -e "
            cmd_ansible += "@/tmp/openbach_agents -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e " 
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password
            cmd_ansible += " /opt/openbach/agent.yml --tags uninstall"
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'install_job':
            agent_ip = data_recv[1]
            job_name = data_recv[2]
            agent = Agent.objects.get(pk=agent_ip)
            job = Job.objects.get(pk=job_name)
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += job.path + "/install_" + job.name + ".yml"
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'uninstall_job':
            agent_ip = data_recv[1]
            job_name = data_recv[2]
            agent = Agent.objects.get(pk=agent_ip)
            job = Job.objects.get(pk=job_name)
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += job.path + "/uninstall_" + job.name + ".yml"
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'start_instance':
            if data_recv[1] == 'date':
                date = data_recv[2]
                interval = None
            elif data_recv[1] == 'interval':
                date = None
                interval = data_recv[2]
            instance_id = data_recv[3]
            instance = Instance.objects.get(pk=instance_id)
            job = instance.job.job
            agent = instance.job.agent
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "start_"
            playbook_filename += job.name + ".yml"
            playbook = open(playbook_filename, 'w')
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_start(playbook, job.name, instance_id,
                                              instance.args, date, interval,
                                              extra_vars)
            playbook.close()
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'stop_instance':
            date = data_recv[1]
            instance_id = data_recv[2]
            instance = Instance.objects.get(pk=instance_id)
            job = instance.job.job
            agent = instance.job.agent
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "stop_"
            playbook_filename += job.name + ".yml"
            playbook = open(playbook_filename, 'w')
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_stop(playbook, job.name, instance_id,
                                             date, extra_vars)
            playbook.close()
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'restart_instance':
            if data_recv[1] == 'date':
                date = data_recv[2]
                interval = None
            elif data_recv[1] == 'interval':
                date = None
                interval = data_recv[2]
            instance_id = data_recv[3]
            instance = Instance.objects.get(pk=instance_id)
            job = instance.job.job
            agent = instance.job.agent
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "restart_"
            playbook_filename += job.name + ".yml"
            playbook = open(playbook_filename, 'w')
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_restart(playbook, job.name, instance_id,
                                                instance.args, date, interval,
                                                extra_vars)
            playbook.close()
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'status_instance':
            watch_type = data_recv[1]
            if watch_type == 'date':
                date = data_recv[2]
                interval = None
                stop = None
            elif watch_type == 'interval':
                date = None
                interval = data_recv[2]
                stop = None
            elif watch_type == 'stop':
                date = None
                interval = None
                stop = data_recv[2]
            instance_id = data_recv[3]
            watch = Watch.objects.get(pk=instance_id)
            job = watch.job.job
            agent = watch.job.agent
            hosts = open('/tmp/openbach_hosts', 'w')
            hosts.write("[Agents]\n" + agent.address + "\n")
            hosts.close()
            playbook_filename = self.playbook_builder.path_to_build + "status_"
            playbook_filename += job.name + ".yml"
            playbook = open(playbook_filename, 'w')
            extra_vars = open('/tmp/openbach_extra_vars', 'w')
            playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
            self.playbook_builder.build_status(playbook, job.name, instance_id,
                                               date, interval, stop, extra_vars)
            playbook.close()
            extra_vars.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e "
            cmd_ansible += "@/tmp/openbach_extra_vars -e "
            cmd_ansible += "ansible_ssh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            if not self.launch_playbook(cmd_ansible):
                return
        elif request_type == 'status_agents':
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
                    playbook_filename += "status_agent.yml"
                    try:
                        subprocess.check_output(["ping", "-c1", "-w2",
                                                 agent.address])
                        returncode = 0
                    except subprocess.CalledProcessError, e:
                        returncode = e.returncode
                    if returncode != 0:
                        agent.reachable = False
                        agent.update_reachable = timezone.now()
                        agent.status = "Agent unreachable"
                        agent.update_status= timezone.now()
                        agent.save()
                        continue
                    playbook = open(playbook_filename, 'w')
                    playbook.write("---\n\n- hosts: Agents\n\n")
                    playbook.close()
                    cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansib"
                    cmd_ansible += "le_ssh_user=" + agent.username + " -e "
                    cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
                    cmd_ansible += playbook_filename
                    p = subprocess.Popen(cmd_ansible, shell=True)
                    p.wait()
                    if p.returncode != 0:
                        agent.reachable = False
                        agent.update_reachable = timezone.now()
                        agent.status = "Agent reachable but connection impossible"
                        agent.update_status= timezone.now()
                        agent.save()
                        continue
                    agent.reachable = True
                    agent.update_reachable = timezone.now()
                    agent.save()
                    playbook = open(playbook_filename, 'w')
                    playbook.write("---\n\n- hosts: Agents\n  tasks:\n")
                    self.playbook_builder.build_status_agent(playbook) 
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
        elif request_type == 'update_agent':
            agent_ip = data_recv[1]
            agent = Agent.objects.get(pk=agent_ip)
            url = "http://" + agent.collector + ":8086/query?db=openbach&epoch="
            url += "ms&q=SELECT+last(\"status\")+FROM+\"" + agent.name + "\""
            r = requests.get(url)
            if 'series' not in r.json()['results'][0]:
                self.clientsocket.send("KO " + r.json()['results'][0]['error'])
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
            url = "http://" + agent.collector + ":8086/query?db=openbach&epoch="
            url += "ms&q=SELECT+last(\"jobs_list\")+FROM+\"" + agent.name + "\""
            r = requests.get(url)
            if 'series' not in r.json()['results'][0]:
                self.clientsocket.send("KO 1 " + r.json()['results'][0]['error'])
                self.clientsocket.close()
                return
            columns = r.json()['results'][0]['series'][0]['columns']
            for i in range(len(columns)):
                if columns[i] == 'time':
                    timestamp = r.json()['results'][0]['series'][0]['values'][0][i]/1000.
                elif columns[i] == 'last':
                    jobs_list = r.json()['results'][0]['series'][0]['values'][0][i].split()
            date = datetime.fromtimestamp(timestamp,
                                          timezone.get_current_timezone())
            installed_jobs = agent.installed_job_set
            for job in installed_jobs.iterator():
                job.delete()
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
            self.playbook_builder.build_enable_stats(playbook,
                                                     rstats_filter_filename,
                                                     job_name, instance_id)
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
 
        self.clientsocket.send('OK')
        self.clientsocket.close()
    

if __name__ == "__main__":
    # Ouverture de la socket d'ecoute
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpsock.bind(("",1113))
    
    while True:
        num_connexion_max = 10
        tcpsock.listen(num_connexion_max)
        (clientsocket, (ip, port)) = tcpsock.accept()
        newthread = ClientThread(clientsocket)
        newthread.start()

