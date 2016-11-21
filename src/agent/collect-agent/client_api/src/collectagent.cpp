#include <sstream>
#include <string>
#include <fstream>
#include <cstring>

#include "collectagent.h"
#include "syslog.h"
#include "asio.hpp"


int rstats_connection_id;


namespace collect_agent {

/*
 * Helpfull constants to easily create sockets to the local
 * RStats relay.
 */
asio::io_service io_service;
asio::ip::udp::resolver resolver(io_service);
asio::ip::udp::endpoint endpoint = *resolver.resolve(asio::ip::udp::resolver::query(asio::ip::udp::v4(), "", "1111"));


/*
 * Helper function to send a message to the local RStats relay.
 */
std::string rstats_messager(const std::string& message) {
  asio::error_code error;

  // Connect to the RStats service and send our message
  asio::ip::udp::socket sock(io_service);
  sock.open(asio::ip::udp::v4());
  sock.send_to(asio::buffer(message), endpoint, 0, error);
  if (error) {
    syslog(LOG_ERR, (char*)"Error: Connexion to rstats refused, maybe rstats service isn't started");
    throw asio::system_error(error);
  }

  // Receive the response from the RStats service and
  // propagate it to the caller.
  char data[2048];
  sock.receive(asio::buffer(data), 0, error);  // TODO: See http://www.boost.org/doc/libs/1_58_0/doc/html/boost_asio/example/cpp03/timeouts/blocking_udp_client.cpp and implement a timeout
  if (error && error != asio::error::message_size) {
    syslog(LOG_ERR, (char*)"Error: Connexion to rstats was closed, could not get an answer");
    throw asio::system_error(error);
  }

  return std::string(data);
}

/*
 * Create the message to register and configure a new job;
 * send it to the RStats service and propagate its response.
 * Also open a syslog connection
 */
bool register_collect(
    const std::string& config_file,
    const std::string& suffix,
    bool _new) {
  // Get the ids
  const char* job_name = std::getenv("JOB_NAME");
  const char* job_instance_id = std::getenv("JOB_INSTANCE_ID");
  const char* scenario_instance_id = std::getenv("SCENARIO_INSTANCE_ID");

  // Open the log
  openlog((char*)job_name, LOG_PID, LOG_USER);

  // Format the message to send to rstats
  std::stringstream command;
  command << "1 " << config_file << " " << (job_name ? job_name : "job_debug") << " " << (job_instance_id ? job_instance_id : "0") << " " << (scenario_instance_id ? scenario_instance_id : "0") << " " << _new;
  if (suffix != "") {
    command << " " << suffix;
  }

  // Send the message to rstats
  std::string result;
  try {
    result = rstats_messager(command.str());
  } catch (std::exception& e) {
    syslog(LOG_ERR, (char*)"Failed to register to rstats service: %s", e.what());
    return false;
  }
  std::stringstream parser(result);

  // Format the response and propagate it
  std::string startswith;
  parser >> startswith;
  if (startswith == "OK") {
    unsigned int id;
    parser >> id;
    if (!id) {
      syslog(LOG_ERR, (char*)"ERROR: Return message isn't well formed");
      syslog(LOG_ERR, (char*)"\t%s", result.c_str());
    } else {
      syslog(LOG_NOTICE, (char*)"NOTICE: Connexion ID is %d", id);
    }
    rstats_connection_id = id;
    return true;
  } else if (startswith == "KO") {
    syslog(LOG_ERR, (char*)"ERROR: Something went wrong");
  } else {
    syslog(LOG_ERR, (char*)"ERROR: Return message isn't well formed");
  }

  syslog(LOG_ERR, (char*)"\t%s", result.c_str());
  return false;
}

/*
 * Send the log
 */
void send_log(
    int priority,
    char* log) {
  // Get the ids
  const char* job_instance_id = std::getenv("JOB_INSTANCE_ID");
  const char* scenario_instance_id = std::getenv("SCENARIO_INSTANCE_ID");
  // Send the message
  syslog(priority, (char*)"SCENARIO_INSTANCE_ID %u, JOB_INSTANCE_ID %u, %s", (scenario_instance_id ? scenario_instance_id : 0), (job_instance_id ? job_instance_id : 0), log);
}

/*
 * Create the message to generate a new statistic;
 * send it to the RStats service and propagate its response.
 */
std::string send_stat(
    long long timestamp,
    const std::unordered_map<std::string, std::string>& stats) {
  // Format the message
  std::stringstream command;
  command << "2 " << rstats_connection_id << " " << timestamp;

  for (auto& stat : stats) {
    command << " \"" << stat.first << "\" \"" << stat.second << "\"";
  }

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to send statistic to rstats: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

/*
 * Helper function that mimics `send_stat` functionality with
 * statistics values already formatted.
 */
std::string send_prepared_stat(
    long long timestamp,
    const std::string& stat_values) {
  // Format the message
  std::stringstream command;
  command << "2 " << rstats_connection_id << " " << timestamp;
  if (stat_values != "") {
    command << " " << stat_values;
  }

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to send statistic to rstats: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to reload a job configuration;
 * send it to the RStats service and propagate its response.
 */
std::string reload_stat() {
  // Format the message
  std::stringstream command;
  command << "3 " << rstats_connection_id;

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to reload statistic: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to remove a registered job;
 * send it to the RStats service and propagate its response.
 */
std::string remove_stat() {
  // Format the message
  std::stringstream command;
  command << "4 " << rstats_connection_id;

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to remove statistic: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to reload all jobs configurations at once;
 * send it to the RStats service and propagate its response.
 */
std::string reload_all_stats() {
  try {
    return rstats_messager("5");
  } catch (std::exception& e) {
    std::string msg = "KO Failed to reload statistics: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to fetch current jobs configurations;
 * send it to the RStats service and propagate its response.
 */
std::string change_config(bool storage, bool broadcast) {
  // Get the ids
  const char* job_instance_id = std::getenv("INSTANCE_ID");
  const char* scenario_instance_id = std::getenv("SCENARIO_ID");

  // Format the message
  std::stringstream command;
  command << "6 " << scenario_instance_id << " " << job_instance_id << " ";
  command << storage << " " << broadcast;

  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to fetch configurations: ";
    msg += e.what();
    syslog(LOG_ERR, (char*)"%s", msg.c_str());
    return msg;
  }
}

}

/*
 * Helper function to return a suitable type to the Python interperter.
 */
char* convert_std_string_to_char(const std::string& value) {
  char* result = new char[value.length()+1];
  std::memcpy(result, value.c_str(), sizeof(char) * value.length());
  result[value.length()] = 0;
  return result;
}

/*
 * Maps C interface to C++ call.
 */
unsigned int collect_agent_register_collect(
    char* config_file,
    char* suffix,
    bool _new) {
  return collect_agent::register_collect(config_file, suffix, _new);
}

/*
 * Maps C interface to C++ call.
 */
void collect_agent_send_log(
    int priority,
    char* log) {
  return collect_agent::send_log(priority, log);
}

/*
 * Maps C interface to C++ call.
 */
char* collect_agent_send_stat(
    long long timestamp,
    char* stats) {
  return convert_std_string_to_char(collect_agent::send_prepared_stat(timestamp, stats));
}

/*
 * Maps C interface to C++ call.
 */
char* collect_agent_reload_stat() {
  return convert_std_string_to_char(collect_agent::reload_stat());
}

/*
 * Maps C interface to C++ call.
 */
char* collect_agent_remove_stat() {
  return convert_std_string_to_char(collect_agent::remove_stat());
}

/*
 * Maps C interface to C++ call.
 */
char* collect_agent_reload_all_stats() {
  return convert_std_string_to_char(collect_agent::reload_all_stats());
}

/*
 * Maps C interface to C++ call.
 */
char* collect_agent_change_config(bool storage, bool broadcast) {
  return convert_std_string_to_char(collect_agent::change_config(storage, broadcast));
}
