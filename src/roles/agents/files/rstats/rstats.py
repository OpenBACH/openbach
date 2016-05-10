#!/usr/bin/python

import threading
import logging
import socket
import ConfigParser
import shlex
import requests
from requests.exceptions import ConnectionError
import resource
resource.setrlimit(resource.RLIMIT_NOFILE, (65536, 65536))


class Rstats:
    DefaultLogPath = "/var/log/rstats.log"
    
    def __init__(self, logpath=DefaultLogPath, confpath="", conf=None,
                 prefix=None, id=None):
        self.__mutex = threading.Lock()
        self.conf = conf
        if prefix == None:
            f = open("/etc/hostname", "r")
            self.prefix = f.readline().split('\n')[0]
            f.close()
        else:
            self.prefix = prefix
        
        if id != None:
            self._logger = logging.getLogger('Rstats' + str(id))
        else:
            self._logger = logging.getLogger('Rstats')
        self._logger.setLevel(logging.INFO)
        try:
            fhd = logging.FileHandler(logpath, mode="a")
            fhd.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            self._logger.addHandler(fhd)
        except:
            pass
         
        self._confpath = confpath
        self._filter = None
        self.reload_conf()
        
    def _send_stat(self, stat_name, stats):
        self.__mutex.acquire()
        local = self._filter.is_denied(stat_name)
        self.__mutex.release()
        if self.prefix != None:
            stat_name = self.prefix + '.' + stat_name
        else:
            stat_name = stat_name
        
        # recuperation des stats
        time = stats["time"]
        del stats["time"]
        logs = 'Stat: ' + str(stat_name) + ', Time: ' + str(time)
        stats_names = "\"time\""
        stats_values = str(time)
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
            stats_names += ",\"" + k + "\""
            stats_values += ",\"" + v + "\""
            logs += ", " + k + ": " + v

        self._logger.info(logs)
        if local:
            return []

        # Former la commande
        if self.conf.influxdb_version == '0.9' or self.conf.influxdb_version == '0.10':
            url = "http://" + self.conf.host + ":" + self.conf.port
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
        if len(result._content) != 0:
            self._logger.error(result._content)
        return result._content
 

    def reload_conf(self):
        self.__mutex.acquire()
        self._logger.info("Load new configuration:")

        self._filter = RstatsFilter()
        load_filter_from_conf(self._filter, self._confpath)

        for line in str(self._filter).splitlines():
            self._logger.info("    %s" % line)
        self.__mutex.release()


class Conf:
    def __init__(self, confpath="config.ini"):
        Config = ConfigParser.ConfigParser()
        Config.read(confpath)
        self.host = Config.get('influxdb', 'host')
        self.port = Config.get('influxdb', 'port')
        self.database = Config.get('influxdb', 'database')
        self.username = Config.get('influxdb', 'username')
        self.password = Config.get('influxdb', 'password')
        self.time_precision = Config.get('influxdb', 'time_precision')
        self.influxdb_version = Config.get('influxdb', 'version')


class RstatsRule:
    ACCEPT = True
    DENY = False

    def __init__(self, name, status=ACCEPT):
        self._name = name
        self._status = status

    def get_name(self):
        return self._name

    def get_status(self):
        return self._status

    def match(self, name):
        return (self._name == name)

    def __str__(self):
        if (self._status == RstatsRule.ACCEPT):
            return "ACCEPT %s" % self._name
        else:
            return "DENY %s" % self._name


class RstatsFilter:

    def __init__(self, default=RstatsRule.ACCEPT):
        self._default = default
        self._rules = [ ]

    def get_default(self):
        return self._default

    def set_default(self, status):
        self._default = status

    def get_rules(self):
        return self._rules

    def _get_status_for(self, name):
        # Find matching rule
        matched = False
        i = 0
        while not matched and i < len(self._rules):
            matched = self._rules[i].match(name)
            i = i + 1

        # Check default case
        if not matched:
            return self._default

        return self._rules[i - 1].get_status()

    def is_accepted(self, name):
        return (self._get_status_for(name) == RstatsRule.ACCEPT)

    def is_denied(self, name):
        return (self._get_status_for(name) == RstatsRule.DENY)

    def __str__(self):
        i = 0
        text = ""
        for rule in self._rules:
            text = "%s[%d] %s\n" % (text, i, str(rule))
            i = i + 1
        rule = RstatsRule("default", self._default)
        text = "%s[%d] %s" % (text, i, str(rule))
        return text


def load_filter_from_conf(filter, filepath):
    # Read file lines
    try:
        f = open(filepath, "r")
        lines = f.read().splitlines()
    except Exception as ex:
        return False, "Unable to read \"%s\"\n%s" % (filepath, str(ex))

    # Parse section
    step_error = -1
    step_check = 0
    step_section = 1
    step_parameter = 2
    step_end = 4

    step = step_check
    i = -1
    description = ""
    name = ""
    line = ""
    while step != step_end and step != step_error:

        if step == step_check:
            # Next line
            i = i + 1

            # Check end
            if len(lines) <= i:
                step = step_end
                continue

            # Check empty line
            if len(lines[i]) <= 0:
               continue

            # Clean line
            line = lines[i]
            try:
                j = line.index('#')
            except:
                j = -1
            if 0 < j:
                line = line[0:j]
            line = line.strip()

            # Check section
            if  line[0] == '[':
                step = step_section
            else:
                step = step_parameter

        elif step == step_section:

            # Parse section
            j = line.index(']')
            if j < 0:
                step = step_error
                description = "Erroneous section"
                continue

            name = line[1:j].strip()
            step = step_check

        elif step == step_parameter:

            # Parse parameter
            dummy = line.split('=')
            if len(dummy) != 2:
                step = step_error
                description = "Erroneous parameter"
                continue
            dummy[0] = dummy[0].strip()
            dummy[1] = dummy[1].strip()

            if dummy[0] != "enabled":
                step = step_error
                description = "Unknown parameter \"%s\"" % dummy[0]
                continue

            status = RstatsRule.ACCEPT
            if dummy[1] == "true" or dummy[1] == "True":
                status = RstatsRule.ACCEPT
            elif dummy[1] == "false" or dummy[1] == "False":
                status = RstatsRule.DENY
            else:
                step = step_error
                description = "Unknown value \"%s\" for parameter \"%s\"" % (dummy[1], dummy[0])
                continue

            if name != "default":
                filter.get_rules().append(RstatsRule(name, status))
            else:
                filter.set_default(status)
            step = step_check

    if step == step_error:
        message = "Invalid line %d" % i
        if 0 < len(description):
            message = "%s\n%s" % (message, description)
        return False, message

    return True, ""


