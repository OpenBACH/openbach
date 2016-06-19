#!/bin/bash

function usage(){
    printf "Utilisation of the script :\n"
    printf "\tagent_address                  : IP Address of the Agent\n"
    printf "\t-u username                    : Username of the Agent (default: opensand)\n"
    printf "\t-p password                    : Password of the Agent (default: opensand)\n"
    printf "\t--ip-auditorium ip             : IP Address of the Auditorium (default: localhost)\n"
    printf "\t--username-auditorium username : Username of the Auditorium (default: opensand)\n"
    printf "\t--password-auditorium password : Password of the Auditorium (default: opensand)\n"
    printf "\t-h                             : print this message.\n"
}

if [ $# -eq 0 ]
then
    usage
    exit 0
fi

if [ $1 = '-h' ]; then
    usage
    exit 0
fi
agent_address=$1

while true ; do
    case "$2" in
        -h) usage;
            exit 0;;
        -u)
            agent_username=$3
            shift 2;;
        -p)
            agent_password=$3
            shift 2;;
        --ip-auditorium)
            auditorium_address=$3
            shift 2;;
        --username-auditorium)
            auditorium_username=$3
            shift 2;;
        --password-auditorium)
            auditorium_password=$3
            shift 2;;
        '') break;;
        *) echo "option not found: $1"; shift;;
    esac
done

if [ -z $agent_username ]; then
    agent_username='opensand'
fi
if [ -z $agent_password ]; then
    agent_password='opensand'
fi
if [ -z $auditorium_address ]; then
    auditorium_address='127.0.0.1'
fi
if [ -z $auditorium_username ]; then
    auditorium_username='opensand'
fi
if [ -z $auditorium_password ]; then
    auditorium_password='opensand'
fi


echo "[Agents]" > configs/hosts_auditorium
echo "agents:" > configs/ips
echo "$agent_address" >> configs/hosts_auditorium
echo "  - $agent_address" >> configs/ips
echo -e "[Auditorium]\n$auditorium_address\n" > configs/hosts
echo "ansible_ssh_user: $auditorium_username" > configs/extra_vars
echo "ansible_ssh_pass: $auditorium_password" >> configs/extra_vars
echo "ansible_sudo_pass: $auditorium_password" >> configs/extra_vars
echo "agent_username: $agent_username" >> configs/extra_vars
echo "agent_password: $agent_password" >> configs/extra_vars


sudo ansible-playbook -i configs/hosts -e @configs/extra_vars -e @configs/ips install/agent.yml --tags del_agent


rm configs/hosts_auditorium configs/hosts configs/ips configs/extra_vars

