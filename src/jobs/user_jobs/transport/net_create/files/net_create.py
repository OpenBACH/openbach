#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author:  / <@toulouse.viveris.com>

import os
import subprocess
import argparse
import syslog
import collect_agent
import ipaddress

#Fonction de définition du type ip :

def ip(argument):
    try: 
       ipaddress.ip_address(argument)
    except Exception as ex:
                raise TypeError('Network parameter is not an IP')
    return argument


def main(net_name, address, password, RCfile):
    conffile = "/opt/openbach-jobs/net_create/net_create_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_DEBUG, "Stating net_create")

    
    # Define variable net for pool address allocation

    net = address.rsplit(".",1)
    
    # CREATE TEMPLATE

    with open("/tmp/" + net_name + '.yml', 'w') as file :
        file.writelines('''\
heat_template_version: 2013-05-23
                        
description: Simple template to deploy a single network instance
                        
resources:
                        
 {0}:
   properties:
     admin_state_up: true
     name: {0}
     shared: false
   type: OS::Neutron::Net
                        
 network_subnet:
   properties:
     allocation_pools:
     - end: {1[0]}.127
       start: {1[0]}.2
     cidr: {2}/24
     dns_nameservers: []
     enable_dhcp: true
     host_routes: []
     ip_version: 4
     name: {0}
     network_id:
       get_resource: {0}
   type: OS::Neutron::Subnet'''.format(net_name, net, address))
        
   # Create network
  
    try:

        subprocess.call('export OS_PASSWORD={0} && source {2} '
                        '&& heat stack-create {1} -f /tmp/{1}.yml'
                        .format(password, net_name, RCfile), shell = True,
                        executable = "/bin/bash") 
    except Exception as ex:
        print(ex)
        collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))

if __name__ == "__main__":
    
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-n','--net_name', type=str, help='')
    parser.add_argument('-a','--address', type=ip, help='') 
    parser.add_argument('-p','--password', type=str, help='') 
    parser.add_argument('-f','--RCfile', type=str, help='')
    # get args
    args = parser.parse_args()
    net_name = args.net_name
    address = args.address
    password = args.password
    RCfile = args.RCfile
    
    main(net_name, address, password, RCfile)
