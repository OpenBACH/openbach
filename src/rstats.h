#ifndef _RSTATS_API_H__
#define _RSTATS_API_H__

#include <string>
#include <unordered_map>

#include "lib_export.h"


namespace rstats {

  DLL_PUBLIC unsigned int register_stat(
      const std::string& config_file,
      const std::string& job_name,
      const std::string& prefix);

  DLL_PUBLIC std::string send_stat(
      unsigned int id,
      const std::string& stat_name,
      long long timestamp,
      const std::unordered_map<std::string, std::string>& stats);

  DLL_PUBLIC std::string reload_stat(unsigned int id);

  DLL_PUBLIC std::string reload_all_stats();

}

extern "C" DLL_PUBLIC unsigned int rstats_register_stat(
	char* config_file,
	char* job_name,
	char* prefix);

extern "C" DLL_PUBLIC char* rstats_send_stat(
	unsigned int id,
	char* stat_name,
	long long timestamp,
	char* stats);

extern "C" DLL_PUBLIC char* rstats_reload_stat(unsigned int id);

extern "C" DLL_PUBLIC char* rstats_reload_all_stats();

#endif /* _RSTATS_API_H__ */
