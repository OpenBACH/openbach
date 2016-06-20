#!/bin/bash
# set PEP

# On récupère les arguments
if [ -z $1 ]
then
    echo "Usage: $0 sat_network [pep_port]"
    exit 1
fi
sat_network=$1
if [ -z $2 ]
then
    PORT_PEP=5002
else
    PORT_PEP=$2
fi

# On modifie la configuration de la machine
# set routing
ip rule add fwmark 1 lookup 100
ip route add local 0.0.0.0/0 dev lo table 100

# enlarge window buffer
echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_mem
echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_rmem
echo "8192 2100000 8400000" >/proc/sys/net/ipv4/tcp_wmem

# optimize incoming connections
iptables -A PREROUTING -t mangle -p tcp -m tcp -s $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1
iptables -A PREROUTING -t mangle -p tcp -m tcp -d $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1

# Lancer le Pep
pepsal -d -p $PORT_PEP

exit 0

