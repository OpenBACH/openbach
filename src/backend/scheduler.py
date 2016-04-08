#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
scheduler.py - <+description+>
"""

import socket
import shlex
import threading
from apscheduler.schedulers.background import BackgroundScheduler
import os
import subprocess
import getpass
from django.core.wsgi import get_wsgi_application
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
application = get_wsgi_application()
from conductor.models import Agent, Job, Instance

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
        playbook.write(self.path_src + "start_job.yml\n")
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
        playbook.write(self.path_src + "status_job.yml\n")
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
        playbook.write(self.path_src + "restart_job.yml\n")
        return True

    def build_stop(self, playbook, job_name, instance_id, date):
        playbook.write("- hosts: Agents\n  vars:\n    - job_name: ")
        playbook.write(job_name + "\n    - id: " + instance_id + "\n    - date")
        playbook.write(": date " + date + "\n\n  tasks:\n    - include: ")
        playbook.write(self.path_src + "stop_job.yml\n")
        return True

class ClientThread(threading.Thread):
    def __init__(self, clientsocket, scheduler):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.scheduler = scheduler
        self.playbook_builder = PlaybookBuilder("/tmp/",
                                                "/opt/openbach/roles/backend/tasks/")

    def check_date_interval(self, data_recv):
        request_type = data_recv[0]
        only_date = ['add_agent', 'del_agent', 'install_job', 'uninstall_job',
                     'stop_job']
        date_interval = ['start_job', 'restart_job', 'status_job']
        if request_type in only_date:
            if len(data_recv) < 2:
                error_msg = "KO Message not formed well. You should provide a "
                error_msg += "date when to execute the order"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return False
        elif request_type in date_interval:
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide a "
                error_msg += "date or an interval in order to execute the order"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return False
        else:
            error_msg = "KO Message not formed well. Request not knwown"
            print(error_msg)
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return False
        return True

    def parse_and_check(self, r):
        data_recv = shlex.split(r)
        if len(data_recv) < 1:
            error_msg = "KO Message not formed well. You should provide a "
            error_msg += "request"
            print(error_msg)
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return []
        if not self.check_date_interval(data_recv):
            return []
        #for i in range(len(data_recv)):
        #    data_recv[i] = data_recv[i]
        request_type = data_recv[0]
        if request_type == 'add_agent' or request_type == 'del_agent':
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide the"
                error_msg += " ip address of the agent"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 3:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'install_job' or request_type == 'uninstall_job':
            if len(data_recv) < 4:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the ip address of the agent and the name of the job"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 4:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'start_job' or request_type == 'restart_job':
            if len(data_recv) < 4:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the id of the instance"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 4:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        elif request_type == 'stop_job':
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. You should provide "
                error_msg += "the id of the instance"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
            if len(data_recv) > 3:
                error_msg = "KO Message not formed well. Too much arguments"
                error_msg += " given"
                print(error_msg)
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                return []
        else:
            error_msg = "KO Request type not defined"
            print(error_msg)
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            return []
        return data_recv
            
    
    def run(self): 
        r = self.clientsocket.recv(2048)
        print r

        data_recv = self.parse_and_check(r)
        if len(data_recv) == 0:
            return
        request_type = data_recv[0]
        if request_type == 'add_agent':
            date = data_recv[1]
            agent_ip = data_recv[2]
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
            print(cmd_ansible)
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'del_agent':
            date = data_recv[1]
            agent_ip = data_recv[2]
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
            print(cmd_ansible)
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'install_job':
            date = data_recv[1]
            agent_ip = data_recv[2]
            job_name = data_recv[3]
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
            print cmd_ansible
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'uninstall_job':
            date = data_recv[1]
            agent_ip = data_recv[2]
            job_name = data_recv[3]
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
            print cmd_ansible
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'start_job':
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
            cmd_ansible += "sh_user=" + agent.username + " " + playbook_filename
            print cmd_ansible
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'stop_job':
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
            cmd_ansible += "sh_user=" + agent.username + " " + playbook_filename
            print cmd_ansible
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
        elif request_type == 'restart_job':
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
            cmd_ansible += "sh_user=" + agent.username + " " + playbook_filename
            print cmd_ansible
            p = subprocess.Popen(cmd_ansible, shell=True)
            p.wait()
            if p.returncode != 0:
                self.clientsocket.send('KO')
                self.clientsocket.close()
                return
 
        self.clientsocket.send('OK')
        self.clientsocket.close()
    

if __name__ == "__main__":
    # Ouverture de la socket d'ecoute
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpsock.bind(("",1113))
    
    # Creation du scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    while True:
        num_connexion_max = 10
        tcpsock.listen(num_connexion_max)
        (clientsocket, (ip, port)) = tcpsock.accept()
        newthread = ClientThread(clientsocket, scheduler)
        newthread.start()

