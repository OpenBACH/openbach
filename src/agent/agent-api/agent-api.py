#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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

"""OpenBACH's agent API"""

__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
'''

import sys
import shlex
import argparse
import datetime
from contextlib import suppress

from conductor import errors
from conductor.openbach_baton import OpenBachBaton

def execute_and_print(function, *args, **kargs):
    try:
        response = function(*args, **kargs)
    except errors.ConductorError as e:
        print('{}: {}'.format(e.error['error'], e.error['agent_message']),
                file=sys.stderr)
        sys.exit(e.ERROR_CODE)
    else:
        print(response)

def main(baton, args=None, interval=None, job_name=None,
        job_instance_id=None, date=None, action=None, **kwargs):

    # Format date
    if not date and not interval:
        date = 'now'
    elif date:
        date = datetime.datetime.strptime(
                '{} {}'.format(*date), 
                '%Y-%m-%d %H:%M:%S.%f').timestamp() * 1000

    if action == 'start_job':
        if job_instance_id > 0:
            execute_and_print(baton.start_job_instance, job_name, job_instance_id,
                    0, 0, args, date=date, interval=interval)
        else:
            message = 'start_job_instance_agent_id {} {}{} {}'.format(
                    shlex.quote(job_name),
                    '' if date is None else 'date {}'.format(date),
                    '' if interval is None else 'interval {}'.format(interval),
                    args)
            execute_and_print(baton.communicate, message)
    elif action == 'stop_job':
        execute_and_print(baton.stop_job_instance, job_name, job_instance_id, date)
    elif action == 'restart_job':
        execute_and_print(baton.restart_job_instance, job_name, job_instance_id,
                0, 0, args, date=date, interval=interval)
    elif action == 'job_status':
        execute_and_print(baton.status_job_instance, job_name, job_instance_id)
    elif action == 'list_jobs':
        execute_and_print(baton.list_jobs)
    elif action == 'restart_agent':
        execute_and_print(baton.restart_agent)


if __name__ == "__main__":
    def parse(value):
        name, *values = shlex.split(value, posix=True)
        return name, values

    # Set up parser
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Global arguments
    parser.add_argument("agent_ip", type=str,
            help="IP address of the agent")
    parser.add_argument("-p", "--port", type=int, default=1112,
            help="Port of the agent")
    subparsers = parser.add_subparsers(dest="action", metavar="action",
            help='The action to run on the agent')

    # Start Job subparser
    parser_start_job = subparsers.add_parser('start_job',
            help='Start a job instance')
    parser_start_job.add_argument("job_name", type=str,
            help="Name of the job to start")
    parser_start_job.add_argument("-i", "--job_instance_id", type=int, default=-1,
            help="The Job Instance ID to use (-1 for first available)")
    group_start_job = parser_start_job.add_mutually_exclusive_group(required=False)
    group_start_job.add_argument("--date", metavar=('DATE', 'TIME'), nargs=2,
            help='Date of the execution')
    group_start_job.add_argument("--interval", type=int,
            help='Interval of the execution')
    parser_start_job.add_argument("-a", "--args", type=str, metavar='ARG1 [ARG2 [...]]', 
            help='The job arguments (must be delimited by quotes)')

    # Stop Job subparser
    parser_stop_job = subparsers.add_parser('stop_job',
            help='Stop a job instance')
    parser_stop_job.add_argument("job_name", type=str,
            help="Name of the job to stop")
    parser_stop_job.add_argument("job_instance_id", type=int,
            help="The Job Instance ID to use")
    parser_stop_job.add_argument("--date", metavar=('DATE', 'TIME'), nargs=2,
            help='Date to stop the job at')

    # Restart Job subparser
    parser_restart_job = subparsers.add_parser('restart_job',
            help='Restart a job instance')
    parser_restart_job.add_argument("job_name", type=str,
            help="Name of the job to restart")
    parser_restart_job.add_argument("job_instance_id", type=int, 
            help="The Job Instance ID to restart")
    group_restart_job = parser_restart_job.add_mutually_exclusive_group(required=False)
    group_restart_job.add_argument("--date", metavar=('DATE', 'TIME'), nargs=2,
            help='Date of the execution')
    group_restart_job.add_argument("--interval", type=int,
            help='Interval of the execution')
    parser_restart_job.add_argument("-a", "--args", type=str, metavar='ARG1 [ARG2 [...]]', 
            help='The job arguments (must be delimited by quotes)')

    # Job Status subparser
    parser_job_status = subparsers.add_parser('job_status',
            help='Get status of a job instance')
    parser_job_status.add_argument("job_name", type=str,
            help="Name of the job to get status of")
    parser_job_status.add_argument("job_instance_id", type=int,
            help="The Job Instance ID")

    # List Jobs subparser
    parser_list_jobs = subparsers.add_parser('list_jobs',
            help='List the installed jobs')

    # Restart Agent subparser
    parser_restart_agent = subparsers.add_parser('restart_agent',
            help='Restart the agent')

    # Parse arguments
    args = parser.parse_args()
    if args.action is None:
        parser.error("Action is required")
    try:
        baton = OpenBachBaton(args.agent_ip, args.port)
    except errors.ConductorError:
        parser.error("Unable to communicate with agent on {}:{}".format(
            args.agent_ip, args.port))

    main(baton, **vars(args))
