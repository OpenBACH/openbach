import subprocess
import argparse
import syslog
import collect_agent


def main(destination_ip, subnet_mask, gateway_ip, action):
    conffile = "/opt/openbach-jobs/ip_route/ip_route_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return


    collect_agent.send_log(syslog.LOG_INFO, "Starting ip_route")



    # Je défini une liste avec mes arguments et je fais ensuite appel à ma liste en utilisant le module subprocess

#    commande = ["route", "add", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip]
#    subprocess.check_call(commande)
#    collect_agent.send_log(syslog.LOG_INFO, "ip_route job done") 





#Fonction de définition du type ip :

def ip(argument):
    address = argument.split('.')
    if len(address) != 4:
        raise TypeError('Not an IP')

    for elem in map(int, address):
        if elem not in range(256):
            raise ValueError('Element of IP address not in range 0 to 255')

    return argument






    # Adding a new variable "action" for the addition/deletion of a route

    if action == 1 :
	#Add a route
	try:
	    subprocess.call(["route", "add", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
	    collect_agent.send_log(syslog.LOG_DEBUG, "New Route Added")
 	except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "ERROR Adding the route " + str(ex))

    else:
	#Delete a route
	try:
	    subprocess.call(["route", "del", "-net", destination_ip, "netmask", subnet_mask, "gw", gateway_ip])
	    collect_agent.send_log(syslog.LOG_DEBUG, "Route deleted")







if __name__ == "__main__":

    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', type=ip, help='')
    parser.add_argument('subnet_mask', type=ip, help='') 
    parser.add_argument('gateway_ip', type=ip, help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    subnet_mask = args.subnet_mask
    gateway_ip = args.gateway_ip

    main(destination_ip, subnet_mask, gateway_ip)
