# Overview

## Goal

fw-release-tool turns an STM32CubeIDE Release build into a traceable firmware
artifact without a separate release step: the build date is compiled into the
binary, the version from `version.h` is written into the S-Record, and the
output file is named after that version. Firmware projects mount it as the
`Tools/` submodule and call it from the CubeIDE build steps. The README is the
user reference (installation, configuration keys, exit codes); this page
explains how the pieces fit.

## Architecture in one picture

```text
                 cubeide_build.config.json  (project directory)
                    |                    |
  CubeIDE           v                    v
  Release  -> cubeide_pre_build.py   cubeide_post_build.py <- <name>.srec
  build          |                       |      |      |
                 v                       |      |      +--> git tag vX.Y.Z, GitHub release
   version.h  <- date stamped            |      +---------> build_info.log, version files
   (compiled                             v
    into the     <------- version read --+--> <name>_vX.Y.Z.srec  (S0 = "<prefix> X.Y.Z")
    binary)
```

The pre-build runs before compilation and only rewrites the three date macros
in `version.h`. The post-build runs after the linker has produced the `.srec`:
it parses the version macros, replaces any earlier version S0 record with a
new one placed before the termination record, copies or renames the file, and
then runs the optional outputs in order - log and version files, git tag,
GitHub release. Each optional step that fails exits with its own code, so the
build console shows which one broke.

## Key decisions

| Decision | Choice | Why |
|---|---|---|
| Runtime | Python 3.9+, standard library only | The scripts run under whatever `python3` the CubeIDE machine has, with no install step and no virtual environment. |
| Version source | Integer macros in `version.h`, names mapped in the config | The header is already the firmware's single source of the version; a regular expression reads it without a C preprocessor, which is why the values must be plain literals. |
| Build date | Rewritten into `version.h` before compilation | The date has to end up inside the binary (for example in a CANopen object), so it cannot be added after the build. |
| Version in the artifact | An extra S0 record before the termination record | Flashing tools ignore S0 records, so the version travels inside the file without changing the programmed image; the first-line S0 the linker writes is kept. |
| Config location | Project directory, found through the script's parent | The config belongs to the firmware project, not to the shared submodule, and must be found whatever working directory CubeIDE uses. |
| Paths in the config | Relative to the script directory | The same config works from any working directory. |
| Two post-build scripts | `fw_release_tool.py` and `cubeide_post_build.py` share the same code | Projects already wired to `fw_release_tool.py` and `fw_release.config.json` keep working unchanged; new projects use the pre/post pair with one shared config. A fix goes into both files. |

## Verification

**Status**: the pre-build date stamping and the post-build S0 record, copy and
failure exit are covered by `tests/`, which CI runs on every pull request
together with ruff and pyright. The git tag and GitHub release steps have no
automated test: they need a real remote and token.
