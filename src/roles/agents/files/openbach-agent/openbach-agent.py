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
from ConfigParser import NoSectionError, MissingSectionHeaderError, NoOptionError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError, ConflictingIdError
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.util import datetime_repr
import subprocess
import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))



def signal_term_handler(signal, frame):
    global dict_jobs
    global mutex_jobs
    global scheduler
    scheduler.remove_all_jobs()
    mutex_jobs.acquire()
    for (job_name, job) in dict_jobs.iteritems():
        if len(job['set_id']) != 0:
            for instance_id in job['set_id']:
                scheduler.add_job(stop_job, 'date', args=[job_name,
                                                          instance_id])
    mutex_jobs.release()
    while len(scheduler.get_jobs()) != 0:
        time.sleep(0.5)
    scheduler.shutdown()
    sys.exit(0)
                 
signal.signal(signal.SIGHUP, signal_term_handler)
                 


# TODO Syslog bug : seulement le 1er log est envoyé, les autres sont ignoré
# Configure logger
syslog.openlog("openbach-agent", syslog.LOG_PID, syslog.LOG_USER)


def launch_job(job_name, instance_id, command, args):
    cmd = "PID=`" + command + " " + args + " > /dev/null 2>&1 & echo $!`; echo"
    cmd += " $PID > /var/run/" + job_name + instance_id + ".pid"
    os.system(cmd)
    
def stop_job(job_name, instance_id):
    cmd = "PID=`cat /var/run/" + job_name + instance_id + ".pid`; pkill -TERM -P"
    cmd += "$PID; kill -TERM $PID; rm"
    cmd += " /var/run/" + job_name + instance_id + ".pid"
    os.system(cmd)
    
def status_job(job_name, instance_id, scheduler):
    # Récupération du status
    timestamp = int(round(time.time() * 1000))
    job = scheduler.get_job(job_name + instance_id)
    if job == None:
        try:
            pid_file = open("/var/run/" + job_name + instance_id + ".pid", 'r')
            pid = int(pid_file.readline())
            pid_file.close()
            if os.path.exists("/proc/" + str(pid)):
                status = "Running"
            else:
                status = "\"Not Running\""
                cmd = "rm /var/run/" + job_name + instance_id + ".pid"
                os.system(cmd)
        except (IOError, ValueError):
            status = "\"Not Running\""
    else:
        status = "\"Programmed "
        if type(job.trigger) == DateTrigger:
            status += "on " + datetime_repr(job.trigger.run_date) + "\""
        elif type(job.trigger) == IntervalTrigger:
            status += "every " + str(job.trigger.interval_length) + " seconds\""
        else:
            # Attention : Potentiellement ça peut être du CronTrigger
            # mais on ne l'utilise pas pour le moment
            pass
    
    # Construction du nom de la stat
    f = open("/etc/hostname", "r")
    stat_name = f.readline().split('\n')[0]
    f.close()
    stat_name += "." + job_name + instance_id
    
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
    
def stop_watch(scheduler, job_name, instance_id):
    try:
        scheduler.remove_job(job_name + instance_id + "_status")
    except JobLookupError:
        pass
 
def ls_jobs():
    global dict_jobs
    global mutex_jobs
    
    # Récupération des jobs disponibles
    timestamp = int(round(time.time() * 1000))
    mutex_jobs.acquire()
    jobs = ''
    for job_name in dict_jobs.keys():
        if jobs != '':
            jobs += ' '
        jobs += job_name
    mutex_jobs.release()
    
    # Construction du nom de la stat
    f = open("/etc/hostname", "r")
    stat_name = f.readline().split('\n')[0]
    f.close()
    
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
    cmd = "2 " + connection_id + " " + stat_name + " " + str(timestamp)
    cmd += " jobs_list \"" + jobs + "\""
    s.send(cmd)
    s.close()
    
    
class Conf:
    def __init__(self, job_name, confpath):
        conffile = confpath + job_name + '.cfg'
        Config = ConfigParser.ConfigParser()
        Config.read(conffile)
        self.command = Config.get(job_name, 'command')
        self.required = Config.get(job_name, 'required')
        self.optional = Config.get(job_name, 'optional')
        self.persistent = Config.get(job_name, 'persistent')
 

