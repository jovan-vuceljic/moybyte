// What MicroPython's lib/libm needs of a C library beyond <math.h>, given to
// its files where the kernel compiles them for the unix and webassembly
// ports (micropython.mk, THE FLOAT FUNCTIONS in README.md): fdlibm's files
// name the integer types newlib and glibc define, which musl does not.
#ifndef MOY_LIBM_H
#define MOY_LIBM_H

#include <stdint.h>

#ifdef __EMSCRIPTEN__
typedef int32_t __int32_t;
typedef uint32_t __uint32_t;
typedef uint8_t __uint8_t;
#endif

#endif // MOY_LIBM_H
