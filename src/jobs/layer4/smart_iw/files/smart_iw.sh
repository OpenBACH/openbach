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
#   @file     smart_iw.sh
#   @brief    Sources of the Job smart_iw
#   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>


#!/bin/bash
# Smart IW

# On récupère les arguments
if [ -z $2 ]
then
    echo "Usage 1: $0 size disable_pacing"
    exit 1
fi

size=$1
disable_pacing=$2


# On modifie la configuration de la machine
sysctl net.ipv4.tcp_smart_iw=$size
sysctl net.ipv4.tcp_disable_pacing=$disable_pacing


exit 0

