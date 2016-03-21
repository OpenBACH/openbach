#!/bin/bash

read -p "Agent Ip Address : ? " agent_address
read -p "SSH Agent Username : ? " agent_username
read -s -p "SSH Agent Password : ? " agent_password
echo
read -p "SSH Username : ? " username
read -s -p "SSH Password : ? " password
echo


ansible-playbook -i configs/hosts -e ansible_ssh_user=$username -e ansible_sudo_pass=$password -e ansible_ssh_pass=$password -e agent_address=agent_address -e agent_username=agent_username -e agent_password=agent_password install/agent.yml --tags add_agent

