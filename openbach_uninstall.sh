#!/bin/bash

read -p "Controller Ip Address : ? " controller_address
if [ -z $controller_address ]
then
    echo "You should provide the IP address of the Controller"
    exit
fi
read -p "SSH Controller Username : ? " controller_username
if [ -z $controller_username ]
then
    echo "You should provide the username of the Controller"
    exit
fi
read -s -p "SSH Controller Password : ? " controller_password
echo
if [ -z $controller_password ]
then
    echo "You should provide the password of the Controller"
    exit
fi
read -p "Collector Ip Address : ? " collector_address
if [ -z $collector_address ]
then
    echo "You should provide the IP address of the Collector"
    exit
fi
read -p "SSH Collector Username : ? " collector_username
if [ -z $collector_username ]
then
    echo "You should provide the username of the Collector"
    exit
fi
read -s -p "SSH Collector Password : ? " collector_password
echo
if [ -z $collector_password ]
then
    echo "You should provide the password of the Collector"
    exit
fi

echo -e "[Controller]\n$controller_address\n" > configs/hosts
echo "controller_ip: $controller_address" > configs/ips
echo -e "[Collector]\n$collector_address" >> configs/hosts
echo "collector_ip: $collector_address" >> configs/ips


ansible-playbook -i configs/hosts -e @configs/ips -e @configs/all -e ansible_ssh_user=$controller_username -e ansible_sudo_pass=$controller_password -e ansible_ssh_pass=$controller_password install/controller.yml --tags uninstall
ansible-playbook -i configs/hosts -e @configs/ips -e @configs/all -e ansible_ssh_user=$collector_username -e ansible_sudo_pass=$collector_password -e ansible_ssh_pass=$collector_password install/collector.yml --tags uninstall

rm configs/hosts configs/ips

