#!/bin/sh

DEV="ens4"
Rate_max=512kbps
rate_q1=512kbps
delay=50ms

tc qdisc del dev $DEV root


tc qdisc add dev $DEV root handle 1: htb default 10
tc class add dev $DEV parent 1: classid 1:1 htb rate $Rate_max burst 1000b
tc class add dev $DEV parent 1:1 classid 1:10 htb rate $rate_q1 burst 1000b 
tc qdisc add dev $DEV parent 1:10 handle 10: netem delay $delay
