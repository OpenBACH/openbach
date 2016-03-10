#!/bin/bash
# Initial Windows

# On récupère les arguments
if [ -z $5 ]
then
    echo "Usage 1: $0 network gw interface initcwnd initrwnd"
    exit 1
fi

network=$1
gw=$2
interface=$3
initcwnd=$4
initrwnd=$5


# On modifie la configuration de la machine
ip route change $network via $gw dev $interface initcwnd $initcwnd initrwnd $initrwnd

exit 0

