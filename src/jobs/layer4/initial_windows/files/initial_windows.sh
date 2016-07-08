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
#   @file     initial_windows.sh
#   @brief    Sources of the Job initial_windows
#   @author   Adrien THIBAUD <adrien.thibaud@toulouse.viveris.com>


#!/bin/bash
# Initial Windows

# On récupère les arguments
if [ -z $5 ]
then
    echo "Usage 1: $0 network gw interface initcwnd initrwnd"
    exit 1
fi

network=$1
gw=$2
interface=$3
initcwnd=$4
initrwnd=$5


# On modifie la configuration de la machine
ip route change $network via $gw dev $interface initcwnd $initcwnd initrwnd $initrwnd

exit 0

