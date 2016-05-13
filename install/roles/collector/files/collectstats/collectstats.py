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
    def __init__(self, conf):
        threading.Thread.__init__(self)
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
            error = "ConnectionError"
            print error
            return error
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

    def check_and_send(self, data):
        data_recv = self.parse_and_check(data)
        if len(data_recv) == 0:
            return False
        stat_name = data_recv[0]
        stats = { 'time': data_recv[1] }
        for i in range((len(data_recv) - 2)/2):
            stats[data_recv[2+2*i]] = data_recv[3+2*i]
        self.send_stat(stat_name, stats)
        return True


class ClientThreadTcp(ClientThread):
    def __init__(self, clientsocket, conf):
        ClientThread.__init__(self, conf)
        self.clientsocket = clientsocket

    def run(self):
        r = self.clientsocket.recv(2048)
        response = self.check_and_send(r)
        if not response:
            self.clientsocket.send("KO")
            self.clientsocket.close()
            return
        self.clientsocket.send("OK")
        self.clientsocket.close()


class ClientThreadUdp(ClientThread):
    def __init__(self, data, conf):
        ClientThread.__init__(self, conf)
        self.data = data

    def run(self):
        return self.check_and_send(self.data)


class TcpThread(threading.Thread):
    def __init__(self, tcpsock):
        threading.Thread.__init__(self)
        self.tcpsock = tcpsock

    def run(self):
        while True:
            (clientsocket, (ip, port)) = tcpsock.accept()
            newthread = ClientThreadTcp(clientsocket, conf)
            newthread.start()


class UdpThread(threading.Thread):
    def __init__(self, udpsock):
        threading.Thread.__init__(self)
        self.udpsock = udpsock
    
    def run(self):
        while True:
            d = self.udpsock.recvfrom(1024)
            data = d[0]
            newthread = ClientThreadUdp(data, conf)
            newthread.start()


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

    # Creer la socket udp
    udpsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udpsock.bind(("", int(conf.collectstats_port)))

    # Creer la socket tcp
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.bind(("", int(conf.collectstats_port)))
    num_connexion_max = 1000
    tcpsock.listen(num_connexion_max)

    # Lancer l'ecoute sur les deux sockets
    newthread_tcp = TcpThread(tcpsock)
    newthread_tcp.start()
    newthread_udp = UdpThread(udpsock)
    newthread_udp.start()

