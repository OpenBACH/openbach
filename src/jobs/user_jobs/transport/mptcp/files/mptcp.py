#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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



   @file     mptcp.py
   @brief    Sources of the Job mptcp
   @author   David PRADAS <david.pradas@toulouse.viveris.com>
"""

SCHEDULERS = {'default', 'roundrobin', 'redundant'}
PATH_MANAGERS = {'default', 'fullmesh', 'ndiffports', 'binder'}

import subprocess
import argparse
import time
import syslog
import collect_agent


def main(iface_link1, iface_link2, iface_on1, iface_on2,
         conf_up, checksum, syn_retries, path_manager, scheduler):
    
    conffile = "/opt/openbach-jobs/mptcp/mptcp_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to collect-agent")
        quit()

    # Check if valid scheduler and path_manager values
    if path_manager and (path_manager not in PATH_MANAGERS):
        collect_agent.send_log(syslog.LOG_ERR, "ERROR invalid path-manager")
        quit()
    if scheduler and (scheduler not in SCHEDULERS):
        collect_agent.send_log(syslog.LOG_ERR, "ERROR scheduler")
        quit()

    # Configure MPTCP routing
    if conf_up == 1:
        # Enable mptcp
        try: 
            subprocess.call(["sysctl", "-w", "net.mptcp.mptcp_enabled=1"])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP is enabled ")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
    else:
        try:
            # Disable mptcp
            subprocess.call(["sysctl", "-w", "net.mptcp.mptcp_enabled=0"])
            subprocess.call(["sysctl", "-p"])
            
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP is disabled ")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR disabling mptcp" + str(ex))
    # Change checksum
    if checksum is not None:
        try: 
            subprocess.call(["sysctl", "-w",
                             "net.mptcp.mptcp_checksum=%d" % checksum])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP checksum updated")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
    # Change syn_retries
    if syn_retries is not None:
        try: 
            subprocess.call(["sysctl", "-w",
                             "net.mptcp.mptcp_syn_retries=%d" % syn_retries])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP syn_retries updated")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
    # Change path_manager
    if path_manager is not None:
        try: 
            subprocess.call(["sysctl", "-w",
                             "net.mptcp.mptcp_path_manager=%s" %
                             path_manager])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP path_manager updated")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
    # Change scheduler
    if scheduler is not None:
        try: 
            subprocess.call(["sysctl", "-w",
                             "net.mptcp.mptcp_scheduler=%s" % scheduler])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP scheduler updated")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
    # Enable interface 1
    if iface_on1:
        try:
            subprocess.call(["ip", "link", "set", "dev", iface_link1, "multipath",
                             "on"])
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERROR, "Error when setting"
                                   " multipath on interface %s" % iface_link1)
        else:
            collect_agent.send_log(syslog.LOG_DEBUG, "Enabled multipath on iface %s"
                                   % iface_link1)
    else:
        try:
            subprocess.call(["ip", "link", "set", "dev", iface_link1, "multipath",
                             "off"])
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERROR, "Error when setting off"
                                   " multipath on interface %s" % iface_link1)
        else:
            collect_agent.send_log(syslog.LOG_DEBUG, "Disabled multipath on iface %s"
                                   % iface_link1)
    # Enable interface 2
    if iface_on2:
        try:
            subprocess.call(["ip", "link", "set", "dev", iface_link2, "multipath",
                             "on"])
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERROR, "Error when setting"
                                   " multipath on interface %s" % iface_link2)
        else:
            collect_agent.send_log(syslog.LOG_DEBUG, "Enabled multipath on iface %s"
                                   % iface_link2)
    else:
        try:
            subprocess.call(["ip", "link", "set", "dev", iface_link2, "multipath",
                             "off"])
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERROR, "Error when setting off"
                                   " multipath on interface %s" % iface_link2)
        else:
            collect_agent.send_log(syslog.LOG_DEBUG, "Disabled multipath on iface %s"
                                   % iface_link2) 
            

if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('iface_link1', metavar='iface_link1', type=str,
                        help='')
    parser.add_argument('iface_link2', metavar='iface_link2', type=str,
                        help='')
    parser.add_argument('-o', '--iface-on1', action='store_true', help='')
    parser.add_argument('-O', '--iface-on2', action='store_true', help='')
    parser.add_argument('-c', '--conf_up', type=int, default=1, help='')
    parser.add_argument('-k', '--checksum', type=int, help='')
    parser.add_argument('-y', '--syn-retries', type=int, help='')
    parser.add_argument('-p', '--path-manager', type=str, help='')
    parser.add_argument('-s', '--scheduler', type=str, help='')

    # get args
    args = parser.parse_args()
    iface_link1 = args.iface_link1
    iface_link2 = args.iface_link2
    iface_on1 = args.iface_on1
    iface_on2 = args.iface_on2
    conf_up = args.conf_up
    checksum = args.checksum
    syn_retries = args.syn_retries
    path_manager = args.path_manager
    scheduler = args.scheduler    

    main(iface_link1, iface_link2, iface_on1, iface_on2, conf_up, checksum,
         syn_retries, path_manager, scheduler) 

