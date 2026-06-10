/******************************************************************************
 * version_example.h — reference header for the CubeIDE build scripts.
 *
 * Shows the macro names the cubeide_pre_build.py / cubeide_post_build.py pair
 * read and write. The names are not hardcoded in the scripts: each project maps
 * them in cubeide_build.config.json (version.defines / date.defines), so you may
 * keep a project-specific prefix (e.g. CANNECT_FW_VERSION_MAJOR) and point the
 * config at it. The defaults below match the example config in config-examples/.
 *
 *  - FW_VERSION_* : maintained by hand, bumped per release.
 *  - FW_BUILD_*   : build date, OVERWRITTEN IN PLACE by cubeide_pre_build.py on
 *                   each Release build (default 0 = unset / non-stamped build).
 ******************************************************************************/

#ifndef VERSION_EXAMPLE_H
#define VERSION_EXAMPLE_H

/* Firmware version (manual). */
#define FW_VERSION_MAJOR  1
#define FW_VERSION_MINOR  0
#define FW_VERSION_BUILD  0

/* Build date (auto-injected pre-build; 0 = unset). */
#define FW_BUILD_YEAR   0
#define FW_BUILD_MONTH  0
#define FW_BUILD_DAY    0

#endif /* VERSION_EXAMPLE_H */
