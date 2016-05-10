#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
rstats_api.py - <+description+>
"""

import socket
import syslog
import errno


def register_stat(conffile, prefix=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("", 1111))
    except socket.error as serr:
        if serr.errno == errno.ECONNREFUSED:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Connexion to rstats refused, "
                          "maybe rstats service isn't started")
        raise serr
    cmd = "1 " + conffile
    if prefix != None:
        cmd += " " + prefix
    s.send(cmd)
    r = s.recv(9999)
    s.close()
    data = r.split(" ")
    if data[0] == 'OK':
        if len(data) != 2:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            return 0
        try:
            int(data[1])
        except:
            syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
            syslog.syslog(syslog.LOG_ERR, "\t" + r)
            return 0
        connection_id = data[1]
        syslog.syslog(syslog.LOG_NOTICE, "NOTICE: Identifiant de connexion = " +
                      connection_id)
        return connection_id
    elif data[0] == 'KO':
        syslog.syslog(syslog.LOG_ERR, "ERROR: Something went wrong :")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
        return 0
    else:
        syslog.syslog(syslog.LOG_ERR, "ERROR: Return message isn't well formed")
        syslog.syslog(syslog.LOG_ERR, "\t" + r)
        return 0


def send_stat(connection_id, stat_name, timestamp, value_name, value):
    cmd = "2 " + connection_id + " " + stat_name + " " +  str(timestamp)
    if type(value_name) == list:
        if type(value) == list:
            if len(value) != len(value_name):
                return "KO, You should provide as many value as value_name"
            for i in range(len(value)):
                cmd += " " + value_name[i] + " " + str(value[i])
        else:
            return "KO, You should provide as many value as value_name"
    else:
        cmd +=  " " + value_name + " " +  str(value)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("", 1111))
    s.send(cmd)
    r = s.recv(9999)
    s.close()
    return r


def reload_stat(connection_id):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("", 1111))
    cmd = "3 " + connection_id
    s.send(cmd)
    r = s.recv(9999)
    s.close()
    return r


