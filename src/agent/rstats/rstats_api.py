#!/usr/bin/env python3

"""
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).


   Copyright © 2016 CNES


   This file is part of the OpenBACH testbed.


   OpenBACH is a free software : you can redistribute it and/or modify it under
   the terms of the GNU General Public License as published by the Free
   Software Foundation, either version 3 of the License, or (at your option)
   any later version.

   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or
   FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
   more details.

   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.



   @file     rstats_client.py
   @brief    rstats communication client
   @author   Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
"""


import ctypes
import json


try:
    rstats = ctypes.cdll.LoadLibrary('librstats.so')
except OSError:
    rstats = ctypes.cdll.LoadLibrary('rstats.dll')


_register_stat = rstats.rstats_register_stat
_register_stat.restype = ctypes.c_uint
_register_stat.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]

_send_stat = rstats.rstats_send_stat
_send_stat.restype = ctypes.c_char_p
_send_stat.argtypes = [
        ctypes.c_uint, ctypes.c_char_p, ctypes.c_longlong, ctypes.c_char_p]

_reload_stat = rstats.rstats_reload_stat
_reload_stat.restype = ctypes.c_char_p
_reload_stat.argtypes = [ctypes.c_uint]

_remove_stat = rstats.rstats_remove_stat
_remove_stat.restype = ctypes.c_char_p
_remove_stat.argtypes = [ctypes.c_uint]

_reload_all_stats = rstats.rstats_reload_all_stats
_reload_all_stats.restype = ctypes.c_char_p
_reload_all_stats.argtypes = []

_get_configs = rstats.rstats_get_configs
_get_configs.restype = ctypes.c_char_p
_get_configs.argtypes = []


def register_stat(config_file, job_name, prefix=None):
    if prefix is None:
        prefix = ''
    return _register_stat(
            config_file.encode(),
            job_name.encode(),
            prefix.encode())


def send_stat(id, stat_name, timestamp, **kwargs):
    stats = ' '.join(
            '"{}" "{}"'.format(k, v)
            for k, v in kwargs.items())
    return _send_stat(
            id, stat_name.encode(),
            timestamp, stats.encode()).decode(errors='replace')


def reload_stat(id):
    return _reload_stat(id).decode(errors='replace')


def remove_stat(id):
    return _remove_stat(id).decode(errors='replace')


def reload_all_stats():
    return _reload_all_stats().decode(errors='replace')


def get_configs():
    configs = _get_configs().decode(errors='replace')
    return json.loads(configs)


if __name__ == '__main__':
    result = reload_all_stats()
    print('Rstats reloaded. Message was', result)
