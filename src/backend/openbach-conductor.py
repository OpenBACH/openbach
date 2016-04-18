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

class PlaybookBuilder():
    def __init__(self, path_to_build, path_src):
        self.path_to_build = path_to_build
        self.path_src = path_src

    def build_start(self, playbook, job_name, instance_id, job_args, date,
                    interval):
        playbook.write("- hosts: Agents\n  vars:\n    - job_name: ")
        playbook.write(job_name + "\n    - id: " + instance_id + "\n    - job_")
        playbook.write("options: " + job_args + "\n    - date_interval: ")
        if date != None:
            playbook.write("date " + date + "\n\n  tasks:\n    - include: ")
        elif interval != None:
            playbook.write("interval " + interval + "\n\n  tasks:\n    -")
            playbook.write(" include: ")
        else:
            return False
        playbook.write(self.path_src + "start_instance.yml\n")
        return True

    def build_status(self, playbook, job_name, instance_id, date, interval,
                     stop):
        playbook.write("- hosts: Agents\n  vars:\n    - job_name: ")
        playbook.write(job_name + "\n    - id: " + instance_id + "\n    - date")
        playbook.write("_interval_stop: ")
        if date != None:
            playbook.write("date " + date + "\n\n  tasks:\n    - include: ")
        elif interval != None:
            playbook.write("interval " + interval + "\n\n  tasks:\n    -")
            playbook.write(" include: ")
        elif stop != None:
            playbook.write("stop " + stop + "\n\n  tasks:\n    - include: ")
        else:
            return False
        playbook.write(self.path_src + "status_instance.yml\n")
        return True

    def build_restart(self, playbook, job_name, instance_id, job_args, date,
                      interval):
        playbook.write("- hosts: Agents\n  vars:\n    - job_name: ")
        playbook.write(job_name + "\n    - id: " + instance_id + "\n    - job_")
        playbook.write("options: " + job_args + "\n    - date_interval: ")
        if date != None:
            playbook.write("date " + date + "\n\n  tasks:\n    - include: ")
        elif interval != None:
            playbook.write("interval " + interval + "\n\n  tasks:\n    -")
            playbook.write(" include: ")
        else:
            return False
        playbook.write(self.path_src + "restart_instance.yml\n")
        return True

    def build_stop(self, playbook, job_name, instance_id, date):
        playbook.write("- hosts: Agents\n  vars:\n    - job_name: ")
        playbook.write(job_name + "\n    - id: " + instance_id + "\n    - date")
        playbook.write(": date " + date + "\n\n  tasks:\n    - include: ")
        playbook.write(self.path_src + "stop_instance.yml\n")
        return True

    def build_status_agent(self, playbook):
        playbook.write("- hosts: Agents\n  tasks:\n    - name: Get status of")
        playbook.write("openbach-agent\n      shell: /etc/init.d/openbach-agen")
        playbook.write("t status\n")
        return True
    
    def build_ls_jobs(self, playbook):
        playbook.write("- hosts: Agents\n  tasks:\n    - name: Get the list of")
        playbook.write("the installed jobs\n      shell: /opt/openbach-agent/o")
        playbook.write("penbach-baton ls_jobs\n")
        return True

class ClientThread(threading.Thread):
    def __init__(self, clientsocket):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.playbook_builder = PlaybookBuilder("/tmp/",
                                                "/opt/openbach/roles/backend/tasks/")

    def check_date_interval(self, data_recv):
        request_type = data_recv[0]
        no_date = ['add_agent', 'del_agent', 'install_job', 'uninstall_job',
                   'status_agents', 'update_agent', 'status_jobs',
                   'update_jobs']
        only_date = ['stop_instance']
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
        elif request_type == 'stop_instance':
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
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            playbook.write("---\n\n")
            self.playbook_builder.build_start(playbook, job.name, instance_id,
                                              instance.args, date, interval)
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansible_s"
            cmd_ansible += "sh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            playbook.write("---\n\n")
            self.playbook_builder.build_stop(playbook, job.name, instance_id,
                                             date)
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansible_s"
            cmd_ansible += "sh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            playbook.write("---\n\n")
            self.playbook_builder.build_restart(playbook, job.name, instance_id,
                                                instance.args, date, interval)
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansible_s"
            cmd_ansible += "sh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
            playbook.write("---\n\n")
            self.playbook_builder.build_status(playbook, job.name, instance_id,
                                               date, interval, stop)
            playbook.close()
            cmd_ansible = "ansible-playbook -i /tmp/openbach_hosts -e ansible_s"
            cmd_ansible += "sh_user=" + agent.username + " -e "
            cmd_ansible += "ansible_sudo_pass=" + agent.password + " -e "
            cmd_ansible += "ansible_ssh_pass=" + agent.password + " "
            cmd_ansible += playbook_filename
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
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
                        agent.reachable = "Agent unreachable"
                        agent.update_reachable = timezone.now()
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
                        continue
                    agent.reachable = "Agent reachable"
                    agent.update_reachable = timezone.now()
                    agent.save()
                    playbook = open(playbook_filename, 'w')
                    playbook.write("---\n\n")
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
                    playbook.write("---\n\n")
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
                installed_job.update_status = timezone.now()
                installed_job.save()
            if error_msg != 'KO 2':
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
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

