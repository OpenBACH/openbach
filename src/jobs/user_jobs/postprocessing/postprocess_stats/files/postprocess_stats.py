#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
   OpenBACH is a generic testbed able to control/configure multiple
   network/physical entities (under test) and collect data from them. It is
   composed of an Auditorium (HMIs), a Controller, a Collector and multiple
   Agents (one for each network entity that wants to be tested).


   Copyright © 2016 CNES


   This file is part of the OpenBACH testbed.


   OpenBACH is a free software : you can redistribute it and/or modify it under the
   terms of the GNU General Public License as published by the Free Software
   Foundation, either version 3 of the License, or (at your option) any later
   version.

   This program is distributed in the hope that it will be useful, but WITHOUT
   ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS
   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
   details.

   You should have received a copy of the GNU General Public License along with
   this program. If not, see http://www.gnu.org/licenses/.



   @file     postprocess_stats.py
   @brief    Sources of the Job postprocess_stats
   @author   David PRADAS <david.pradas@toulouse.viveris.com>
"""


from sys import exit
import signal
import argparse
import tempfile
import syslog
from subprocess import call
import collect_agent
import numpy as np
import matplotlib
# Force matplotlib to not use any Xwindows backend.
matplotlib.use('Agg')
import matplotlib.pyplot as ppp
from math import sqrt
from scipy import stats
import scipy as sp
import numpy as np
import time

import sys
from data_access import CollectorConnection


def write_conf_file(collector_infos):
    """ Function that writes the collector configuration file """
    with tempfile.NamedTemporaryFile('w', delete=False) as conf_file:
        print('---\n', file=conf_file)
        for key, value in collector_infos.items():
            print('{}: {}'.format(key, value), file=conf_file)
    return conf_file.name


def main(scenario_instance_id, agent_name, job_instance_ids, job_name, stat_name):
    # Connect to the collect-agent service
    conffile = "/opt/openbach-jobs/postprocess_stats/postprocess_stats_rstats_filter.conf"
    success = collect_agent.register_collect(conffile)
    if not success:
        collect_agent.send_log(syslog.LOG_ERR, "ERROR connecting to collect-agent")
        quit()
        
    # Write the Collector informations in a file
    collector_infos = {
        'collector_ip': "localhost",
        'influxdb_port': "8086",
        'database_name': "openbach",
        'epoch': "ms",
        'elasticsearch_port': "9200"
    }
    conf_filename =write_conf_file(collector_infos) 
    requester = CollectorConnection(conf_filename)
    job_instance_ids = job_instance_ids.split(',')
    for job_instance_id in job_instance_ids:
        #Import results from Collector Database
        try:
            job_inst_results = requester.get_job_instance_values(scenario_instance_id, agent_name,
                                            int(job_instance_id), job_name, None,
                                            [stat_name])
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "Error getting stats from collector" + str(ex))
            
        data = job_inst_results.statisticresults
        list_data=[]
        for stamp,statisticsresults in data.items():
            list_data.append(statisticsresults.values[stat_name])
        
        # Compute mean statistics values (mean/std/etc)
        n, min_max, mean, var, skew, kurt = stats.describe(list_data)
        std = sqrt(var)
        confidence_interval = stats.norm.interval(0.9,loc=mean,scale= std/sqrt(len(list_data)))
        
        #Send stats mean/var/and ci to Collector 
        timestamp = round(time.time() * 1000)
        try:
            statistics = {'mean_value_of_' + stat_name: mean}
            r = collect_agent.send_stat(timestamp, **statistics)
            
            statistics = {'variance_value_of_' + stat_name: var}
            r = collect_agent.send_stat(timestamp, **statistics)
            
            statistics = {'down_ci_value_of_' + stat_name:
                          confidence_interval[0]}
            r = collect_agent.send_stat(timestamp, **statistics)
            
            statistics = {'up_ci_value_of_' + stat_name:
                          confidence_interval[1]}
            r = collect_agent.send_stat(timestamp, **statistics)
            
        except Exception as ex: 
            collect_agent.send_log(syslog.LOG_ERR, "ERROR sending stats" +
                                   str(ex))

        # Compute, plot and save figure of CDF 
        try:
            ppp.figure(figsize=(12, 8), dpi=80, facecolor='w',
                   edgecolor='k')
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "Matplotlib problem:" +
                                    str(ex))
        ppp.ylabel('CDF')
        ppp.xlabel('Page load time (s)')
        ppp.title('CDF of web page load time')
        n_bins = 1000
        n, bins, patches = ppp.hist(list_data, n_bins, normed=1, cumulative=True)
        try:
            path = '/tmp/cdf_'+ str(scenario_instance_id) + '_' + str(job_instance_id) + '_' + job_name + '_' + stat_name + '.png'
            ppp.savefig(path)
            collect_agent.send_log(syslog.LOG_DEBUG, "Plot file saved in " + path)
        except Exception as ex:
            collect_agent.send_log(syslog.LOG_ERR, "Error saving plot files" + str(ex))
        

    
if __name__ == "__main__":
    # Define Usage
    parser = argparse.ArgumentParser(description='', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('scenario_instance_id', metavar='scenario_instance_id',
                        type=int, help='The ID of the scenario instance where \
                        the stat can be found')
    parser.add_argument('agent_name', metavar='agent_name',
                        type=str, help='The agent name where the stat has been \
                        generated')
    parser.add_argument('job_name', metavar='job_name', type=str,
                        help='The job name that has generated the stat')
    
    parser.add_argument('stat_name', metavar='stat_name', type=str,
                        help='The name of the stat that shall be postprocessed')
    
    parser.add_argument('job_instance_ids', type=str, help='The IDs of \
                        the job instances that have generated the stat \
                        (separated by commas)')
   
    parser.add_argument('-m', '--export-mode', type=int, help='The type of export')


    # get args
    args = parser.parse_args()
    scenario_instance_id = args.scenario_instance_id
    agent_name = args.agent_name
    job_instance_ids = args.job_instance_ids
    job_name = args.job_name
    stat_name = args.stat_name
    export_mode = args.export_mode 

    main(scenario_instance_id, agent_name, job_instance_ids, job_name, stat_name)