class ClientThread(threading.Thread):
    def __init__(self, clientsocket, scheduler, path):
        threading.Thread.__init__(self)
        self.clientsocket = clientsocket
        self.scheduler = scheduler
        self.path = path
        
    def start_job(self, mutex_job, dict_jobs, data_recv):
        job_name = data_recv[1]
        instance_id = data_recv[2]
        mutex_jobs.acquire()
        command = dict_jobs[job_name]['command']
        mutex_jobs.release()
        args = ' '.join(data_recv[5:])
        actual_timestamp = time.time()
        if data_recv[3] == 'date':
            if data_recv[4] < actual_timestamp:
                date = None
            else:
                try:
                    date = datetime.fromtimestamp(data_recv[4])
                except:
                    date = None
            try:
                self.scheduler.add_job(launch_job, 'date', run_date=date,
                                       args=[job_name, instance_id, command, args],
                                       id=job_name + instance_id)
            except ConflictingIdError:
                error_msg = "KO A job " + job_name + " is already programmed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return False
            mutex_jobs.acquire()
            if dict_jobs[job_name]['persistent']:
                dict_jobs[job_name]['set_id'].add(instance_id)
            mutex_jobs.release()
        elif data_recv[3] == 'interval':
            if dict_jobs[job_name]['persistent']:
                error_msg = "KO This job " + job_name + " is persistent, you"
                error_msg += "can't start it with the 'interval' option"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return False
            interval = data_recv[4]
            try:
                self.scheduler.add_job(launch_job, 'interval', seconds=interval,
                                       args=[job_name, instance_id, command, args],
                                       id=job_name + instance_id)
            except ConflictingIdError:
                error_msg = "KO An instance " + job_name + "with the id "
                error_msg += instance_id + " is already programmed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return False
            mutex_jobs.acquire()
            dict_jobs[job_name]['set_id'].add(instance_id)
            mutex_jobs.release()
        else:
            pass
        return True

        
    def parse_and_check(self, r):
        global dict_jobs
        global mutex_jobs
        data_recv = r.split()
        # Récupération du type de la requete et du nom du job
        if len(data_recv) < 1:
            error_msg = "KO Message not formed well. It should have at least an"
            error_msg += " action"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            syslog.syslog(syslog.LOG_ERR, error_msg)
            return []
        request_type = data_recv[0]
        if len(data_recv) < 2 and request_type != 'ls_jobs':
            error_msg = "KO Message not formed well. It should have an action "
            error_msg += "and a job name (with eventually options)"
            self.clientsocket.send(error_msg)
            self.clientsocket.close()
            syslog.syslog(syslog.LOG_ERR, error_msg)
            return []
        elif request_type != 'ls_jobs':
            job_name = data_recv[1]
        if request_type == 'add':
            # On vérifie si le job est déjà installé
            mutex_jobs.acquire()
            if job_name in dict_jobs:
                mutex_jobs.release()
                error_msg = "OK A job " + job_name + " is already installed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            mutex_jobs.release()
            # On vérifie qu'il n'y ai pas d'autre argument
            if len(data_recv) > 2:
                error_msg = "KO Message not formed well. To add a job,"
                error_msg += " you should only provide the job name"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie que ce fichier de conf contient tout ce qu'il faut
            try:
                conf = Conf(job_name, self.path)
            except (NoSectionError, MissingSectionHeaderError, NoOptionError):
                error_msg = "KO Conf files for job " + job_name + " isn't formed well"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            data_recv.append(conf.command)
            if conf.required == '':
                data_recv.append(False)
            else:
                data_recv.append(conf.required)
            if conf.optional == 'True' or conf.optional == 'true':
                data_recv.append(True)
            elif conf.optional == 'False' or conf.optional == 'false':
                data_recv.append(False)
            else:
                error_msg = "KO Conf 'optional' for job " + job_name + " should"
                error_msg += "be a boolean"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            if conf.persistent == 'True' or conf.persistent == 'true':
                data_recv.append(True)
            elif conf.persistent == 'False' or conf.persistent == 'false':
                data_recv.append(False)
            else:
                error_msg = "KO Conf 'persistent' for job " + job_name + " should"
                error_msg += "be a boolean"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        elif request_type == 'del':
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
                error_msg = "KO Message not formed well. To delete"
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
            # On vérifie que l'instance_id est donné
            if len(data_recv) < 3:
                error_msg = "KO To start or restart a job, you should provide an "
                error_msg += "instance_id (to be able to get the status or stop the job)"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            instance_id = data_recv[2]
            # On vérifie que le message soit bien formé
            if len(data_recv) < 4:
                error_msg = "KO To get a status, start or stop a watch you have"
                error_msg += " to tell it ('date', 'interval' or 'stop')"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date ou l'interval
            if data_recv[3] == 'date':
                if len(data_recv) != 5:
                    error_msg = "KO To get a status, you have"
                    error_msg += " to specify when"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                if data_recv[4] == 'now':
                    data_recv[4] = 0
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The date to watch the status should be give"
                    error_msg += " as timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])/1000.
            elif data_recv[3] == 'interval':
                if len(data_recv) != 5:
                    error_msg = "KO To start a watch, you have"
                    error_msg += " to specify the interval"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The interval to execute the job should be"
                    error_msg +=  " give in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])
            elif data_recv[3] == 'stop':
                if len(data_recv) != 5:
                    error_msg = "KO To stop a watch, you have to"
                    error_msg += " specify when"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                if data_recv[4] == 'now':
                    data_recv[4] = 0
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The date to watch the status should be give"
                    error_msg += " as timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])/1000.
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
            # On vérifie que l'instance_id est donné
            if len(data_recv) < 3:
                error_msg = "KO To start or restart a job, you should provide an "
                error_msg += "instance_id (to be able to get the status or stop the job)"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            instance_id = data_recv[2]
            # On vérifie si il n'est pas déjà demarré (seulement dans le cas
            # 'start')
            job = dict_jobs[job_name]
            mutex_jobs.release()
            if request_type == 'start':
                if instance_id in job['set_id']:
                    error_msg = "KO instance " + job_name + "with id " + instance_id
                    error_msg += " is already started"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
            # On vérifie que la date ou l'intervalle est donné
            if len(data_recv) < 5:
                error_msg = "KO To start or restart an instance, you should "
                error_msg += "provide a date or an interval"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date ou l'interval
            if data_recv[3] == 'date':
                if data_recv[4] == 'now':
                    data_recv[4] = 0
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The date to begin should be give as"
                    error_msg += "timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])/1000.
            elif data_recv[3] == 'interval':
                if dict_jobs[job_name]['persistent']:
                    error_msg = "KO You can only start a watch on jobs that are"
                    error_msg += " not persistent"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The interval to execute the job should be"
                    error_msg +=  " give in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])
            else:
                # TODO Gérer le 'cron' ?
                error_msg = "KO Only 'date' and 'interval' are allowed to "
                error_msg += "specify when execute the job"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il au moins autant d'arguments qu'exigé pour lancer
            # la commande
            if not job['required']:
                nb_args = 0
            else:
                nb_args = len(job['required'])
            if len(data_recv) < nb_args + 5:
                error_msg = "KO job " + job_name + " required at least "
                error_msg += str(len(job['required'])) + " arguments"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifié qu'il n'y ait pas trop d'arguments
            if (not job['optional']) and len(data_recv) > nb_args + 5:
                error_msg = "KO job " + job_name + " doesn't require more "
                error_msg += "than " + str(len(job['required'])) + " arguments"
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
            mutex_jobs.release()
            # On vérifie que l'instance_id est donné
            if len(data_recv) < 3:
                error_msg = "KO To stop a job, you should provide it instance_id"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On vérifie si il y a autant d'arguments qu'exigé
            # (la date à laquelle il faut stopper le job)
            if len(data_recv) < 5:
                error_msg = "KO To stop a job you have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            elif len(data_recv) > 5:
                error_msg = "KO To stop a job you just have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
            # On récupère la date
            if data_recv[3] == 'date':
                if data_recv[4] == 'now':
                    data_recv[4] = 0
                try:
                    int(data_recv[4])
                except:
                    error_msg = "KO The date to stop should be give as"
                    error_msg += "timestamp in sec "
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return []
                data_recv[4] = int(data_recv[4])/1000.
            else:
                error_msg = "KO To stop a job you have to specify the date"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        elif request_type == 'ls_jobs':
            # On vérifie qu'il n'y ait pas d'arguments indésirables
            if len(data_recv) != 1:
                error_msg = "KO Message not formed well. For ls_jobs"
                error_msg += ", no more arguments are needed"
                self.clientsocket.send(error_msg)
                self.clientsocket.close()
                syslog.syslog(syslog.LOG_ERR, error_msg)
                return []
        else:
            error_msg = "KO Action not recognize. Actions possibles are : "
            error_msg += "add del status start stop restart ls_jobs"
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
        if request_type != 'ls_jobs':
            job_name = data_recv[1]
        if request_type == 'add':
            # TODO Vérifié que l'appli a bien été installé ?
            mutex_jobs.acquire()
            if not data_recv[3]:
                dict_jobs[job_name] = dict(command=data_recv[2],
                                           required=data_recv[3],
                                           optional=data_recv[4],
                                           set_id = set(),
                                           persistent=data_recv[5])
            else:
                dict_jobs[job_name] = dict(command=data_recv[2],
                                           required=str(data_recv[3]).split(' '),
                                           optional=data_recv[4],
                                           set_id = set(),
                                           persistent=data_recv[5])
            mutex_jobs.release()
        elif request_type == 'del':
            # On vérifie si le job n'est pas en train de tourner
            mutex_jobs.acquire()
            if len(dict_jobs[job_name]['set_id']) != 0:
                for instance_id in dict_jobs[job_name]['set_id']:
                    self.scheduler.add_job(stop_job, 'date', args=[job_name,
                                                                   instance_id])
            mutex_jobs.release()
            # TODO Vérifié que l'appli a bien été déinstallé ?
            mutex_jobs.acquire()
            del dict_jobs[job_name]
            mutex_jobs.release()
        elif request_type == 'start':
            if not self.start_job(mutex_jobs, dict_jobs, data_recv):
                return
        elif request_type == 'stop':
            instance_id = data_recv[2]
            actual_timestamp = time.time()
            if data_recv[4] < actual_timestamp:
                date = None
            else:
                date = datetime.fromtimestamp(data_recv[4])
            self.scheduler.add_job(stop_job, 'date', run_date=date,
                                   args=[job_name, instance_id])
            try:
                self.scheduler.remove_job(job_name + instance_id)
            except JobLookupError:
                # On vérifie si il n'est pas déjà stoppé
                mutex_jobs.acquire()
                job = dict_jobs[job_name]
                mutex_jobs.release()
                if not instance_id in job['set_id']:
                    error_msg = "OK job " + job_name + "with id " + instance_id
                    error_msg += " is already stopped"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return
            mutex_jobs.acquire()
            dict_jobs[job_name]['set_id'].remove(instance_id)
            mutex_jobs.release()
        elif request_type == 'status':
            instance_id = data_recv[2]
            # Récupérer le status actuel
            if data_recv[3] == 'date':
                actual_timestamp = time.time()
                if data_recv[4] < actual_timestamp:
                    date = None
                else:
                    date = datetime.fromtimestamp(data_recv[4])
                try:
                    self.scheduler.add_job(status_job, 'date', run_date=date,
                                           args=[job_name, instance_id,
                                                 self.scheduler], id=job_name
                                           + instance_id + "_status")
                except ConflictingIdError:
                    error_msg = "KO A watch on instance " + job_name + " with "
                    error_msg += "id " + instance_id + " is already programmed"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return
            # Programmer de regarder le status régulièrement
            elif data_recv[3] == 'interval':
                interval = data_recv[4]
                try:
                    self.scheduler.add_job(status_job, 'interval', seconds=interval,
                                           args=[job_name, instance_id,
                                                 self.scheduler], id=job_name
                                           + instance_id + "_status")
                except ConflictingIdError:
                    error_msg = "KO A watch on instance " + job_name + " with "
                    error_msg += "id " + instance_id + " is already programmed"
                    self.clientsocket.send(error_msg)
                    self.clientsocket.close()
                    syslog.syslog(syslog.LOG_ERR, error_msg)
                    return
            # Déprogrammer
            elif data_recv[3] == 'stop':
                actual_timestamp = time.time()
                if data_recv[4] < actual_timestamp:
                    date = None
                else:
                    date = datetime.fromtimestamp(data_recv[4])
                try:
                    self.scheduler.get_job(job_name + instance_id + "_status")
                    # TODO get_job doesn't raise JobLookupError when the job
                    # isn't found. We have to found a function that does it
                except JobLookupError:
                    self.clientsocket.send("KO No watch on the status of the "
                                           "instance" + job_name + " with the "
                                           "id " + instance_id + " was programmed")
                    self.clientsocket.close()
                    return
                self.scheduler.add_job(stop_watch, 'date', args=[self.scheduler,
                                                                 job_name,
                                                                 instance_id],
                                       run_date=date)
        elif request_type == 'restart':
            # Stop le job si il est lancer
            instance_id = data_recv[2]
            mutex_jobs.acquire()
            if instance_id in dict_jobs[job_name]['set_id']:
                self.scheduler.add_job(stop_job, 'date', args=[job_name,
                                                               instance_id])
            mutex_jobs.release()
            try:
                self.scheduler.remove_job(job_name + instance_id)
            except JobLookupError:
                pass
            mutex_jobs.acquire()
            dict_jobs[job_name]['set_id'].remove(instance_id)
            mutex_jobs.release()
            # Le relancer avec les nouveaux arguments (éventuellement les mêmes)
            if not self.start_job(mutex_jobs, dict_jobs, data_recv):
                return
        elif request_type == 'ls_jobs':
            self.scheduler.add_job(ls_jobs, 'date')
        self.clientsocket.send("OK")
        self.clientsocket.close()



