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


def main(interface_name, ip_address, action):
    conffile = "/opt/openbach-jobs/ifconfig/ifconfig_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_ERR, "Starting ifconfig job")
#   collect_agent.send_log(syslog.LOG_INFO,== c'etait log info avant 

##################################################


    # Je défini une liste avec mes arguments et je fais ensuite appel à ma liste en utilisant le module subprocess

#    commande = ["ifconfig", interface_name, ip_address]
#    subprocess.check_call(commande)
#    collect_agent.send_log(syslog.LOG_INFO, "ifconfig job done") 

###############################################


    # Adding a new variable "action" for the addition/deletion of an ip address

    if action == 1 :
	#Add an ip add
        try:
            subprocess.check_call(["ifconfig", interface_name, ip_address])
            collect_agent.send_log(syslog.LOG_DEBUG, "New ip address added")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))
# Essai 1 : ecriture d'une chaîne de car = OK

#        with open('/etc/network/interfaces', 'a') as file :
#            file.writelines('\niface koukou ')


##########

# Essai 2 :Remplacement D'uen CHAR :  OK
    
#         # Read in the file
#        with open('/etc/network/interfaces', 'r') as file :
#            filedata = file.read()
#         # Replace the target string
#        filedata = filedata.replace('address', 'abcd')

#         # Write the file out again
#        with open('/etc/network/interfaces', 'w') as file:
#            file.write(filedata)
#########              

# Essai 3 : Remplacement après split : OK
    
        # Read in the file                                             #rajouter
                                                                       # lacces aux fichier d conf de linterface
        with open('/etc/network/interfaces', 'r+') as file :
            l = file.readlines()
        for index, line in enumerate(l): 
            liste = line.split()
            if len(liste) > 2 and liste[1] == interface_name :
                l[index+1] = '    address ip_address\n'       # rajouter ip_add
                                                              # en tant qu'argument
        with open('/etc/network/interfaces', 'w') as file :        
            file.writelines(l)
         

#########


#'iface 'interface_name' inet static\n     address 'ip_address'\n     netmask 255.255.255.0\n'
 
    else:
	#Delete an interface's ip address
        try:
            subprocess.check_call(["ifconfig", interface_name, "0"])
            collect_agent.send_log(syslog.LOG_DEBUG, "ip address deleted")
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR" + str(ex))

##################################################################################
#ou bien changer le repertoire 
#import os
#os.chdir("/etc")   #pr me positionner dans un repertoire

#fichier = sudo open("/etc/network/interfaces","a")  # a pr append car le fichier existe deja
#fichier.writelines('iface 'interface_name' inet static\n     address 'ip_address'\n     netmask 255.255.255.0\n')

#fichier.close()
########################################################################

if __name__ == "__main__":

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('interface_name', type=str, help='')
    parser.add_argument('-i','--ip_address', type=ip, help='') 
    parser.add_argument('-a', '--action', type=int, default=1, help='')
   
    # get args
    args = parser.parse_args()
    interface_name = args.interface_name
    ip_address = args.ip_address
    action = args.action

    main(interface_name, ip_address, action)
