#!/bin/bash


read -p "Path to job since src/jobs/ : " job
if [ -z $job ]
then
    echo "You should provide at least one path"
    exit
fi
while [ ! -z $job ]
do
    jobs=`echo $jobs $job`
    read -p "Path to job since src/jobs/ : " job
done

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


for job in $jobs
do
    ansible-playbook -i configs/hosts -e ansible_ssh_user=$username -e ansible_sudo_pass=$password -e ansible_ssh_pass=$password -e job=$job install/job.yml --tags del_job
done

rm configs/hosts
