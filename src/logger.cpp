#include "logger.h"

#if defined _WIN32 || defined __CYGWIN__
#include <Windows.h>

namespace logging {
	HANDLE event_log = 0;
	DWORD msg_counter = 0;
	int current_mask = 0xFF;

	int message_type_value(int priority) {
		switch(priority) {
		case 1 << MessageType::LOGGING_DEBUG:
		case 1 << MessageType::LOGGING_INFO:
		case 1 << MessageType::LOGGING_NOTICE:
			return EVENTLOG_INFORMATION_TYPE;
		case 1 << MessageType::LOGGING_WARNING:
			return EVENTLOG_WARNING_TYPE;
		case 1 << MessageType::LOGGING_ALERT:
		case 1 << MessageType::LOGGING_CRIT:
		case 1 << MessageType::LOGGING_EMERG:
		case 1 << MessageType::LOGGING_ERR:
			return EVENTLOG_ERROR_TYPE;
		default:
			return 0;
		}
	}

	void casted_open(const std::string& ident, int, int) {
		if (event_log) {
			close();
		}
		event_log = RegisterEventSource(0, ident.c_str());
	}

	void open(const std::string& ident, int options, FacilityType facility) {
		return casted_open(ident, options, facility);
	}

	void close() {
		if (event_log) {
			DeregisterEventSource(event_log);
			event_log = 0;
		}
	}

	void casted_message(const std::string& msg, int priority, int) {
		int prio = (1 << priority) & current_mask;
		if (!prio) {
			return;
		}

		if (!event_log) {
			open("Application", 0, FacilityType::LOGGING_USER);
		}
		const char* msg_str = msg.c_str();
		ReportEvent(event_log, message_type_value(prio), 0, ++msg_counter, 0, 1, 0, &msg_str, 0);
	}

	void message(const std::string& msg, MessageType type, FacilityType facility) {
		casted_message(msg, type, facility);
	}

	int set_log_mask(int mask) {
		int old_mask = current_mask;
		current_mask = mask;
		return old_mask;
	}

	int set_log_mask_to(MessageType type) {
		return set_log_mask(1 << type);
	}

	int set_log_mask_up_to(MessageType type) {
		int mask = 0;
		for (int i = 0; i <= type; ++i) {
			mask += 1 << i;
		}
		return set_log_mask(mask);
	}
}
#else
#include <syslog.h>

namespace logging {
	void casted_open(const std::string& ident, int options, int facility) {
		openlog(ident.c_str(), options, facility);
	}

	void open(const std::string& ident, int options, FacilityType facility) {
		return casted_open(ident, options, 8 * facility);
	}

	void close() {
		closelog();
	}

	void casted_message(const std::string& msg, int priority, int facility) {
		int prio = facility | priority;
		syslog(prio, msg.c_str());
	}

	void message(const std::string& msg, MessageType type, FacilityType facility) {
		casted_message(msg, type, 8 * facility);
	}

	int set_log_mask(int mask) {
		return setlogmask(mask);
	}

	int set_log_mask_to(MessageType type) {
		return set_log_mask(LOG_MASK(type));
	}

	int set_log_mask_up_to(MessageType type) {
		return set_log_mask(LOG_UPTO(type));
	}
}
#endif

void logging_open(char* ident, int option, int facility) {
	logging::casted_open(ident, option, facility);
}

void logging_close() {
	logging::close();
}

void logging_message(char* msg, int priority, int facility) {
	logging::casted_message(msg, priority, facility);
}

int logging_set_log_mask(int mask) {
	return logging::set_log_mask(mask);
}
