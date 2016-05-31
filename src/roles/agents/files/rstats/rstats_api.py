#!/usr/bin/env python3
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
rstats_api.py - <+description+>
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
            syslgo.syslog(syslog.LOG_NOTICE, 'NOTICE: Identifiant de connexion = {}'.format(id))
            return id
    elif result.startswith('KO'):
        syslog.syslog(syslog.LOG_ERR, 'ERROR: Something went wrong :')
        syslog.syslog(syslog.LOG_ERR, '\t{}'.format(result))
    else:
        syslog.syslog(syslog.LOG_ERR, 'ERROR: Return message isn\'t well formed')
        syslog.syslog(syslog.LOG_ERR, '\t{}'.format(result))


def send_stat(connection_id, stat_name, timestamp, value_name, value):
    cmd = '2 ' + connection_id + ' ' + stat_name + ' ' +  str(timestamp)
    if type(value_name) == list:
        if type(value) == list:
            if len(value) != len(value_name):
                return 'KO, You should provide as many value as value_name'
            for i in range(len(value)):
                cmd += ' ' + value_name[i] + ' ' + str(value[i])
        else:
            return 'KO, You should provide as many value as value_name'
    else:
        cmd +=  ' ' + value_name + ' ' +  str(value)
    return _rstat_send_message(cmd)


def reload_stat(connection_id):
    return _rstat_send_message('3 {}'.format(connection_id))


def reload_all_stats():
    return _rstat_send_message('4')


if __name__ == '__main__':
    # Reload rstat when calling this file
    result = reload_alll_stats()
    print('Rstat reloaded. Message was', result)

