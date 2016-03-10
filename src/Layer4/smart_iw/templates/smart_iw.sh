#!/bin/bash
# Smart IW

# On récupère les arguments
if [ -z $2 ]
then
    echo "Usage 1: $0 size disable_pacing"
    exit 1
fi

size=$1
disable_pacing=$2


# On modifie la configuration de la machine
sysctl net.ipv4.tcp_smart_iw=$size
sysctl net.ipv4.tcp_disable_pacing=$disable_pacing


exit 0

