#!/bin/bash

read -p "Controller Ip Address : " controller_address
if [ -z $controller_address ]
then
    echo "You should provide the IP address of the Controller"
    exit
fi
read -p "SSH Controller Username : " controller_username
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
read -p "Collector Ip Address : " collector_address
if [ -z $collector_address ]
then
    echo "You should provide the IP address of the Collector"
    exit
fi
read -p "SSH Collector Username : " collector_username
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

if [ $controller_address != $collector_address ]
then
    skip_tag_collector=""
else
    skip_tag_collector="--skip-tag only-collector"
fi

list_local_ip=`hostname -I`
skip_tag_controller=""
for ip in $list_local_ip
do
    if [ $controller_address = $ip ]
    then
        skip_tag_controller="--skip-tag only-controller"
    fi
done


echo -e "[Controller]\n$controller_address\n" > configs/hosts
echo "controller_ip: $controller_address" > configs/ips
echo -e "[Collector]\n$collector_address" >> configs/hosts
echo "collector_ip: $collector_address" >> configs/ips


echo "local_username:" `whoami` > configs/extra_vars
echo "ansible_ssh_user: $controller_username" >> configs/extra_vars
echo "ansible_ssh_pass: $controller_password" >> configs/extra_vars
echo "ansible_sudo_pass: $controller_password" >> configs/extra_vars
ansible-playbook -i configs/hosts -e @configs/ips -e @configs/all -e @configs/extra_vars install/controller.yml --tags install $skip_tag_controller


echo "local_username:" `whoami` > configs/extra_vars
echo "ansible_ssh_user: $collector_username" >> configs/extra_vars
echo "ansible_ssh_pass: $collector_password" >> configs/extra_vars
echo "ansible_sudo_pass: $collector_password" >> configs/extra_vars
ansible-playbook -i configs/hosts -e @configs/ips -e @configs/all -e @configs/extra_vars install/collector.yml --tags install $skip_tag_collector

rm configs/hosts configs/ips configs/extra_vars

