#!/bin/bash
# Tcp Buffer

# On récupère les arguments
if [ -z $4 ]
then
    echo "Usage 1: $0 name min_size size max_size"
    exit 1
fi

name=$1
min_size=$2
size=$3
max_size=$4


# On modifie la configuration de la machine
sysctl net.ipv4.tcp_$name='$min_size $size $max_size'


exit 0

