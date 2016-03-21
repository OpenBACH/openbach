#!/bin/bash

read -p "SSH Username : ? " username
read -s -p "SSH Password : ? " password
echo


ansible-playbook -i configs/hosts -e @configs/all -e ansible_ssh_user=$username -e ansible_sudo_pass=$password -e ansible_ssh_pass=$password install/site.yml --tags uninstall

