#!/usr/bin/env python3

"""
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).


   Copyright © 2016 CNES


   This file is part of the OpenBACH testbed.


   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.

   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.

   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.



   @file     utils.py
   @brief    Classes used in the Controller
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import os
import tempfile
import json
import syslog


class BadRequest(Exception):
    """Custom exception raised when parsing of a request failed"""
    def __init__(self, reason, returncode=400, infos=None):
        super().__init__(reason)
        self.reason = reason
        self.returncode = returncode
        if infos:
            self.infos = infos
        else:
            self.infos = {}
        syslog.syslog(syslog.LOG_ERR, self.reason)


def send_fifo(msg, socket):
    """ Function that sends a message through a socket, and gets a fifo name in
    return (the response will be in that fifo) """
    socket.send(json.dumps(msg).encode())
    response = socket.recv(4096).decode()
    fifoname = json.loads(response)['fifoname']
    return fifoname


def recv_fifo(socket):
    """ Function that will receive a message through a socket, creates a fifo
    and send the name of this fifo through the socket (return the received
    message and the fifo name) """
    msg = socket.recv(4096).decode()
    msg = json.loads(msg)
    with tempfile.NamedTemporaryFile('w') as f:
        pass
    try:
        os.mkfifo(f.name)
    except OSError as e:
        raise BadRequest('Impossible to create the Fifo', 400, {'error': e})
    response = {'fifoname': f.name}
    socket.send(json.dumps(response).encode())
    return msg, f.name


def send_all(fifoname, msg):
    """ Function that send all the message through the fifo """
    with open(fifoname, 'w') as fifo:
        fifo.write(msg)


def recv_all(fifoname):
    """ Function that receives a message through the fifo """
    with open(fifoname, 'r') as fifo:
        msg = fifo.read()
    os.remove(fifoname)
    return msg


_SEVERITY_MAPPING = {
    0: 3,   # Error
    1: 4,   # Warning
    2: 6,   # Informational
    3: 7,   # Debug
}


def convert_severity(severity):
    """ Function that converts the syslog severity to the openbach severity """
    return _SEVERITY_MAPPING.get(severity, 8)
