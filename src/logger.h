/*
 * Wrapper around syslog interface.
 *
 * Maps to actual syslog call on *nix; sends messages to
 * EventLog on Windows.
 */

#ifndef _LOGGER_H__
#define _LOGGER_H__

#include <string>
#include "lib_export.h"


namespace logging {

	enum MessageType {
		LOGGING_EMERG = 0,
		LOGGING_ALERT,
		LOGGING_CRIT,
		LOGGING_ERR,
		LOGGING_WARNING,
		LOGGING_NOTICE,
		LOGGING_INFO,
		LOGGING_DEBUG,
	};

	enum FacilityType {
		LOGGING_KERN = 0,
		LOGGING_USER,
		LOGGING_MAIL,
		LOGGING_DAEMON,
		LOGGING_AUTH,
		LOGGING_LPR,
		LOGGING_NEWS,
		LOGGING_UUCP,
		LOGGING_CRON,
		LOGGING_SYSLOG,
		LOGGING_LOCAL0 = 16,
		LOGGING_LOCAL1,
		LOGGING_LOCAL2,
		LOGGING_LOCAL3,
		LOGGING_LOCAL4,
		LOGGING_LOCAL5,
		LOGGING_LOCAL6,
		LOGGING_LOCAL7,
	};

	enum OptionType {
		LOGGING_PID = 1 << 0,
		LOGGING_CONS = 1 << 1,
		LOGGING_ODELAY = 1 << 2,
		LOGGING_NDELAY = 1 << 3,
		LOGGING_NOWAIT = 1 << 4,
		LOGGING_PERROR = 1 << 5,
	};

  /*
   * Create/Connects to a new journal entry
   */
	void DLL_PUBLIC open(const std::string& ident, int, FacilityType);

  /*
   * Close the currently connected journal
   */
	void DLL_PUBLIC close();

  /*
   * Write a new message into the currently connected journal if
   * its type matches with the current mask.
   */
	void DLL_PUBLIC message(const std::string& msg, MessageType type, FacilityType facility = FacilityType::LOGGING_KERN);

  /*
   * Changes the mask associated to the current journal so other kind
   * of messages are filtered/allowed.
   */
	int DLL_PUBLIC set_log_mask_to(MessageType type);
	int DLL_PUBLIC set_log_mask_up_to(MessageType type);
}

/*
 * C interface whose calls matches the C++ functions in the logging namespace
 *
 * Used by Python ctypes module for bindings.
 */
extern "C" DLL_PUBLIC void logging_open(char* ident, int option, int facility);
extern "C" DLL_PUBLIC void logging_close();
extern "C" DLL_PUBLIC void logging_message(char* msg, int priority, int facility);
extern "C" DLL_PUBLIC int logging_set_log_mask(int mask);

#endif /* _LOGGER_H__ */
