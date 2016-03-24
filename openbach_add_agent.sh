#!/bin/bash

read -p "Agent Ip Address : " agent_address
if [ -z $agent_address ]
then
    echo "You should provide at least one IP address"
    exit
fi
echo "[Agents]" > configs/hosts_controller
while [ ! -z $agent_address ]
do
    echo "$agent_address" >> configs/hosts_controller
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
read -p "Controller Ip Address : " controller_address
if [ -z $controller_address ]
then
    echo "You should provide the IP address of the Controller"
    exit
fi
read -p "SSH Controller Username : " username
if [ -z $username ]
then
    echo "You should provide the username of the Controller"
    exit
fi
read -s -p "SSH Controller Password : ? " password
echo
if [ -z $password ]
then
    echo "You should provide the password of the Controller"
    exit
fi
echo -e "[Controller]\n$controller_address\n" > configs/hosts
echo "controller_ip: $controller_address" > configs/ips
echo "collector_ip: $collector_address" > configs/ips


ansible-playbook -i configs/hosts -e ansible_ssh_user=$username -e ansible_sudo_pass=$password -e ansible_ssh_pass=$password -e agent_username=$agent_username -e agent_password=$agent_password install/agent.yml --tags add_agent

rm configs/hosts_controller configs/hosts configs/ips

