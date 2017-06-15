#!/usr/bin/env python 
# -*- coding: utf-8 -*-
# Author:  / <@toulouse.viveris.com>

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


def main(stack_name, flavor, image_id, network_name):
    conffile = "/opt/openbach-jobs/net_create/net_create_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Stating stack_create")

    
    # Define variable net for pool address allocation

#    address.split(".")
#    net = var[0] + "." + var[1] + "." + var[2]
#    address.rsplit(".",1)
#    net = address.rsplit(".",1)
    
    # CREATE TEMPLATE

    with open(net_name + '.yml', 'w') as file :
        file.writelines('heat_template_version: 2015-04-30\n\n' + 'description:' +
                        ' Simple template to deploy a single compute
                        instance\n\n' + 'resources'+':\n\n ' + stack_name + ':\n
                        ' + '  properties:\n' + '       image'+ 
                        ' ' + '     name: ' + net_name + '\n'+' '+ '     shared: false\n'+' '+'  type: OS::Neutron::Net\n\n '+
                        'network_subnet:\n' +' '+ '  properties:\n'+' '+
                        '    allocation_pools:\n' +' '+ '    - end: ' + net[0] +
                        '.127\n' +' '+ '      start: ' + net[0] + '.2\n' +' '+ '    cidr: ' + address +
                        '/24\n' +' '+ '    dns_nameservers: []\n' +' '+
                        '    enable_dhcp: true' + '\n' +' '+ '    host_routes: []\n' +' '+
                        '    ip_version: 4' + '\n ' +'    name: '+ net_name + '\n ' +
                        '    network_id:\n ' + '      get_resource: ' + net_name +
                        '\n ' + '  type: OS::Neutron::Subnet')

   # Create stack
    try:
#        subprocess.check_call(["heat", "stack-create", net_name, "-f", "test1.yml"])
#        subprocess.check_call(["heat","stack-create" , net_name, "-f", net_name + ".yml"])
#        collect_agent.send_log(syslog.LOG_DEBUG, "New network added")
#    except Exception as ex:
#        collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))

if __name__ == "__main__":
    
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-n','--stack_name', type=str, help='')
    parser.add_argument('-f','--flavor', type=str, help='') 
    parser.add_argument('-n','--image_id', type=str, help='')
    parser.add_argument('-n','--network_name', type=str, help='')

    # get args
    args = parser.parse_args()
    stack_name = args.stack_name
    flavor = args.flavor
    image_id = args.image_id
    network = args.network

    main(stack_name, flavor, image_id, network)
