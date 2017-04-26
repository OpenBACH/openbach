import subprocess
import argparse
import syslog
import collect_agent


def main(destination_ip, subnet_Mask, Gatewap_ip):
    conffile = "/opt/openbach-jobs/ip_route/ip_route_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)     
    if not success:
        return

    collect_agent.send_log(syslog.LOG_INFO, "Starting ip_route")

    # Je défini une liste avec mes arguments et je fais ensuite appel à ma liste en utilisant le module subprocess
    commande = ["route", "add", "-net", destination_ip, "netmask", Subnet_Mask, "gw", Gateway_ip]
    subprocess.check_call(commande)

    collect_agent.send_log(syslog.LOG_INFO, "ip_route job done") 


def ip(argument):
    address = argument.split('.')
    if len(address) != 4:
        raise TypeError('Not an IP')

    for elem in map(int, address):
        if elem not in range(256):
            raise ValueError('Element of IP address not in range 0 to 255')

    return argument


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', type=ip, help='')
    parser.add_argument('Subnet_Mask', type=ip, help='') 
    parser.add_argument('Gateway_ip', type=ip, help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    Subnet_Mask = args.Subnet_Mask
    Gateway_ip = args.Gateway_ip

    main(destination_ip, Subnet_Mask, Gateway_ip)
