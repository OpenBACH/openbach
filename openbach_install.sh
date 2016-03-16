#!/bin/bash

read -s -p "SSH Password : ?" password
echo

read -s -p "Vault Password : ?" vaultPassword
echo

echo $vaultPassword > ~/.openbach-pass-vault.txt

ansible-playbook -i group_vars/all install_collector.yml  -e ansible_become_pass=$password  -e ansible_ssh_pass=$password -e ansible_sudo_pass=$password --vault-password-file ~/.openbach-pass-vault.txt -f 2 -vvvv

rm -rf  ~/.openbach-pass-vault.txt

