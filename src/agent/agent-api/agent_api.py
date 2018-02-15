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


"""OpenBACH's agent API"""


__author__ = 'Viveris Technologies'
__credits__ = '''Contributors:
 * Joaquin MUGUERZA <joaquin.muguerza@toulouse.viveris.com>
 * Mathias ETTINGER <mathias.ettinger@toulouse.viveris.com>
'''


import sys
import shlex
import argparse
import datetime

from conductor import errors
from conductor.openbach_baton import OpenBachBaton


DATE_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def contact_agent(baton, action, date, interval, job_name, job_id, arguments):
    if action == 'start_job':
        if job_id < 0:
            message = 'start_job_instance_agent_id {} {}{} {}'.format(
                    shlex.quote(job_name),
                    '' if date is None else 'date {}'.format(date),
                    '' if interval is None else 'interval {}'.format(interval),
                    arguments)
            return baton.communicate(message)
        else:
            return baton.start_job_instance(
                    job_name, job_id, 0, 0,
                    arguments, date, interval)
    elif action == 'stop_job':
        return baton.stop_job_instance(job_name, job_id, date)
    elif action == 'restart_job':
        return baton.restart_job_instance(
                job_name, job_id, 0, 0,
                arguments, date, interval)
    elif action == 'job_status':
        return baton.status_job_instance(job_name, job_id)
    elif action == 'list_jobs':
        return baton.list_jobs()
    elif action == 'restart_agent':
        return baton.restart_agent()


def main(baton, action, **kwargs):
    # Format date
    date = kwargs.get('date')
    interval = kwargs.get('interval')
    if date is None and interval is None:
        date = 'now'
    elif date is not None:
        date = '{} {}'.format(date)
        date = datetime.datetime.strptime(date, DATE_FORMAT)
        date = int(date.timestamp() * 1000)

    # Format arguments
    arguments = kwargs.get('arguments')
    if arguments is not None:
        arguments = ' '.join(map(shlex.quote, arguments))

    # Execute requested action
    try:
        response = contact_agent(
                baton, action,
                date, interval,
                kwargs.get('job_name'),
                kwargs.get('job_instance_id'),
                arguments)
    except errors.ConductorError as e:
        print(
                e.error['error'], ': ', e.error['agent_message'],
                sep='', file=sys.stderr)
        sys.exit(e.ERROR_CODE)
    else:
        print(response)


def build_parser():
    date_help = DATE_FORMAT.replace('%', '%%')

    # Set up parser
    parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Global arguments
    parser.add_argument('agent', help='IP address of the agent')
    parser.add_argument(
            '-p', '--port', type=int, default=1112,
            help='port of the agent')
    subparsers = parser.add_subparsers(
            dest='action', metavar='action',
            help='the action to run on the agent')

    # Start Job subparser
    parser_start_job = subparsers.add_parser(
            'start_job',
            help='start a job instance')
    parser_start_job.add_argument('job_name', help='name of the job to start')
    parser_start_job.add_argument(
            '-i', '--job_instance_id', type=int, default=-1,
            help='a specific job instance ID to use')
    group = parser_start_job.add_mutually_exclusive_group(required=False)
    group.add_argument(
            '-d', '--date', metavar=('DATE', 'TIME'), nargs=2,
            help='date of the execution (format: {})'.format(date_help))
    group.add_argument(
            '-t', '--interval', type=int,
            help='interval of the execution in seconds')
    parser_start_job.add_argument(
            '-a', '--arg', nargs='+', dest='arguments', metavar='ARG',
            help='arguments for the job (delimit each value by quotes)')

    # Stop Job subparser
    parser_stop_job = subparsers.add_parser(
            'stop_job',
            help='stop a job instance')
    parser_stop_job.add_argument('job_name', help='name of the job to stop')
    parser_stop_job.add_argument(
            'job_instance_id', type=int,
            help='the job instance ID to stop')
    parser_stop_job.add_argument(
            '-d', '--date', metavar=('DATE', 'TIME'), nargs=2,
            help='date to stop the job at (format: {})'.format(date_help))

    # Restart Job subparser
    parser_restart_job = subparsers.add_parser(
            'restart_job',
            help='restart a job instance')
    parser_restart_job.add_argument(
            'job_name',
            help='name of the job to restart')
    parser_restart_job.add_argument(
            'job_instance_id', type=int,
            help='the job instance ID to restart')
    group = parser_restart_job.add_mutually_exclusive_group(required=False)
    group.add_argument(
            '-d', '--date', metavar=('DATE', 'TIME'), nargs=2,
            help='date of the execution (format: {})'.format(date_help))
    group.add_argument(
            '-t', '--interval', type=int,
            help='interval of the execution in seconds')
    parser_restart_job.add_argument(
            '-a', '--arg', nargs='+', dest='arguments', metavar='ARG',
            help='arguments for the job (delimit each value by quotes)')

    # Job Status subparser
    parser_job_status = subparsers.add_parser(
            'job_status',
            help='get the status of a job instance')
    parser_job_status.add_argument('job_name', help='name of the job to query')
    parser_job_status.add_argument(
            'job_instance_id', type=int,
            help='the job instance ID to query')

    # List Jobs subparser
    subparsers.add_parser('list_jobs', help='list the installed jobs')

    # Restart Agent subparser
    subparsers.add_parser('restart_agent', help='restart the agent')

    return parser


if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()
    if args.action is None:
        parser.error('an action is required')

    try:
        baton = OpenBachBaton(args.agent, args.port)
    except errors.ConductorError:
        parser.error(
                'unable to communicate with agent on {}:{}'
                .format(args.agent, args.port))

    main(baton, **vars(args))
