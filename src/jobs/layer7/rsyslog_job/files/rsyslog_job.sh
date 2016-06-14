#!/bin/bash

if [ -z $2 ]
then
    echo "Usage: $0 job_name instance_id [disable_code]"
    echo "       disable_code = 1 to disable sending logs to the Collector"
    echo "       disable_code = 2 to disable local registery of logs"
    echo "       disable_code = 3 to disable both"
    exit 1
fi


job_name=$1
instance_id=$2
if [ -z $3 ]
then
    disable='0'
else
    disable=$3
fi


if [ $disable != '1' ] && [ $disable != '3' ]
then
    mv /etc/rsyslog.d/${job_name}${instance_id}.conf.locked /etc/rsyslog.d/${job_name}.conf
else
    mv /etc/rsyslog.d/${job_name}.conf /etc/rsyslog.d/${job_name}.conf.locked
fi

if [ $disable != '2' ] && [ $disable != '3' ]
then
    mv /etc/rsyslog.d/${job_name}${instance_id}_local.conf.locked /etc/rsyslog.d/${job_name}_local.conf
else
    mv /etc/rsyslog.d/${job_name}_local.conf /etc/rsyslog.d/${job_name}_local.conf.locked
fi

service rsyslog restart

