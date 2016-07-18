#include <sstream>
#include <string>
#include <fstream>
#include <cstring>

#include "rstats.h"
#include "logger.h"
#include "asio.hpp"


namespace rstats {

asio::io_service io_service;
asio::ip::udp::resolver resolver(io_service);
asio::ip::udp::endpoint endpoint = *resolver.resolve(asio::ip::udp::resolver::query(asio::ip::udp::v4(), "", "1111"));


std::string rstats_messager(const std::string& message) {
  asio::error_code error;
  asio::ip::udp::socket sock(io_service);
  sock.open(asio::ip::udp::v4());
  sock.send_to(asio::buffer(message), endpoint, 0, error);
  if (error) {
    logging::message(
        "Error: Connexion to rstats refused, maybe rstats service isn't started",
		logging::MessageType::LOGGING_ERR);
	throw asio::system_error(error);
  }

  // TODO: See http://www.boost.org/doc/libs/1_58_0/doc/html/boost_asio/example/cpp03/timeouts/blocking_udp_client.cpp
  // and implement a timeout
  char data[2048];
  sock.receive(asio::buffer(data), 0, error);
  if (error && error != asio::error::message_size) {
    logging::message(
        "Error: Connexion to rstats was closed, could not get an answer",
		logging::MessageType::LOGGING_ERR);
    throw asio::system_error(error);
  }

  return std::string(data);
}

unsigned int register_stat(
    const std::string& config_file,
    const std::string& job_name,
    const std::string& prefix) {
  std::stringstream command;
  command << "1 " << config_file << " " << job_name;
  if (prefix != "") {
    command << " " << prefix;
  }

  std::string result;
  try {
    result = rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "Failed to register to rstats service: ";
	msg += e.what();
	logging::message(msg, logging::MessageType::LOGGING_ERR);
	return 0;
  }
  std::stringstream parser(result);

  std::string startswith;
  parser >> startswith;
  if (startswith == "OK") {
    unsigned int id;
    parser >> id;
	if (!id) {
		logging::message("ERROR: Return message isn't well formed", logging::MessageType::LOGGING_ERR);
		std::string msg = "\t";
		msg += result;
		logging::message(msg, logging::MessageType::LOGGING_ERR);
	} else {
		std::stringstream msg;
		msg << "NOTICE: Connexion ID is " << id;
		logging::message(msg.str(), logging::MessageType::LOGGING_NOTICE);
	}
    return id;
  } else if (startswith == "KO") {
	logging::message("ERROR: Something went wrong", logging::MessageType::LOGGING_ERR);
  } else {
	logging::message("ERROR: Return message isn't well formed", logging::MessageType::LOGGING_ERR);
  }

  std::string msg = "\t";
  msg += result;
  logging::message(msg, logging::MessageType::LOGGING_ERR);
  return 0;
}

std::string send_stat(
    unsigned int id,
    const std::string& stat_name,
    long long timestamp,
    const std::unordered_map<std::string, std::string>& stats) {
  std::stringstream command;
  command << "2 " << id << " \"" << stat_name << "\" " << timestamp;

  for (auto& stat : stats) {
    command << " \"" << stat.first << "\" \"" << stat.second << "\"";
  }

  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "Failed to send statistic to rstats: ";
	msg += e.what();
	logging::message(msg, logging::MessageType::LOGGING_ERR);
	return msg;
  }
}

std::string send_prepared_stat(
	unsigned int id,
    const std::string& stat_name,
    long long timestamp,
	const std::string& stat_values) {
  std::stringstream command;
  command << "2 " << id << " \"" << stat_name << "\" " << timestamp;
  if (stat_values != "") {
	  command << " " << stat_values;
  }

  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "Failed to send statistic to rstats: ";
	msg += e.what();
	logging::message(msg, logging::MessageType::LOGGING_ERR);
	return msg;
  }
}


std::string reload_stat(unsigned int id) {
  std::stringstream command;
  command << "3 " << id;
  try {
    return rstats_messager(command.str());
  } catch (std::exception& e) {
    std::string msg = "Failed to reload statistic: ";
	msg += e.what();
	logging::message(msg, logging::MessageType::LOGGING_ERR);
	return msg;
  }
}

std::string reload_all_stats() {
  try {
    return rstats_messager("4");
  } catch (std::exception& e) {
    std::string msg = "Failed to reload statistics: ";
	msg += e.what();
	logging::message(msg, logging::MessageType::LOGGING_ERR);
	return msg;
  }
}

}

char* convert_std_string_to_char(const std::string& value) {
	char* result = new char[value.length()+1];
	std::memcpy(result, value.c_str(), sizeof(char) * value.length());
	result[value.length()] = 0;
	return result;
}

unsigned int rstats_register_stat(
	char* config_file,
	char* job_name,
	char* prefix) {
		return rstats::register_stat(config_file, job_name, prefix);
}

char* rstats_send_stat(
		unsigned int id,
		char* stat_name,
		long long timestamp,
		char* stats) {
	return convert_std_string_to_char(rstats::send_prepared_stat(id, stat_name, timestamp, stats));
}

char* rstats_reload_stat(unsigned int id) {
	return convert_std_string_to_char(rstats::reload_stat(id));
}

char* rstats_reload_all_stats() {
	return convert_std_string_to_char(rstats::reload_all_stats());
}
