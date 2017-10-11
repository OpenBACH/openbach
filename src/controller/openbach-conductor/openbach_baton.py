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


"""Means of sending orders to the Agents"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import shlex
import struct
import socket

import errors


class OpenBachBaton:
    def __init__(self, agent_ip, agent_port=1112):
        address = (agent_ip, agent_port)
        self.socket = None
        try:
            self.socket = socket.create_connection(address)
        except OSError as e:
            raise errors.UnprocessableError(
                    'Cannot connect to the agent {}: {}'
                    .format(agent_ip, e))

    def __del__(self):
        if self.socket is not None:
            self.socket.close()

    def _recv_all(self, amount):
        buffer = bytearray(amount)
        view = memoryview(buffer)
        while amount > 0:
            received = self.socket.recv_into(view[-amount:])
            if not received:
                break
            amount -= received
        return buffer

    def send_message(self, message):
        message = message.encode()
        length = struct.pack('>I', len(message))
        self.socket.sendall(length)
        self.socket.sendall(message)

    def recv_message(self):
        size = self._recv_all(4)
        length, = struct.unpack('>I', size)
        return self._recv_all(length).decode()

    def communicate(self, message):
        try:
            self.send_message(message)
            response = self.recv_message()
        except OSError as e:
            raise errors.UnprocessableError(
                    'Sending message to the agent failed: {}'
                    .format(e))

        if not response.startswith('OK'):
            raise errors.UnprocessableError(
                    'The agent did not send a success message',
                    agent_message=response)

        return response

    def start_job_instance(self, job_name, job_id, scenario_id, owner_id, arguments, date=None, interval=None):
        assert sum(time is not None for time in (date, interval)) == 1

        message = 'start_job_instance_agent {} {} {} {} {}{} {}'.format(
                shlex.quote(job_name), job_id, scenario_id, owner_id,
                '' if date is None else 'date {}'.format(date),
                '' if interval is None else 'interval {}'.format(interval),
                arguments)

        return self.communicate(message)

    def stop_job_instance(self, job_name, job_id, date):
        message = (
                'stop_job_instance_agent {} {} date {}'
                .format(shlex.quote(job_name), job_id, date)
        )

        return self.communicate(message)

    def restart_job_instance(self, job_name, job_id, scenario_id, arguments, date=None, interval=None):
        assert sum(time is not None for time in (date, interval)) == 1

        message = 'restart_job_instance_agent {} {} {} {}{} {}'.format(
                shlex.quote(job_name), job_id, scenario_id,
                '' if date is None else 'date {}'.format(date),
                '' if interval is None else 'interval {}'.format(interval),
                arguments)

        return self.communicate(message)

    def status_job_instance(self, job_name, job_id):
        message = 'status_job_instance_agent {} {}'.format(shlex.quote(job_name), job_id)
        return self.communicate(message)

    def list_jobs(self):
        return self.communicate('status_jobs_agent')

    def add_job(self, job_name):
        return self.communicate('add_job_agent {}'.format(shlex.quote(job_name)))

    def remove_job(self, job_name):
        return self.communicate('del_job_agent {}'.format(shlex.quote(job_name)))

    def restart_agent(self):
        return self.communicate('restart_agent')
