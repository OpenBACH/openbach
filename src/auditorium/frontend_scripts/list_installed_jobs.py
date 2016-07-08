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
   
   
   
   @file     list_installed_jobs.py
   @brief    Call the openbach-function list_installed_jobs
   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from frontend import list_installed_jobs, pretty_print


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='OpenBach - List installed jobs',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('agent_ip', help='IP Address of the Agent')
    parser.add_argument('-u', '--update', action='store_true',
        help='Use only the last status present on the collector')
    parser.add_argument("-v", "--verbosity", action="count",
        help="Increase output verbosity")
    
    # get args
    args = parser.parse_args()
    agent_ip = args.agent_ip
    update = args.update
    verbosity = args.verbosity

    pretty_print(list_installed_jobs)(agent_ip, verbosity, update)

