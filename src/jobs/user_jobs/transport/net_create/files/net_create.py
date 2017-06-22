#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author:  / <@toulouse.viveris.com>

import os
import subprocess
import argparse
import syslog
import collect_agent

#Fonction de définition du type ip :

def ip(argument):
    address = argument.split('.')
    if len(address) != 4:
        raise TypeError('Not an IP')

    for elem in map(int, address):
        if elem not in range(256):
            raise ValueError('Element of IP address not in range 0 to 255')

    return argument


def main(net_name, address, password, RCfile):
    conffile = "/opt/openbach-jobs/net_create/net_create_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Stating net_create")

    
    # Define variable net for pool address allocation

#    address.split(".")
#    net = var[0] + "." + var[1] + "." + var[2]
    address.rsplit(".",1)
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
        
        
        # file.writelines('heat_template_version: 2013-05-23\n\n' + 'description:'
                        # + ' Simple template to deploy a single network instance\n\n' + 'resources'+':\n\n' + ' ' + net_name + ':\n' + 
                        # ' ' + '  properties:\n' + ' '+'     admin_state_up: true\n' + 
                        # ' ' + '     name: ' + net_name + '\n'+' '+ '     shared: false\n'+' '+'  type: OS::Neutron::Net\n\n '+
                        # 'network_subnet:\n' +' '+ '  properties:\n'+' '+
                        # '    allocation_pools:\n' +' '+ '    - end: ' + net[0] +
                        # '.127\n' +' '+ '      start: ' + net[0] + '.2\n' +' '+ '    cidr: ' + address +
                        # '/24\n' +' '+ '    dns_nameservers: []\n' +' '+
                        # '    enable_dhcp: true' + '\n' +' '+ '    host_routes: []\n' +' '+
                        # '    ip_version: 4' + '\n ' +'    name: '+ net_name + '\n ' +
                        # '    network_id:\n ' + '      get_resource: ' + net_name +
                        # '\n ' + '  type: OS::Neutron::Subnet')

   # Create network
  
    try:
        # cmd = "echo " +  password + "|" + "source /home/exploit/CNES-openrc.sh"
        # print(cmd)
        # subprocess.check_call(cmd, shell=True, executable='/bin/bash')
        # cmd2 = "heat" " stack-create " + net_name + " -f " + "/tmp/" + net_name + ".yml"
        # print (cmd2)
        #subprocess.check_call(["heat", "stack-create", net_name, "-f", "test1.yml"])
        #subprocess.check_call(cmd2, shell=True, executable='/bin/bash')

#        subprocess.check_call('echo "{0}" | source /tmp/CNES-openrc.sh '
#                              '&& heat stack-create {1} -f /tmp/{1}.yml'
#                              .format(password, net_name),shell = True,
#                              executable = "/bin/bash")
        
         subprocess.check_call('echo "{0}" | source {2} '
                              '&& heat stack-create {1} -f /tmp/{1}.yml'
                              .format(password, net_name, RCfile),shell = True,
                              executable = "/bin/bash") 
 


    #Add path to the rc file : 
    #    subprocess.check_call('echo "{0}" | source /tmp/{2}.sh '
    #                          '&& heat stack-create {1} -f /tmp/{1}.yml'
    #                          .format(password, net_name, RCfile))
        collect_agent.send_log(syslog.LOG_DEBUG, "New network stack added")
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
