import subprocess
import argparse
import syslog
import collect_agent


"""
def command_line_flag_for_argument(argument, flag):
    if argument is not None:
        yield flag
        yield str(argument)
"""
"""def handle_exception(exception, timestamp):
    statistics = {'status': 'Error'}
    collect_agent.send_stat(timestamp, **statistics)
    collect_agent.send_log(syslog.LOG_ERR, "ERROR: %s" % exception)
"""

def main(destination_ip, subnet_Mask, Gatewap_ip):
    conffile = "/opt/openbach-jobs/ip_route/ip_route_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not succes:
        return

    collect_agent.send_log(syslog.LOG_INFO, "Starting ip_route")

    cmd = ['ip_route', destination_ip]
    cmd = ['ip_route', Subnet_Mask]
    cmd = ['ip_route', Gateway_ip]


    #non persitent jobs that finishes without being stopped manually

if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', type=int,
                        help='')
    parser.add_argument('Subnet_Mask', type=int,
                        help='') 
    parser.add_argument('Gateway_ip', type=int,
                        help='')


    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    Subnet_Mask = args.Subnet_Mask
    Gateway_ip = args.Gateway_ip
    

    main(destination_ip, Subnet_Mask, Gateway_ip)
