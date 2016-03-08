#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
openbach-agent.py - <+description+>
"""

import socket
import threading
import syslog
import os
import sys
import errno
import time
import signal
import ConfigParser
from datetime import datetime
from ConfigParser import NoSectionError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError



def signal_term_handler(signal, frame):
    global dict_jobs
    global mutex_jobs
    global scheduler
    mutex_jobs.acquire()
    for job_name in dict_jobs.keys():
        try:
            scheduler.remove_job(job_name)
        except JobLookupError:
            pass
        if dict_jobs[job_name]['status']:
            scheduler.add_job(stop_job, 'date', args=[job_name])
    mutex_jobs.release()
    time.sleep(10)
    sys.exit(0)
                 
signal.signal(signal.SIGHUP, signal_term_handler)
                 


# TODO Syslog bug : seulement le 1er log est envoyé, les autres sont ignoré
# Configure logger
syslog.openlog("openbach-agent", syslog.LOG_PID, syslog.LOG_USER)


def launch_job(job_name, command, args):
    cmd = "PID=`" + command + " " + args + "> /dev/null 2>&1 & echo $!`; echo"
    cmd += " $PID > /var/run/" + job_name + ".pid"
    os.system(cmd)
    
def stop_job(job_name):
    cmd = "PID=`cat /var/run/" + job_name + ".pid`; kill -HUP $PID; rm "
    cmd += "/var/run/" + job_name + ".pid"
    os.system(cmd)

def status_job(job_name):
    # Récupération du status
    timestamp = int(round(time.time() * 1000))
    try:
        pid_file = open("/var/run/" + job_name + ".pid", 'r')
        pid = int(pid_file.readline())
        if os.path.exists("/proc/" + str(pid)):
            status = "Running"
        else:
            status = "Not_Running"
        pid_file.close()
    except (IOError, ValueError):
        status = "Not_Running"
    
    # Construction du nom de la stat
    f = open("/etc/hostname", "r")
    stat_name = f.readline().split('\n')[0]
    f.close()
    stat_name += "." + job_name
    
    # Envoie de la stat à Rstats
    # Connexion au service de collecte de l'agent
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("", 1111))
    except socket.error as serr:
        if serr.errno == errno.ECONNREFUSED:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Connexion to rstats refused, maybe rstats service isn't started")
        raise serr
    s.send("1 /opt/openbach-agent/openbach-agent_filter.conf")
    r = s.recv(9999)
    s.close()
    data = r.split(" ")
    if data[0] == 'OK':
        if len(data) != 2:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            quit()
        try:
            int(data[1])
        except:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            quit()
        connection_id = data[1]
        syslog.syslog(syslog.LOG_NOTICE, "NOTICE: Identifiant de connexion = " + connection_id)
    elif data[0] == 'KO':
        syslog.syslog(syslog.LOG_ERR, "ERROR: Something went wrong :")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
        quit()
    else:
        syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
        quit()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("", 1111))
    cmd = "2 " + connection_id + " " + stat_name + " " + str(timestamp) + " status "
    cmd += status
    s.send(cmd)
    s.close()
    
    
class Conf:
    def __init__(self, job_name, confpath="config.ini"):
        Config = ConfigParser.ConfigParser()
        Config.read(confpath)
        self.command = Config.get(job_name, 'command')
        self.required = Config.get(job_name, 'required')
        self.optional = Config.get(job_name, 'optional')
 

class ClientThread(threading.Thread):
    def __init__(self, clientsocket, scheduler):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.scheduler = scheduler
        
    def start_job(self, mutex_job, dict_jobs, data_recv):
        job_name = data_recv[1]
        mutex_jobs.acquire()
        command = dict_jobs[job_name]['command']
        mutex_jobs.release()
        args = ' '.join(data_recv[4:])
        actual_timestamp = int(round(time.time() * 1000))
        if data_recv[2] == 'date':
            if data_recv[3] < actual_timestamp:
                date = None
            else:
                date = datetime.fromtimestamp(data_recv[3])
            self.scheduler.add_job(launch_job, 'date', run_date=date,
                                   args=[job_name, command, args],
                                   id=job_name)
            mutex_jobs.acquire()
            dict_jobs[job_name]['status'] = True
            mutex_jobs.release()
        elif data_recv[2] == 'interval':
            interval = data_recv[3]
            self.scheduler.add_job(launch_job, 'interval', seconds=interval,
                                   args=[job_name, command, args],
                                   id=job_name)
            mutex_jobs.acquire()
            dict_jobs[job_name]['status'] = True
            mutex_jobs.release()
        self.clientsocket.send("OK")
        self.clientsocket.close()

        
    def parse_and_check(self, r):
        global dict_jobs
        global mutex_jobs
        data_recv = r.split()
        # Récupération du type de la requete et du nom du job
        if len(data_recv) < 2:
            error_msg = "KO Message not formed well. It should have an action"
            error_msg += "and a job name (with eventually options)"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            syslog.syslog(syslog.LOG_ERR, error_msg)
            return []
        request_type = data_recv[0]
        job_name = data_recv[1]
        if request_type == 'install':
            # On vérifie si le job est déjà installé
            mutex_jobs.acquire()
            if job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "KO A job " + job_name + " is already installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            mutex_jobs.release()
            # On vérifie qu'il y a un 3eme argument (le fichier de conf)
            if len(data_recv) < 3:
                error_msg = "KO Message not formed well. To perform an install,"
                error_msg += " you should provide a configuration file"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            elif len(data_recv) > 3:
                error_msg = "KO Message not formed well. To perform an install,"
                error_msg += " you should only provide a configuration file"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            try:
                conf = Conf(job_name, data_recv[2])
            except NoSectionError:
                error_msg = "KO Conf files for job " + job_name + " isn't formed well"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            data_recv[2] = conf.command
            if conf.required == '':
                data_recv.append(False)
            else:
                data_recv.append(conf.required)
            data_recv.append(conf.optional)
        elif request_type == 'uninstall':
            # On vérifie que le job soit bien installé
            mutex_jobs.acquire()
            if not job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "OK No job " + job_name + " is installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            mutex_jobs.release()
            # On vérifie qu'il n'y ait pas d'arguments indésirables
            if len(data_recv) != 2:
                error_msg = "KO Message not formed well. For uninstall"
                error_msg += ", no more arguments are needed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        elif request_type == 'status':
            # On vérifie que le job soit bien installé
            mutex_jobs.acquire()
            if not job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "KO No job " + job_name + " is installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            mutex_jobs.release()
            # On vérifie que le message soit bien formé
            if len(data_recv) < 3:
                error_msg = "KO To get a status, start or stop a watch you have"
                error_msg += " to tell it ('date', 'interval' or 'stop')"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date ou l'interval
            if data_recv[2] == 'date':
                if len(data_recv) != 4:
                    error_msg = "KO To get a status, you have"
                    error_msg += " to specify when"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                if data_recv[3] == 'now':
                    data_recv[3] = 0
                try:
                    int(data_recv[3])
                except:
                    error_msg = "KO The date to watch the status should be give"
                    error_msg += " as timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[3] = int(data_recv[3])
            elif data_recv[2] == 'interval':
                if len(data_recv) != 4:
                    error_msg = "KO To start a watch, you have"
                    error_msg += " to specify the interval"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                try:
                    int(data_recv[3])
                except:
                    error_msg = "KO The interval to execute the job should be"
                    error_msg +=  " give in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[3] = int(data_recv[3])
            elif data_recv[2] == 'stop':
                # S'assurer qu'il n'y a pas d'autres arguments
                if len(data_recv) != 3:
                    error_msg = "KO To stop a watch, you don't have to"
                    error_msg += " specify anything"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
            else:
                # TODO Gérer le 'cron' ?
                error_msg = "KO Only 'date', 'interval' and 'stop' are allowed "
                error_msg += "with the 'status' action"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        elif request_type == 'start' or request_type == 'restart':
            # On vérifie que le job soit bien installé
            mutex_jobs.acquire()
            if not job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "KO No job " + job_name + " is installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il n'est pas déjà demarré
            job = dict_jobs[job_name]
            mutex_jobs.release()
            if job['status']:
                error_msg = "KO job " + job_name + " is already started"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date ou l'interval
            if data_recv[2] == 'date':
                if data_recv[3] == 'now':
                    data_recv[3] = 0
                try:
                    int(data_recv[3])
                except:
                    error_msg = "KO The date to begin should be give as"
                    error_msg += "timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[3] = int(data_recv[3])
            elif data_recv[2] == 'interval':
                try:
                    int(data_recv[3])
                except:
                    error_msg = "KO The interval to execute the job should be"
                    error_msg +=  " give in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[3] = int(data_recv[3])
            else:
                # TODO Gérer le 'cron' ?
                error_msg = "KO Only 'date' and 'interval' are allowed to "
                error_msg += "specify when execute the job"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il au moins autant d'arguments qu'exigé (+ la date
            # à laquelle il faut executer le job)
            if not job['required']:
                nb_args = 0
            else:
                nb_args = len(job['required'])
            if len(data_recv) < nb_args + 4:
                error_msg = "KO job " + job_name + " required at least "
                error_msg += str(len(job['required'])) + " arguments"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        elif request_type == 'stop':
            # On vérifie que le job soit bien installé
            mutex_jobs.acquire()
            if not job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "KO No job " + job_name + " is installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il n'est pas déjà stoppé
            job = dict_jobs[job_name]
            mutex_jobs.release()
            if not job['status']:
                error_msg = "KO job " + job_name + " is already stopped"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il y a autant d'arguments qu'exigé
            # (la date à laquelle il faut stopper le job)
            if len(data_recv) < 4:
                error_msg = "KO To stop a job you have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            elif len(data_recv) > 4:
                error_msg = "KO To stop a job you just have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date
            if data_recv[2] == 'date':
                if data_recv[3] == 'now':
                    data_recv[3] = 0
                try:
                    int(data_recv[3])
                except:
                    error_msg = "KO The date to stop should be give as"
                    error_msg += "timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[3] = int(data_recv[3])
            else:
                error_msg = "KO To stop a job you have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        else:
            error_msg = "KO Action not recognize. Actions possibles are : "
            error_msg += "install uninstall status start stop"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            syslog.syslog(syslog.LOG_ERR, error_msg)
            return []
        return data_recv
            

    def run(self): 
        global dict_jobs
        global mutex_jobs
        r = self.clientsocket.recv(2048)

        data_recv = self.parse_and_check(r)
        if len(data_recv) == 0:
            return
        request_type = data_recv[0]
        job_name = data_recv[1]
        if request_type == 'install':
            # TODO Vérifié que l'appli a bien été installé ?
            mutex_jobs.acquire()
            if not data_recv[3]:
                dict_jobs[job_name] = dict(command=data_recv[2],
                                           required=data_recv[3],
                                           optional=bool(data_recv[4]),
                                           status=False)
            else:
                dict_jobs[job_name] = dict(command=data_recv[2],
                                           required=str(data_recv[3]).split(' '),
                                           optional=bool(data_recv[4]),
                                           status=False)
            mutex_jobs.release()
            self.clientsocket.send("OK")
            self.clientsocket.close()
        elif request_type == 'uninstall':
            # On vérifie si le job n'est pas en train de tourner
            mutex_jobs.acquire()
            if dict_jobs[job_name]['status']:
                self.scheduler.add_job(stop_job, 'date', args=[job_name])
            mutex_jobs.release()
            # TODO Vérifié que l'appli a bien été déinstallé ?
            mutex_jobs.acquire()
            del dict_jobs[job_name]
            mutex_jobs.release()
            self.clientsocket.send("OK")
            self.clientsocket.close()
        elif request_type == 'start':
            self.start_job(mutex_jobs, dict_jobs, data_recv)
        elif request_type == 'stop':
            actual_timestamp = int(round(time.time() * 1000))
            if data_recv[3] < actual_timestamp:
                date = None
            else:
                date = datetime.fromtimestamp(data_recv[3])
            self.scheduler.add_job(stop_job, 'date', run_date=date,
                                   args=[job_name])
            mutex_jobs.acquire()
            dict_jobs[job_name]['status'] = False
            mutex_jobs.release()
            try:
                self.scheduler.remove_job(job_name)
            except JobLookupError:
                pass
            self.clientsocket.send("OK")
            self.clientsocket.close()
        elif request_type == 'status':
            # Récupérer le status actuel
            if data_recv[2] == 'date':
                actual_timestamp = int(round(time.time() * 1000))
                if data_recv[3] < actual_timestamp:
                    date = None
                else:
                    date = datetime.fromtimestamp(data_recv[3])
                self.scheduler.add_job(status_job, 'date', run_date=date,
                                       args=[job_name], id=job_name + "_status")
            # Programmer de regarder le status régulièrement
            elif data_recv[2] == 'interval':
                interval = data_recv[3]
                self.scheduler.add_job(status_job, 'interval', seconds=interval,
                                       args=[job_name], id=job_name + "_status")
            # Déprogrammer
            elif data_recv[2] == 'stop':
                try:
                    self.scheduler.remove_job(job_name + "_status")
                except JobLookupError:
                    self.clientsocket.send("KO No watch on the status of " +
                                           job_name + " was programmed")
                    self.clientsocket.close()
                    return
            self.clientsocket.send("OK")
            self.clientsocket.close()
        elif request_type == 'restart':
            # Stop le job si il est lancer
            mutex_jobs.acquire()
            if dict_jobs[job_name]['status']:
                self.scheduler.add_job(stop_job, 'date', args=[job_name])
            mutex_jobs.release()
            # Le relancer avec les nouveaux arguments (éventuellement les mêmes)
            self.start_job(mutex_jobs, dict_jobs, data_recv)



if __name__ == "__main__":
    # Ouverture de la socket d'ecoute
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpsock.bind(("",1112))

    # Creation du scheduler
    global scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    # Liste de job disponible (+ son mutex)
    global dict_jobs
    global mutex_jobs
    dict_jobs = {}
    mutex_jobs = threading.Lock()

    while True:
        num_connexion_max = 10
        tcpsock.listen(num_connexion_max)
        (clientsocket, (ip, port)) = tcpsock.accept()
        newthread = ClientThread(clientsocket, scheduler)
        newthread.start()

