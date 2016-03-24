#!/bin/bash

read -p "Agent Ip Address : " agent_address
if [ -z $agent_address ]
then
    echo "You should provide at least one IP address"
    exit
fi
echo "[Agents]" > /tmp/openbach_hosts
while [ ! -z $agent_address ]
do
    echo "$agent_address" >> /tmp/openbach_hosts
    read -p "Agent Ip Address : " agent_address
done
read -p "SSH Agents Username : " agent_username
if [ -z $agent_username ]
then
    echo "You should provide the username of the Agents"
    exit
fi
read -s -p "SSH Agents Password : ? " agent_password
echo
if [ -z $agent_password ]
then
    echo "You should provide the password of the Agents"
    exit
fi
read -p "Collector Ip Address : " collector_address
if [ -z $collector_address ]
then
    echo "You should provide the IP address of the Controller"
    exit
fi
echo "collector_ip: $collector_address" > /tmp/openbach_ips


ansible-playbook -i /tmp/openbach_hosts -e @/tmp/openbach_ips -e @/opt/openbach/configs/all -e ansible_ssh_user=$agent_username -e ansible_sudo_pass=$agent_password -e ansible_ssh_pass=$agent_password /opt/openbach/agent.yml --tags install

rm /tmp/openbach_hosts /tmp/openbach_ips

