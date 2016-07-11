#!/bin/bash
# 
#   OpenBACH is a generic testbed able to control/configure multiple
#   network/physical entities (under test) and collect data from them. It is
#   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
#   Agents (one for each network entity that wants to be tested).
#   
#   
#   Copyright © 2016 CNES
#   
#   
#   This file is part of the OpenBACH testbed.
#   
#   
#   OpenBACH is a free software : you can redistribute it and/or modify it under the
#   terms of the GNU General Public License as published by the Free Software
#   Foundation, either version 3 of the License, or (at your option) any later
#   version.
#   
#   This program is distributed in the hope that it will be useful, but WITHOUT
#   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#   
#   You should have received a copy of the GNU General Public License along with
#   this program. If not, see http://www.gnu.org/licenses/.
#   
#   
#   
#   @file     rsyslog_job.sh
#   @brief    Sources of the Job rsyslog_job
#   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>


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

