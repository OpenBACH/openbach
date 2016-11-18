/*
 * API to communicate with an RStats relay
 * on the local machine.
 */

#ifndef _RSTATS_API_H__
#define _RSTATS_API_H__

#include <string>
#include <unordered_map>

#include "lib_export.h"


namespace rstats {

  /*
   * Create and configure a new statistic for a
   * given job. The associated configuration file
   * should describe which statistics are to be
   * forwarded to the collector and which are to
   * be kept local.
   */
  DLL_PUBLIC unsigned int register_stat(
      const std::string& config_file,
      const std::string& suffix,
      bool _new);

  /*
   * Send a new statistic containing several attributes
   * for the given job, represented by its ID.
   */
  DLL_PUBLIC std::string send_stat(
      unsigned int id,
      long long timestamp,
      const std::unordered_map<std::string, std::string>& stats);

  /*
   * Reload the configuration for a given job,
   * represented by its ID.
   */
  DLL_PUBLIC std::string reload_stat(unsigned int id);

  /*
   * Remove the statistic represented by its ID
   * from the pool of statistics handled by the
   * Rstats server.
   */
  DLL_PUBLIC std::string remove_stat(unsigned int id);

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
 * C interface whose calls matches the C++ functions in the rstats namespace.
 *
 * Used by Python ctypes module for bindings.
 */
extern "C" DLL_PUBLIC unsigned int rstats_register_stat(
  char* config_file,
  char* suffix,
  bool _new);
extern "C" DLL_PUBLIC char* rstats_send_stat(
  unsigned int id,
  long long timestamp,
  char* stats);
extern "C" DLL_PUBLIC char* rstats_reload_stat(unsigned int id);
extern "C" DLL_PUBLIC char* rstats_remove_stat(unsigned int id);
extern "C" DLL_PUBLIC char* rstats_reload_all_stats();
extern "C" DLL_PUBLIC char* rstats_change_config(bool storage, bool broadcast);

#endif /* _RSTATS_API_H__ */
