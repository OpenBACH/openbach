import subprocess
import argparse
import time
import syslog
import collect_agent

def command_line_flag_for_argument(argument, flag):
    if argument is not None:
        yield flag
        yield str(argument)

def handle_exception(exception, timestamp):
    statistics = {'status': 'Error'}
    collect_agent.send_stat(timestamp, **statistics)
    collect_agent.send_log(syslog.LOG_ERR, "ERROR: %s" % exception)


def main(destination_ip, count, interval, interface, packetsize, ttl):
    conffile = "/opt/openbach-jobs/fping/fping_rstats_filter.conf"

    cmd = ['fping', destination_ip]
    cmd.extend(command_line_flag_for_argument(count, '-c'))
    cmd.extend(command_line_flag_for_argument(interval, '-i'))
    cmd.extend(command_line_flag_for_argument(interface, '-I'))
    cmd.extend(command_line_flag_for_argument(packetsize, '-s'))
    cmd.extend(command_line_flag_for_argument(ttl, '-t'))

    success = collect_agent.register_collect(conffile)
    if not success:
        return

    #persitent jobs that only finishes when it is stopped by OpenBACH
    while True:
        timestamp = int(round(time.time() * 1000))
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as ex:
            if ex.returncode in (-15, -9):
                continue
            handle_exception(ex, timestamp)
            return
        try:
            rtt_data = output.strip().decode().split(':')[-1].split('=')[-1].split('/')[1]
        except IndexError as ex:
            handle_exception(ex, timestamp)
            return
        statistics = {'rtt': rtt_data}
        collect_agent.send_stat(timestamp, **statistics)


if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('destination_ip', metavar='destination_ip', type=str,
                        help='')
    parser.add_argument('-c', '--count', type=int,
                        help='', default=3)
    parser.add_argument('-i', '--interval', type=int,
                        help='')
    parser.add_argument('-I', '--interface', type=str,
                        help='')
    parser.add_argument('-s', '--packetsize', type=int,
                        help='')
    parser.add_argument('-t', '--ttl', type=int,
                        help='')

    # get args
    args = parser.parse_args()
    destination_ip = args.destination_ip
    count = args.count
    interval = args.interval
    interface = args.interface
    packetsize = args.packetsize
    ttl = args.ttl

    main(destination_ip, count, interval, interface, packetsize, ttl)
