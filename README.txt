Install

To install OpenBACH, you'll need to install Ansible.
To install Ansible :
$ sudo apt-get install software-properties-common
$ sudo apt-add-repository ppa:ansible/ansible
$ sudo apt-get update
$ sudo apt-get install ansible

To use ansible, you need to install your ssh key on the remote machines you want be able to controll.
First, create your ssh key :
$ ssh-keygen -t dsa -b 1024
Then, install your ssh key on all the machine you want to controll with ansible (including your own computer if needed) (always on root user) :
$ ssh-copy-id -i ~/.ssh/id_dsa.pub root@*IP_ADDR*

First, you have to define and install the global variable of OpenBACH.
File the file group_vars/all. The defaut port for logstash elasticsearch and influxdb are filled but you can change them.
It is here you choose the database name and the username and password associate to it.
Then move the repository to /etc/ansible :
$ sudo cp -r group_vars/ /etc/ansible/

Now, you have to specify the machines you want to install OpenBACH to Ansible.
Open the hosts file :
$ vim hosts
And write the Agents, collector and controller IP.
The copy this file to the ansible repository :
# sudo cp hosts /etc/ansible/

You can now run the installation playbook :
$ ansible-playbook install_agents.yml
$ ansible-playbook install_collector.yml
$ ansible-playbook install_controller.yml

(install_stats.yml only install the stats part of OpenBACH, same for install_logs.yml and install_synchro.yml)

Now everything is install.
To see the logs in the kibana interface, go to http://*controller_ip*:5601 (5601 is the defaut port for kibana, if you choosed an other one, use it).
To see the stats in the grafana interface, go to http://*controller_ip*:3000 (3000 is the defaut port for graphana, if you choosed an other one, use it). The login/password are admin/admin. First you have to add a data source.
Choose "InfluxDB 0.9.x" as Type, Url is http://*collector_ip*:8086 (8086 is the defaut port for influxDB, if you choosed an other one, use it), InfluxDB Details are the ones you choose in /etc/ansible/group_vars/all file.
