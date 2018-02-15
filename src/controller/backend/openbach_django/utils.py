#!/usr/bin/env python3

# OpenBACH is a generic testbed able to control/configure multiple
# network/physical entities (under test) and collect data from them. It is
# composed of an Auditorium (HMIs), a Controller, a Collector and multiple
# Agents (one for each network entity that wants to be tested).
#
#
# Copyright © 2016 CNES
#
#
# This file is part of the OpenBACH testbed.
#
#
# OpenBACH is a free software : you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see http://www.gnu.org/licenses/.


"""Helper tools to simplify the writing of models and views"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import os
import enum
import json
import shlex
import socket
import syslog
import tempfile
import ipaddress


class BadRequest(Exception):
    """Custom exception raised when parsing of a request failed"""
    def __init__(self, reason, returncode=400, infos=None,
                 severity=syslog.LOG_ERR):
        super().__init__(reason)
        self.reason = reason
        self.returncode = returncode
        if infos:
            self.infos = infos
        else:
            self.infos = {}
        syslog.syslog(severity, self.reason)


def send_fifo(message, local_port=1113):
    """Communicate a message on the given port of the local
    machine through a socket and a FIFO file.

    Opens a FIFO and write the message to it, then send to
    the other end the path to that FIFO. Wait for the other
    end to write back a result and return it to the caller.
    """
    with socket.create_connection(('localhost', local_port)) as conductor:
        with tempfile.NamedTemporaryFile('w') as f:
            fifoname = f.name
        try:
            os.mkfifo(fifoname)
        except OSError as e:
            raise BadRequest('Can not create FIFO file', 400, {'error': e})
        os.chmod(fifoname, 0o666)
        conductor.send(json.dumps({'fifoname': fifoname}).encode())
        with open(fifoname, 'w') as fifo:
            fifo.write(json.dumps(message))
        conductor.recv(16)  # Any response indicates end of processing

    with open(fifoname, 'r') as fifo:
        msg = fifo.read()
    os.remove(fifoname)
    return msg


def nullable_json(model):
    """Return the json attribute of a model, or None if no model"""
    if model is None:
        return None
    return model.json


def extract_models(cls):
    """Generate each sub-model out of a base Django's model class.

    Does not generate models that are marked abstract as they don't
    have any database representation.
    """
    for sub_class in cls.__subclasses__():
        if not sub_class._meta.abstract:
            yield sub_class
        yield from extract_models(sub_class)


def extract_integer(container, name, *, default=None):
    """Extract a field named `name` from the given container and
    tries to convert it to an integer.

    Return the default value if the field is not present or an
    integer otherwise. Raise ValueError on failure.
    """
    try:
        value = container[name]
    except KeyError:
        return default
    else:
        try:
            return int(value)
        except ValueError:
            raise ValueError(name) from None


class ValuesType(enum.Enum):
    INTEGER = 'int'
    BOOLEAN = 'bool'
    STRING = 'str'
    FLOATING_POINT_NUMBER = 'float'
    IP_ADDRESS = 'ip'
    LIST = 'list'
    JSON_DATA = 'json'
    NONE_TYPE = 'None'


def check_and_get_value(value, kind):
    kind = ValuesType(kind)
    try:
        validate = VALIDATORS[kind]
    except KeyError:
        raise ValueError(
                'Value \'{}\' has unknown type: {}'
                .format(value, kind))

    validate(value)
    if kind == ValuesType.JSON_DATA:
        return json.dumps(value)
    if kind == ValuesType.LIST:
        return ' '.join(shlex.quote(str(val)) for val in value)
    return value


def _generic_validator(value, converter, type_name):
    try:
        converter(value)
    except ValueError:
        raise ValueError(
                'Value \'{}\' does not parse as {}'
                .format(value, type_name))


def _validate_int(value):
    _generic_validator(value, int, 'an integer')


def _validate_bool(value):
    if str(value).lower() not in {'true', 't', 'false', 'f'}:
        raise ValueError(
                'Value \'{}\' does not parse as a '
                'boolean'.format(value))


def _validate_str(value):
    pass


def _validate_float(value):
    _generic_validator(value, float, 'a floating point number')


def _validate_ip(value):
    _generic_validator(value, ipaddress.ip_address, 'an IP address')


def _validate_list(value):
    if not isinstance(value, list):
        raise ValueError('Value \'{}\' does not parse as a list'.format(value))


def _validate_json(value):
    if not isinstance(value, dict):
        raise ValueError('Value \'{}\' is not valid JSON data'.format(value))


def _validate_none(value):
    pass


VALIDATORS = {
        ValuesType.INTEGER: _validate_int,
        ValuesType.BOOLEAN: _validate_bool,
        ValuesType.STRING: _validate_str,
        ValuesType.FLOATING_POINT_NUMBER: _validate_float,
        ValuesType.IP_ADDRESS: _validate_ip,
        ValuesType.LIST: _validate_list,
        ValuesType.JSON_DATA: _validate_json,
        ValuesType.NONE_TYPE: _validate_none,
}
