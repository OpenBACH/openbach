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
   
   
   
   @file     rstats_api.py
   @brief    The API to use to communicate with rstats
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


import socket
import syslog
import errno


def _rstat_send_message(message):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('', 1111))
    except socket.error as serr:
        if serr.errno == errno.ECONNREFUSED:
            syslog.syslog(syslog.LOG_ERR,
                    'ERROR: Connexion to rstats refused, '
                    'maybe rstats service isn\'t started')
        raise serr
    sock.send(message.encode())
    result = sock.recv(9999).decode()
    sock.close()
    return result


def register_stat(conffile, job_name, prefix=None):
    if prefix:
        cmd = '1 {} {} {}'.format(conffile, job_name, prefix)
    else:
        cmd = '1 {} {}'.format(conffile, job_name)

    result = _rstat_send_message(cmd)
    if result.startswith('OK'):
        try:
            ok, id = result.split()
            id = int(id)
        except ValueError:
            syslog.syslog(syslog.LOG_ERR, 'ERROR: Return message isn\'t well formed')
            syslog.syslog(syslog.LOG_ERR, '\t{}'.format(result))
        else:
            syslog.syslog(syslog.LOG_NOTICE, 'NOTICE: Identifiant de connexion = {}'.format(id))
            return id
    elif result.startswith('KO'):
        syslog.syslog(syslog.LOG_ERR, 'ERROR: Something went wrong :')
        syslog.syslog(syslog.LOG_ERR, '\t{}'.format(result))
    else:
        syslog.syslog(syslog.LOG_ERR, 'ERROR: Return message isn\'t well formed')
        syslog.syslog(syslog.LOG_ERR, '\t{}'.format(result))


def send_stat(connection_id, stat_name, timestamp, value_names, values):
    # TODO send_stat(..., **kwargs)
    cmd = '2 {} {} {}'.format(connection_id, stat_name, timestamp)
    if isinstance(value_names, list):
        if isinstance(values, list):
            if len(values) != len(value_names):
                return 'KO, You should provide as many value as value_name'
            args = ' '.join('{} {}'.format(name, '\\n'.join(value.split('\n'))) for name, value in zip(value_names, values))
            cmd = '{} \"{}\"'.format(cmd, args)
        else:
            return 'KO, You should provide as many value as value_name'
    else:
        cmd = '{} {} \"{}\"'.format(cmd, value_names, '\\n'.join(values.split('\n')))
    return _rstat_send_message(cmd)


def reload_stat(connection_id):
    return _rstat_send_message('3 {}'.format(connection_id))


def reload_all_stats():
    return _rstat_send_message('4')


if __name__ == '__main__':
    # Reload rstat when calling this file
    result = reload_all_stats()
    print('Rstat reloaded. Message was', result)

