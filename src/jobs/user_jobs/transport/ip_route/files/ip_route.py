#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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


def main(destination_ip, subnet_mask, gateway_ip, action, default_gateway, default_gw_name):
    conffile = "/opt/openbach-jobs/ip_route/ip_route_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Starting ip_route")

# """""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
    # Je défini une liste avec mes arguments et je fais ensuite appel à ma liste en utilisant le module subprocess

#    commande = ["route", "add", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip]
#    subprocess.check_call(commande)
#    collect_agent.send_log(syslog.LOG_INFO, "ip_route job done") 

# """"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""
    # Adding a new variable "action" for the addition/deletion of a route
    if action == 1:
       if default_gateway == 1:
           #Add a default gateway
           try:
               subprocess.check_call(["route", "add", "default", "gw", destination_ip, default_gw_name])
               collect_agent.send_log(syslog.LOG_DEBUG, "New default route added")
           except Exception as ex:
               collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))
       else:
           #Add a normal route
           try:
               subprocess.check_call(["route", "add", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
               collect_agent.send_log(syslog.LOG_DEBUG,  "Route Added")
           except Exception as ex:
               collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))

    else:
       if  default_gateway == 1:
           #delete a default gateway
           try:
               subprocess.check_call(["route", "del", "default", "gw", destination_ip, default_gw_name])
               collect_agent.send_log(syslog.LOG_DEBUG, "Default Route deleted")
           except Exception as ex:
               collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))
       else:
           #Delete a normal route
           try:
               subprocess.check_call(["route", "del", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
               collect_agent.send_log(syslog.LOG_DEBUG, "Route deleted")
           except Exception as ex:
               collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))




if __name__ == "__main__":

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i','--destination_ip', type=ip, help='')
    parser.add_argument('-s','--subnet_mask', type=ip, help='') 
    parser.add_argument('-g','--gateway_ip', type=ip, help='')
    parser.add_argument('-a', '--action', type=int, help='')
    parser.add_argument('-d', '--default_gateway', type=int, help='')
    parser.add_argument('-b', '--default_gw_name', type=str, help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    subnet_mask = args.subnet_mask
    gateway_ip = args.gateway_ip
    action = args.action
    default_gateway = args.default_gateway
    default_gw_name = args.default_gw_name

    main(destination_ip, subnet_mask, gateway_ip, action, default_gateway, default_gw_name)
