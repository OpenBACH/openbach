#!/usr/bin/python

import threading
import socket
import shlex
import requests
import ConfigParser
from requests.exceptions import ConnectionError
import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))


class ClientThread(threading.Thread):
    def __init__(self, data, conf):
        threading.Thread.__init__(self)
        self.data = data
        self.conf = conf


    def send_stat(self, stat_name, stats):
        # recuperation des stats
        time = stats["time"]
        del stats["time"]
        stats_v09 = ''
        for k, v in stats.iteritems():
            if stats_v09 != '':
                stats_v09 += ','
            try:
                int(v)
                stats_v09 += k + "=" + v + "i"
            except:
                try:
                    float(v)
                    stats_v09 += k + "=" + v
                except:
                    boolean=['t','T','true','True','TRUE','f','F','false','False','FALSE']
                    if v in boolean:
                        stats_v09 += k + "=" + v
                    else:
                        stats_v09 += k + "=\"" + v + "\""

        # Former la commande
        url = "http://" + '127.0.0.1' + ":" + self.conf.port
        url += "/write?db=" + self.conf.database + "&precision="
        url += self.conf.time_precision + "&u=" + self.conf.username + "&p="
        url += self.conf.password
        data = stat_name + " " + stats_v09 + " " + str(time)

        # Envoyer la commande
        try:
            result = requests.post(url, data=data)
        except ConnectionError:
            result = "ConnectionError"
            print result
            return result
        return result._content


    def parse_and_check(self, r):
        data_recv = shlex.split(r)
        if (len(data_recv) < 4) | (len(data_recv)%2 != 0):
            error = "Message not formed well"
            print error
            return []
        try:
            data_recv[1] = int(data_recv[1])
        except:
            error = "Timestamp should be an int in millisecond"
            print error
            return []
        return data_recv


    def run(self): 
        data_recv = self.parse_and_check(self.data)
        if len(data_recv) == 0:
            return
        stat_name = data_recv[0]
        stats = { 'time': data_recv[1] }
        for i in range((len(data_recv) - 2)/2):
            stats[data_recv[2+2*i]] = data_recv[3+2*i]
        self.send_stat(stat_name, stats)


class Conf:
    def __init__(self, confpath="config.ini"):
        Config = ConfigParser.ConfigParser()
        Config.read(confpath)
        self.collectstats_port = Config.get('collectstats', 'port')
        self.port = Config.get('influxdb', 'port')
        self.database = Config.get('influxdb', 'database')
        self.username = Config.get('influxdb', 'username')
        self.password = Config.get('influxdb', 'password')
        self.time_precision = Config.get('influxdb', 'time_precision')


if __name__ == "__main__":
    conf = Conf("collectstats.cfg")

    udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udpsock.bind(("", int(conf.collectstats_port)))
    
    while True:
        d = udpsock.recvfrom(1024)
        data = d[0]
        newthread = ClientThread(data, conf)
        newthread.start()

