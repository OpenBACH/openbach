/*
 * Generate DLL_PUBLIC macro to apply symbols visibility
 * into libraries bases on the compiler used.
 */

#ifndef __LIB_EXPORT_H__
#define __LIB_EXPORT_H__

#if defined _WIN32 || defined __CYGWIN__
  #ifdef GENERATE_LIB
    #ifdef __GNUC__
      #define DLL_PUBLIC __attribute__ ((dllexport))
    #else
      #define DLL_PUBLIC __declspec(dllexport) // Note: actually gcc seems to also supports this syntax.
    #endif
  #else
    #ifdef __GNUC__
      #define DLL_PUBLIC __attribute__ ((dllimport))
    #else
      #define DLL_PUBLIC __declspec(dllimport) // Note: actually gcc seems to also supports this syntax.
    #endif
  #endif
  #define DLL_LOCAL
#else
  #if __GNUC__ >= 4
    #define DLL_PUBLIC __attribute__ ((visibility ("default")))
    #define DLL_LOCAL  __attribute__ ((visibility ("hidden")))
  #else
    #define DLL_PUBLIC
    #define DLL_LOCAL
  #endif
#endif

#endif /* __LIB_EXPORT_H__ */
