#!/bin/bash
# unset PEP for the ST

# On récupère les arguments
if [ -z $1 ]
then
    echo "Usage: $0 sat_network"
    exit 1
fi
sat_network=$1
if [ -z $2 ]
then
    PORT_PEP=5002
else
    PORT_PEP=$2
fi


# Stopper le Pep
pkill pepsal

# flush existing tables
iptables -D PREROUTING -t mangle -p tcp -m tcp -s $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1
iptables -D PREROUTING -t mangle -p tcp -m tcp -d $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1

