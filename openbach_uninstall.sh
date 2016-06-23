#!/bin/bash

function usage(){
    printf "Utilisation of the script :\n"
    printf "\t--ip-controller ip             : IP Address of the Controller (default: localhost)\n"
    printf "\t--username-controller username : Username of the Controller (default: opensand)\n"
    printf "\t--password-controller password : Password of the Controller (default: opensand)\n"
    printf "\t--ip-collector ip              : IP Address of the Collector (default: ip-controller)\n"
    printf "\t--username-collector username  : Username of the Collector (default: username-controller)\n"
    printf "\t--password-collector password  : Password of the Collector (default: password-controller)\n"
    printf "\t--ip-auditorium ip             : IP Address of the Auditorium (default: ip-controller)\n"
    printf "\t--username-auditorium username : Username of the Auditorium (default: username-controller)\n"
    printf "\t--password-auditorium password : Password of the Auditorium (default: password-controller)\n"
    printf "\t-h                             : print this message.\n"
}

if [ $# -eq 0 ]
then
    usage
    exit 0
fi


while true ; do
    case "$1" in
        -h) usage;
            exit 0;;
        --ip-controller)
            controller_address=$2
            shift 2;;
        --username-controller)
            controller_username=$2
            shift 2;;
        --password-controller)
            controller_password=$2
            shift 2;;
        --ip-collector)
            collector_address=$2
            shift 2;;
        --username-collector)
            collector_username=$2
            shift 2;;
        --password-collector)
            collector_password=$2
            shift 2;;
        --ip-auditorium)
            auditorium_address=$2
            shift 2;;
        --username-auditorium)
            auditorium_username=$2
            shift 2;;
        --password-auditorium)
            auditorium_password=$2
            shift 2;;
        '') break;;
        *) echo "option not found: $1"; shift;;
    esac
done


if [ -z $controller_address ]; then
    controller_address='127.0.0.1'
fi
if [ -z $controller_username ]; then
    controller_username='opensand'
fi
if [ -z $controller_password ]; then
    controller_password='opensand'
fi
if [ -z $collector_address ]; then
    collector_address=$controller_address
fi
if [ -z $collector_username ]; then
    collector_username=$controller_username
fi
if [ -z $collector_password ]; then
    collector_password=$controller_password
fi
if [ -z $auditorium_address ]; then
    auditorium_address=$controller_address
fi
if [ -z $auditorium_username ]; then
    auditorium_username=$controller_username
fi
if [ -z $auditorium_password ]; then
    auditorium_password=$controller_password
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
echo -e "[Auditorium]\n$auditorium_address" >> /tmp/openbach_hosts
echo "auditorium_ip: $auditorium_address" >> configs/ips

echo "ansible_ssh_user: $controller_username" > /tmp/openbach_extra_vars
echo "ansible_ssh_pass: $controller_password" >> /tmp/openbach_extra_vars
echo "ansible_sudo_pass: $controller_password" >> /tmp/openbach_extra_vars
sudo ansible-playbook -i /tmp/openbach_hosts -e @configs/ips -e @configs/all -e @/tmp/openbach_extra_vars install/controller.yml --tags uninstall

echo "ansible_ssh_user: $collector_username" > /tmp/openbach_extra_vars
echo "ansible_ssh_pass: $collector_password" >> /tmp/openbach_extra_vars
echo "ansible_sudo_pass: $collector_password" >> /tmp/openbach_extra_vars
sudo ansible-playbook -i /tmp/openbach_hosts -e @configs/ips -e @configs/all -e @/tmp/openbach_extra_vars install/collector.yml --tags uninstall $skip_tag_collector

echo "ansible_ssh_user: $auditorium_username" > /tmp/openbach_extra_vars
echo "ansible_ssh_pass: $auditorium_password" >> /tmp/openbach_extra_vars
echo "ansible_sudo_pass: $auditorium_password" >> /tmp/openbach_extra_vars
sudo ansible-playbook -i /tmp/openbach_hosts -e @configs/ips -e @configs/all -e @/tmp/openbach_extra_vars install/auditorium.yml --tags uninstall


rm /tmp/openbach_hosts configs/ips /tmp/openbach_extra_vars

