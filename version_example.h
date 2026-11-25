/******************************************************************************
 * @file    version_example.h
 * @brief   Reference version.h for the CubeIDE build steps.
 *
 * The macro names match config-examples/cubeide_build.config.json. They are
 * not hardcoded in the scripts: each project maps its own prefix in the
 * config (version.defines / date.defines).
 *
 * Defines stay plain integers (decimal or hex, no 'u' suffix): the scripts
 * parse them with a regular expression.
 ******************************************************************************/

#ifndef VERSION_H
#define VERSION_H

#include <stdint.h>

/* Firmware version, bumped by hand per release. MAJOR and MINOR are 8-bit,
 * PATCH is the 16-bit build field. */
#define APP_FW_VERSION_MAJOR  1
#define APP_FW_VERSION_MINOR  0
#define APP_FW_VERSION_PATCH  0
#define APP_FW_VERSION_U32 \
    (((uint32_t)APP_FW_VERSION_MAJOR << 24) | \
     ((uint32_t)APP_FW_VERSION_MINOR << 16) | \
     ((uint32_t)APP_FW_VERSION_PATCH & 0xFFFFu))

/* Build date. The committed values are 0 (unset, e.g. a Debug build): the
 * Release pre-build (Tools/cubeide_pre_build.py) rewrites them in place with
 * the date of the build before compilation. */
#define APP_FW_BUILD_YEAR   0
#define APP_FW_BUILD_MONTH  0
#define APP_FW_BUILD_DAY    0
#define APP_FW_BUILD_DATE_U32 \
    (((uint32_t)APP_FW_BUILD_YEAR  << 16) | \
     ((uint32_t)APP_FW_BUILD_MONTH << 8)  | \
      (uint32_t)APP_FW_BUILD_DAY)

#endif /* VERSION_H */
