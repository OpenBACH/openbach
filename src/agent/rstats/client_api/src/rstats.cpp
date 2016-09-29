#include <sstream>
#include <string>
#include <fstream>
#include <cstring>

#include "rstats.h"
#include "syslog.h"
#include "asio.hpp"


namespace rstats {

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
    syslog(LOG_ERR, "Error: Connexion to rstats refused, maybe rstats service isn't started");
    throw asio::system_error(error);
  }

  // Receive the response from the RStats service and
  // propagate it to the caller.
  char data[2048];
  sock.receive(asio::buffer(data), 0, error);  // TODO: See http://www.boost.org/doc/libs/1_58_0/doc/html/boost_asio/example/cpp03/timeouts/blocking_udp_client.cpp and implement a timeout
  if (error && error != asio::error::message_size) {
    syslog(LOG_ERR, "Error: Connexion to rstats was closed, could not get an answer");
    throw asio::system_error(error);
  }

  return std::string(data);
}

/*
 * Create the message to register and configure a new job;
 * send it to the RStats service and propagate its response.
 */
unsigned int register_stat(
    const std::string& config_file,
    const std::string& job_name,
    const std::string& prefix) {
  // Format the message
  std::stringstream command;
  command << "1 " << config_file << " " << job_name;
  if (prefix != "") {
    command << " " << prefix;
  }

  // Send the message
  std::string result;
  try {
    result = rstats_messager(command.str());
  } catch (std::exception& e) {
    syslog(LOG_ERR, "Failed to register to rstats service: %s", e.what());
    return 0;
  }
  std::stringstream parser(result);

  // Format the response and propagate it
  std::string startswith;
  parser >> startswith;
  if (startswith == "OK") {
    unsigned int id;
    parser >> id;
    if (!id) {
      syslog(LOG_ERR, "ERROR: Return message isn't well formed");
      syslog(LOG_ERR, "\t%s", result.c_str());
    } else {
      syslog(LOG_NOTICE, "NOTICE: Connexion ID is %d", id);
    }
    return id;
  } else if (startswith == "KO") {
    syslog(LOG_ERR, "ERROR: Something went wrong");
  } else {
    syslog(LOG_ERR, "ERROR: Return message isn't well formed");
  }

  syslog(LOG_ERR, "\t%s", result.c_str());
  return 0;
}

/*
 * Create the message to generate a new statistic;
 * send it to the RStats service and propagate its response.
 */
std::string send_stat(
    unsigned int id,
    const std::string& stat_name,
    long long timestamp,
    const std::unordered_map<std::string, std::string>& stats) {
  // Format the message
  std::stringstream command;
  command << "2 " << id << " \"" << stat_name << "\" " << timestamp;

  for (auto& stat : stats) {
    command << " \"" << stat.first << "\" \"" << stat.second << "\"";
  }

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to send statistic to rstats: ";
    msg += e.what();
    syslog(LOG_ERR, "%s", msg.c_str());
    return msg;
  }
}

/*
 * Helper function that mimics `send_stat` functionality with
 * statistics values already formatted.
 */
std::string send_prepared_stat(
    unsigned int id,
    const std::string& stat_name,
    long long timestamp,
    const std::string& stat_values) {
  // Format the message
  std::stringstream command;
  command << "2 " << id << " \"" << stat_name << "\" " << timestamp;
  if (stat_values != "") {
    command << " " << stat_values;
  }

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to send statistic to rstats: ";
    msg += e.what();
    syslog(LOG_ERR, "%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to reload a job configuration;
 * send it to the RStats service and propagate its response.
 */
std::string reload_stat(unsigned int id) {
  // Format the message
  std::stringstream command;
  command << "3 " << id;

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to reload statistic: ";
    msg += e.what();
    syslog(LOG_ERR, "%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to remove a registered job;
 * send it to the RStats service and propagate its response.
 */
std::string remove_stat(unsigned int id) {
  // Format the message
  std::stringstream command;
  command << "4 " << id;

  // Send the message and propagate RStats response
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "KO Failed to remove statistic: ";
    msg += e.what();
    syslog(LOG_ERR, "%s", msg.c_str());
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
    syslog(LOG_ERR, "%s", msg.c_str());
    return msg;
  }
}

/*
 * Create the message to fetch current jobs configurations;
 * send it to the RStats service and propagate its response.
 */
std::string get_configs() {
  try {
    return rstats_messager("6");
  } catch (std::exception& e) {
    std::string msg = "KO Failed to fetch configurations: ";
    msg += e.what();
    syslog(LOG_ERR, "%s", msg.c_str());
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
unsigned int rstats_register_stat(
    char* config_file,
    char* job_name,
    char* prefix) {
  return rstats::register_stat(config_file, job_name, prefix);
}

/*
 * Maps C interface to C++ call.
 */
char* rstats_send_stat(
    unsigned int id,
    char* stat_name,
    long long timestamp,
    char* stats) {
  return convert_std_string_to_char(rstats::send_prepared_stat(id, stat_name, timestamp, stats));
}

/*
 * Maps C interface to C++ call.
 */
char* rstats_reload_stat(unsigned int id) {
  return convert_std_string_to_char(rstats::reload_stat(id));
}

/*
 * Maps C interface to C++ call.
 */
char* rstats_remove_stat(unsigned int id) {
  return convert_std_string_to_char(rstats::remove_stat(id));
}

/*
 * Maps C interface to C++ call.
 */
char* rstats_reload_all_stats() {
  return convert_std_string_to_char(rstats::reload_all_stats());
}

/*
 * Maps C interface to C++ call.
 */
char* rstats_get_configs() {
  return convert_std_string_to_char(rstats::get_configs());
}
