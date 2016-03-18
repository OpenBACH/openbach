#!/bin/bash
# Initial Spreading Fq

# On récupère les arguments
if [ -z $3 ]
then
    echo "Usage 1: $0 rate disable_pacing interface1 [interface2 ...]"
    exit 1
fi

rate=$1
disable_pacing=$2
shift
shift


# On modifie la configuration de la machine
sysctl net.ipv4.tcp_initial_spreading_rate_min=$rate
for interface in "$@"
do
    tc qdisc add dev $interface root fq
done
sysctl net.ipv4.tcp_disable_pacing=$disable_pacing


exit 0

