#!/bin/bash

if [ -z $2 ]
then
    echo "Usage: $0 job_name instance_id"
    exit 1
fi
job_name=$1
instance_id=$2


mv /opt/openbach-jobs/${job_name}/${job_name}${instance_id}_rstats_filter.conf.locked /opt/openbach-jobs/${job_name}/${job_name}_rstats_filter.conf

service rstats reload

