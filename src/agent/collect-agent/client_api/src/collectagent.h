/*
 * API to communicate with an RStats relay and rsyslog
 * on the local machine.
 */

#ifndef _COLLECT_AGENT_API_H__
#define _COLLECT_AGENT_API_H__

#include <string>
#include <unordered_map>

#include "lib_export.h"


extern int rstats_connection_id;


namespace collect_agent {

  /*
   * Create and configure a new statistic for a
   * given job. The associated configuration file
   * should describe which statistics are to be
   * forwarded to the collector and which are to
   * be kept local.
   */
  DLL_PUBLIC bool register_collect(
      const std::string& config_file,
      bool _new);

  /*
   * Send the log
   */
  DLL_PUBLIC void send_log(
      int priority,
      char* log);

  /*
   * Send a new statistic containing several attributes
   * for the given job
   */
  DLL_PUBLIC std::string send_stat(
      long long timestamp,
      const std::string& suffix,
      const std::unordered_map<std::string, std::string>& stats);

  /*
   * Reload the configuration for a given job
   */
  DLL_PUBLIC std::string reload_stat();

  /*
   * Remove the statistic
   * from the pool of statistics handled by the
   * Rstats server.
   */
  DLL_PUBLIC std::string remove_stat();

  /*
   * Reload the configuration for all registered jobs.
   */
  DLL_PUBLIC std::string reload_all_stats();

  /*
   * Retrive informations about the configuration of
   * currently monitored stats.
   */
  DLL_PUBLIC std::string change_config(bool storage, bool broadcast);

}

/*
 * C interface whose calls matches the C++ functions in the collect_agent
 * namespace.
 *
 * Used by Python ctypes module for bindings.
 */
extern "C" DLL_PUBLIC unsigned int collect_agent_register_collect(
  char* config_file,
  bool _new);
extern "C" DLL_PUBLIC void collect_agent_send_log(
  int priority,
  char* log);
extern "C" DLL_PUBLIC char* collect_agent_send_stat(
  long long timestamp,
  char* suffix,
  char* stats);
extern "C" DLL_PUBLIC char* collect_agent_reload_stat();
extern "C" DLL_PUBLIC char* collect_agent_remove_stat();
extern "C" DLL_PUBLIC char* collect_agent_reload_all_stats();
extern "C" DLL_PUBLIC char* collect_agent_change_config(
  bool storage,
  bool broadcast);

#endif /* _COLLECT_AGENT_API_H__ */
