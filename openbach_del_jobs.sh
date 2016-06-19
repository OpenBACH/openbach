#!/bin/bash

function usage(){
    printf "Utilisation of the script :\n"
    printf "\t-j job                         : Path to new job since src/jobs/\n"
    printf "\t--ip-controller ip             : IP Address of the Controller (default: localhost)\n"
    printf "\t--username-controller username : Username of the Controller (default: opensand)\n"
    printf "\t--password-controller password : Password of the Controller (default: opensand)\n"
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
        -j)
            jobs=`echo $jobs $2`
            shift 2;;
        --ip-controller)
            controller_address=$2
            shift 2;;
        --username-controller)
            controller_username=$2
            shift 2;;
        --password-controller)
            controller_password=$2
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


echo -e "[Controller]\n$controller_address\n" > configs/hosts
echo "ansible_ssh_user: $controller_username" > configs/extra_vars
echo "ansible_ssh_pass: $controller_password" >> configs/extra_vars
echo "ansible_sudo_pass: $controller_password" >> configs/extra_vars


for job in $jobs
do
    sudo ansible-playbook -i configs/hosts -e @configs/extra_vars -e job=$job install/job.yml --tags del_job
done

rm configs/hosts configs/extra_vars