if __name__ == "__main__":
    # Ouverture de la socket d'ecoute
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpsock.bind(("",1112))
    num_connexion_max = 1000
    tcpsock.listen(num_connexion_max)

    # Creation du scheduler
    global scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    
    # Liste de job disponible (+ son mutex)
    global dict_jobs
    global mutex_jobs
    dict_jobs = {}
    mutex_jobs = threading.Lock()
    # On ajoute tous les jobs déjà présent
    path = '/opt/openbach-agent/jobs/'
    result_ls = subprocess.check_output(["ls", path]).split('\n')
    jobs = []
    for job in result_ls:
        if job[-4:] == '.cfg':
            jobs.append(job[:-4])
    for job_name in jobs:
        # On vérifie que ce fichier de conf contient tout ce qu'il faut
        try:
            conf = Conf(job_name, path)
        except (NoSectionError, MissingSectionHeaderError, NoOptionError):
            error_msg = "KO Conf files for job " + job_name + " isn't formed well"
            syslog.syslog(syslog.LOG_ERR, error_msg)
            continue
        if conf.required == '':
            conf.required = False
        if conf.optional == 'True' or conf.optional == 'true':
            conf.optional = True
        elif conf.optional == 'False' or conf.optional == 'false':
            conf.optional = False
        else:
            error_msg = "KO Conf 'optional' for job " + job_name + " should"
            error_msg += "be a boolean"
            syslog.syslog(syslog.LOG_ERR, error_msg)
            continue
        if conf.persistent == 'True' or conf.persistent == 'true':
            conf.persistent = True
        elif conf.persistent == 'False' or conf.persistent == 'false':
            conf.persistent = False
        else:
            error_msg = "KO Conf 'persistent' for job " + job_name + " should"
            error_msg += "be a boolean"
            syslog.syslog(syslog.LOG_ERR, error_msg)
            continue
        # On ajoute le job a la liste des jobs disponibles
        if not conf.required:
            dict_jobs[job_name] = dict(command=conf.command,
                                       required=conf.required,
                                       optional=conf.optional,
                                       set_id = set(),
                                       persistent=conf.persistent)
        else:
            dict_jobs[job_name] = dict(command=conf.command,
                                       required=str(conf.required).split(' '),
                                       optional=conf.optional,
                                       set_id = set(),
                                       persistent=conf.persistent)

    while True:
        (clientsocket, (ip, port)) = tcpsock.accept()
        newthread = ClientThread(clientsocket, scheduler, path)
        newthread.start()

