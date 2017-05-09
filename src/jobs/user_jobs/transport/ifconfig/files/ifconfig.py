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


def main(interface_name, ip_address):
    conffile = "/opt/openbach-jobs/ifconfig/ifconfig_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Starting ifconfig job")
#   collect_agent.send_log(syslog.LOG_INFO,== c'etait log info avant 




    # Je défini une liste avec mes arguments et je fais ensuite appel à ma liste en utilisant le module subprocess

    commande = ["ifconfig", interface_name, ip_address]
    subprocess.check_call(commande)
    collect_agent.send_log(syslog.LOG_INFO, "ifconfig job done") 


######################################

#    # Adding a new variable "action" for the addition/deletion of a route
#
#    if action == 1 :
#	#Add a route
#        try:
#            subprocess.check_call(["route", "add", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
#            collect_agent.send_log(syslog.LOG_DEBUG, "New Route Added")
#        except Exception as ex:
#            collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))
#
#    else:
#	#Delete a route
#        try:
#            subprocess.check_call(["route", "del", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
#            collect_agent.send_log(syslog.LOG_DEBUG, "Route deleted")
#        except Exception as ex:
#            collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))

########################################






if __name__ == "__main__":

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('interface_name', type=str, help='')
    parser.add_argument('ip_address', type=ip, help='') 

    # get args
    args = parser.parse_args()
    interface_name = args.interface_name
    ip_address = args.ip_address

    main(interface_name, ip_address)

