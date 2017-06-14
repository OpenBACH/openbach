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


def main(network_name, address, dhcp):
    conffile = "/opt/openbach-jobs/ip_route/ip_route_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Stating net_create")

    # Create template
    try:
        subprocess.check_call(["vim", net_name, ".yml"])
        collect_agent.send_log(syslog.LOG_DEBUG, "New network template added")
        
# là j demande au user les valeurs des parametres
     with open(''network_name'.yml', 'a') as file :
         file.writelines('heat_template_version: 2013-05-23\n' + 'description:
                         Simple template to deploy a single network instance\n'
                         + ' ' + network_name + ':\n' + '  properties:\n' +
                         '     name:' + network_name + '\n'+ '     shared:
                         false\n'+'   type: OS::Neutron::Net\n\n'+ '
                         network_subnet':\n' + '   properties:\n'+ '
                         allocation_pools:\n' +'      - end: 192.172.12.254_n'+
                         start: 192.172.12.2\n' +'      cidr:'+ address
                         +'/24\n'+'     dns_nameservers: []\n+
                         enable_dhcp:'+dhcp\n+'     host_routes: []\n+
                         ip_version: 4\n+'     name: '+ network_name\n+'
                         network_id:\n'+'       get_resource: '+network_name+\n'
                         +'    type: OS::Neutron::Subnet')
   # Create network

     subprocess.check_call(["heat stack-create", network_name, "–template", 
                            "network_name",".yml"])
     collect_agent.send_log(syslog.LOG_DEBUG, "New network added")

if __name__ == "__main__":

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-n','--network_name', type=str, help='')
    parser.add_argument('-a','--address', type=ip, help='') 
    parser.add_argument('-d','--dhcp', type=int, help='')

    # get args
    args = parser.parse_args()
    network_name = args.network_name
    address = args.subnet_address
    dhcp = args.dhcp

    main(network_name, address, dhcp)
