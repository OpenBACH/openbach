#!/bin/bash

read -p "Agent Ip Address : " agent_address
if [ -z $agent_address ]
then
    echo "You should provide at least one IP address"
    exit
fi
echo "[Agents]" > configs/hosts_controller
echo "agents:" > configs/ips
while [ ! -z $agent_address ]
do
    echo "$agent_address" >> configs/hosts_controller
    echo "  - $agent_address" >> configs/ips
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
echo "ansible_ssh_user: $username" > configs/extra_vars
echo "ansible_ssh_pass: $password" >> configs/extra_vars
echo "ansible_sudo_pass: $password" >> configs/extra_vars
echo "agent_username: $agent_username" >> configs/extra_vars
echo "agent_password: $agent_password" >> configs/extra_vars


ansible-playbook -i configs/hosts -e @configs/extra_vars -e @configs/ips install/agent.yml --tags del_agent


rm configs/hosts_controller configs/hosts configs/ips configs/extra_vars

