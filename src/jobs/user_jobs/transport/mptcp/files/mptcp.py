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


import subprocess
import argparse
import time
import syslog
import collect_agent


def main(iface_link1, iface_link2, network_link1, network_link2, gw_link1, 
         gw_link2, ip_link1, ip_link2, conf_up):
    
    conffile = "/opt/openbach-jobs/mptcp/mptcp_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to collect-agent")
        quit()

    #Configure MPTCP routing
    if conf_up == 1:
        #Add mptcp routes for link1
        try:
            subprocess.call(["ip", "route", "add", "table", "1", "to",
                             network_link1, "dev", iface_link1, "scope", "link"])
    
            subprocess.call(["ip", "route", "add", "table", "1", "default", "via",
                             gw_link1, "dev", iface_link1])
    
            subprocess.call(["ip", "rule", "add", "from", ip_link1, "table", "1"])
    
            #Add mptcp routes for link2
            subprocess.call(["ip", "route", "add", "table", "2", "to",
                             network_link2, "dev", iface_link2, "scope", "link"])
    
            subprocess.call(["ip", "route", "add", "table", "2", "default", "via",
                             gw_link2, "dev", iface_link2])
    
            subprocess.call(["ip", "rule", "add", "from", ip_link2, "table", "2"])

    
        
            #enable both interfaces for mptcp
            subprocess.call(["ip", "link", "set", "dev", iface_link1, "multipath", "on"])
            subprocess.call(["ip", "link", "set", "dev", iface_link2, "multipath", "on"])
            collect_agent.send_log(syslog.LOG_DEBUG, "Added routes")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying ip route " + str(ex))
        
        #enable mptcp
        try: 
            subprocess.call(["sysctl", "-w", "net.mptcp.mptcp_enabled=1"])
            subprocess.call(["sysctl", "-p"])
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP is enabled ")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR modifying sysctl " + str(ex))
        
        
    else:
        try:
            #delete routes/tables
            subprocess.call(["ip", "rule", "del", "table", "1"])
            subprocess.call(["ip", "route", "flush", "table", "1"])
            subprocess.call(["ip", "rule", "del", "table", "2"])
            subprocess.call(["ip", "route", "flush", "table", "2"])
        
            #disable both interfaces for mptcp
            subprocess.call(["ip", "link", "set", "dev", iface_link1, "multipath", "off"])
            subprocess.call(["ip", "link", "set", "dev", iface_link2, "multipath", "off"])
        
            #disable mptcp
            subprocess.call(["sysctl", "-w", "net.mptcp.mptcp_enabled=0"])
            subprocess.call(["sysctl", "-p"])
            
            collect_agent.send_log(syslog.LOG_DEBUG, "MPTCP is disabled ")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR removing routes and mptcp" + str(ex))

if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('iface_link1', metavar='iface_link1', type=str,
                        help='')
    parser.add_argument('iface_link2', metavar='iface_link2', type=str,
                        help='')
    parser.add_argument('network_link1', metavar='network_link1', type=str,
                        help='')
    parser.add_argument('network_link2', metavar='network_link2', type=str,
                        help='')
    parser.add_argument('gw_link1', metavar='gw_link1', type=str,
                        help='')
    parser.add_argument('gw_link2', metavar='gw_link2', type=str,
                        help='')
    parser.add_argument('ip_link1', metavar='ip_link1', type=str,
                        help='')
    parser.add_argument('ip_link2', metavar='ip_link2', type=str,
                        help='')
    parser.add_argument('-c', '--conf_up', type=int, default=1, help='')



    # get args
    args = parser.parse_args()
    iface_link1 = args.iface_link1
    iface_link2 = args.iface_link2
    network_link1 = args.network_link1
    network_link2 = args.network_link2
    gw_link1 = args.gw_link1
    gw_link2 = args.gw_link2
    ip_link1 = args.ip_link1
    ip_link2 = args.ip_link2
    conf_up = args.conf_up
    

    main(iface_link1, iface_link2, network_link1, network_link2, gw_link1,
         gw_link2, ip_link1, ip_link2, conf_up) 

