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
#   @file     set_pep.sh
#   @brief    Sources of the Job pep
#   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>


#!/bin/bash
# unset PEP for the ST

# On récupère les arguments
if [ -z $1 ]
then
    echo "Usage: $0 sat_network"
    exit 1
fi
sat_network=$1
if [ -z $2 ]
then
    PORT_PEP=5002
else
    PORT_PEP=$2
fi


# Stopper le Pep
pkill pepsal

# flush existing tables
iptables -D PREROUTING -t mangle -p tcp -m tcp -s $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1
iptables -D PREROUTING -t mangle -p tcp -m tcp -d $sat_network -j TPROXY --on-port $PORT_PEP --tproxy-mark 1

