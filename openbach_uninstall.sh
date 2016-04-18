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


list_local_ip=`hostname -I`
skip_tag_controller=""
for ip in $list_local_ip
do
    if [ $controller_address = $ip ]
    then
        skip_tag_controller="--skip-tag only-controller"
    fi
done


echo -e "[Controller]\n$controller_address\n" > /tmp/openbach_hosts
echo "controller_ip: $controller_address" > configs/ips
echo -e "[Collector]\n$collector_address" >> /tmp/openbach_hosts
echo "collector_ip: $collector_address" >> configs/ips


echo "ansible_ssh_user: $controller_username" > /tmp/openbach_extra_vars
echo "ansible_ssh_pass: $controller_password" >> /tmp/openbach_extra_vars
echo "ansible_sudo_pass: $controller_password" >> /tmp/openbach_extra_vars
sudo ansible-playbook -i /tmp/openbach_hosts -e @configs/ips -e @configs/all -e @/tmp/openbach_extra_vars install/controller.yml --tags uninstall


echo "ansible_ssh_user: $collector_username" > /tmp/openbach_extra_vars
echo "ansible_ssh_pass: $collector_password" >> /tmp/openbach_extra_vars
echo "ansible_sudo_pass: $collector_password" >> /tmp/openbach_extra_vars
sudo ansible-playbook -i /tmp/openbach_hosts -e @configs/ips -e @configs/all -e @/tmp/openbach_extra_vars install/collector.yml --tags uninstall $skip_tag_collector

rm /tmp/openbach_hosts configs/ips /tmp/openbach_extra_vars