class ClientThread(threading.Thread):
    def __init__(self, ip, port, clientsocket, conf):
        threading.Thread.__init__(self)
        self.ip = ip
        self.port = port
        self.clientsocket = clientsocket
        self.conf = conf
        
    def parse_and_check(self, r):
        data_recv = shlex.split(r)
        try:
            request_type = int(data_recv[0])
            data_recv[0] = request_type
        except:
            self.clientsocket.send("KO Type not recognize")
            self.clientsocket.close()
            return []
        if request_type == 1:
            if len(data_recv) != 2 and len(data_recv) != 3:
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
        elif request_type == 2:
            if (len(data_recv) < 6) or (len(data_recv)%2 != 0):
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
            try:
                int(data_recv[1])
                int(data_recv[3])
            except:
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
        elif request_type == 3:
            if len(data_recv) != 2:
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
            try:
                int(data_recv[1])
            except:
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
        elif request_type == 4:
            if len(data_recv) != 1:
                self.clientsocket.send("KO Message not formed well")
                self.clientsocket.close()
                return []
        else:
            self.clientsocket.send("KO Request type unknown")
            self.clientsocket.close()
            return []
        return data_recv
            

    def run(self): 
        global dict_statsclient
        global mutex_dict
        global last_id
        r = self.clientsocket.recv(2048)

        data_recv = self.parse_and_check(r)
        if len(data_recv) == 0:
            return
        request_type = int(data_recv[0])
        if request_type == 1:
            last_id += 1
            # creer le rstatsclient
            if len(data_recv) == 2:
                stats_client = Rstats(confpath=data_recv[1], conf=self.conf,
                                      id=last_id)
            else:
                stats_client = Rstats(confpath=data_recv[1],
                                      prefix=data_recv[2], conf=self.conf,
                                      id=last_id)
            # creer un mutex associe
            stats_client_mutex = threading.Lock()
            # ajouter le rstatsclient et son mutex au dict
            mutex_dict.acquire()
            dict_statsclient[last_id] = [stats_client, stats_client_mutex]
            mutex_dict.release()
            # envoyer OK
            self.clientsocket.send("OK " + str(last_id))
            self.clientsocket.close()
        elif request_type == 2:
            # recuperer le rstatsclient et son mutex
            mutex_dict.acquire()
            if int(data_recv[1]) in dict_statsclient:
                (stats_client, stats_client_mutex) = dict_statsclient[int(data_recv[1])]
            else:
                self.clientsocket.send("KO The given id doesn't represent an"
                                       " open connexion")
                self.clientsocket.close()
                mutex_dict.release()
                return
            mutex_dict.release()
            # recuperer les stats
            nb_stats = (len(data_recv) - 4) / 2
            stats = {}
            for i in range(nb_stats):
                stats[data_recv[4+2*i]] = data_recv[5+2*i]
            stats["time"] = data_recv[3]
            # send les stats
            stats_client_mutex.acquire()
            result = stats_client._send_stat(data_recv[2], stats)
            stats_client_mutex.release()
            # envoyer OK
            if len(result) == 0:
                self.clientsocket.send("OK")
            else:
                self.clientsocket.send("KO : " + result)
            self.clientsocket.close()
        elif request_type == 3:
            # recuperer le rstatsclient et son mutex
            mutex_dict.acquire()
            if int(data_recv[1]) in dict_statsclient:
                (stats_client, stats_client_mutex) = dict_statsclient[int(data_recv[1])]
            else:
                self.clientsocket.send("KO The given id doesn't represent an"
                                       " open connexion")
                self.clientsocket.close()
                mutex_dict.release()
                return
            mutex_dict.release()
            # reload la conf
            stats_client_mutex.acquire()
            stats_client.reload_conf()
            stats_client_mutex.release()
            # envoyer OK
            self.clientsocket.send("OK")
            self.clientsocket.close()
        elif request_type == 4:
            mutex_dict.acquire()
            for k, v in dict_statsclient.iteritems():
                stats_client = v[0]
                stats_client_mutex = v[1]
                # relad la conf
                stats_client_mutex.acquire()
                stats_client.reload_conf()
                stats_client_mutex.release()
            mutex_dict.release()
            # envoyer OK
            self.clientsocket.send("OK")
            self.clientsocket.close()


if __name__ == "__main__":
    tcpsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcpsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcpsock.bind(("",1111))
    num_connexion_max = 1000
    tcpsock.listen(num_connexion_max)

    global dict_statsclient
    global mutex_dict
    global last_id
    dict_statsclient = {}
    mutex_dict = threading.Lock()
    last_id = 0
    
    conf = Conf("rstats.cfg")

    while True:
        (clientsocket, (ip, port)) = tcpsock.accept()
        newthread = ClientThread(ip, port, clientsocket, conf)
        newthread.start()
    
