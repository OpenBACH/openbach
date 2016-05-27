#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author: Adrien THIBAUD / <adrien.thibaud@toulouse.viveris.com>

"""
uninstall_jobs.py - <+description+>
"""

import argparse
from frontend import uninstall_jobs, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - Uninstall Jobs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-j', '--job_name', metavar='NAME', action='append',
            nargs='+', required=True, help='Name of the Jobs to install on '
            'the next agent. May be specified several times to install '
            'different sets of jobs on different agents.')
    parser.add_argument('-a', '--agent_ip', metavar='ADDRESS', action='append',
            required=True, help='IP address of the agent where the next set '
            'of jobs should be installed. May be specified several times to '
            'install different sets of jobs on different agents.')
    
    # get args
    args = parser.parse_args()
    jobs_names = args.job_name
    agents_ips = args.agent_ip

    # If user specified more set of jobs than agent ips
    # we can't figure it out
    if len(jobs_names) != len(agents_ips):
        parser.error('-j and -a arguments should appear by pairs')

    # Backward compatibility: change the backend behaviour
    # before removing the next 4 lines
    #  -> flatten jobs_names so we have a list instead of a list of lists
    jobs_names = list(itertools.chain.from_iterable(jobs_names))
    #  -> use only the first agent ip
    agents_ips = [agents_ips[0]]

    pretty_print(uninstall_jobs)(jobs_names, agents_ips)

