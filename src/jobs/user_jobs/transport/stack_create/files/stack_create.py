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


def main(stack_name, flavor, image_id, network_name):
    conffile = "/opt/openbach-jobs/stack_create/stack_create_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Stating stack_create")

    
    # CREATE TEMPLATE
    

    with open("/tmp/" + net_name + '.yml', 'w') as file :
        file.writelines('''\
heat_template_version: 2015-04-30
                        
description: Simple template to deploy a single compute instance
                        
resources:
  {0}                        
    type: OS::Neutron::Server
    properties:
      image : {1}
      flavor: {2}
      networks:
        -network:{3}
        -network:'''.format(stack_name, image_id, flavor, network))
        

   # Create stack
    try:
        print("vri")
        subprocess.check_call('echo "{0}" | source /tmp/CNES-openrc.sh '
                              '&& heat stack-create {1} -f /tmp/{1}.yml'
                              .format(password, net_name))
        collect_agent.send_log(syslog.LOG_DEBUG, "New stack added")
    except Exception as ex:
        print(ex)
        collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))




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
