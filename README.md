# fw-release-tool

Pre- and post-build steps for STM32CubeIDE projects that turn a build into a
traceable firmware release:

- **Pre-build** - stamps the build date into the project's `version.h`, so the
  date is compiled into the binary.
- **Post-build** - reads the firmware version from `version.h`, writes it into
  the S-Record as an S0 record, and copies or renames the `.srec` to
  `<name>_vX.Y.Z.srec`. Optionally it appends a one-line build log, writes
  version files, pushes a `vX.Y.Z` git tag and creates a GitHub release with
  the S-Record attached.

On success the post-build prints a single line, and the build console shows
it:

```text
OK v1.2.3 -> Firmware_v1.2.3.srec (tool 1.0.2)
```

## Scripts

| Script | Build step | Config file |
|---|---|---|
| `cubeide_pre_build.py` | Pre-build | `cubeide_build.config.json` |
| `cubeide_post_build.py` | Post-build | `cubeide_build.config.json` |
| `fw_release_tool.py` | Post-build (standalone) | `fw_release.config.json` |

`cubeide_pre_build.py` and `cubeide_post_build.py` are the pair to use on a
new project: they share one config file. `fw_release_tool.py` is the same
post-build logic with its own config file, for projects that do not stamp the
build date.

## Requirements

- Python 3.9 or newer on the machine that runs CubeIDE, available as
  `python3`.
- Standard library only: nothing to install.
- `git` on the `PATH` for the branch and commit in the build log and for
  tagging.

## Installation

Mount the repository as a git submodule at `Tools/` in the CubeIDE project
directory (the folder holding `.project` and `.cproject`):

```bash
git submodule add https://github.com/nexilica/fw-release-tool.git Tools
```

Put `cubeide_build.config.json` in the project directory, next to
`.cproject`, so it is tracked by the project rather than by the submodule.
Start from `config-examples/cubeide_build.config.json` and map the macro names
to your `version.h`.

Resulting layout:

```text
your-fw-project/
  .cproject
  cubeide_build.config.json
  Application/
    version.h
  Release/
    <build output>
  Tools/                      (this repository)
    cubeide_pre_build.py
    cubeide_post_build.py
```

Then add the build steps in CubeIDE under *Project > Properties > C/C++ Build
> Settings > Build Steps*, on the **Release** configuration only - the
pre-build rewrites `version.h` on every build:

```bash
# Pre-build steps
python3 "${ProjDirPath}/Tools/cubeide_pre_build.py"

# Post-build steps
python3 "${ProjDirPath}/Tools/cubeide_post_build.py" "${ProjDirPath}/Release/${BuildArtifactFileBaseName}.srec"
```

The S-Record output must be enabled in the project's post-build settings
(*MCU Post build outputs > Convert to Motorola S-record file*).

## Config discovery

The scripts search for their config file in this order and use the first one
found:

| Order | `cubeide_pre_build.py`, `cubeide_post_build.py` | `fw_release_tool.py` |
|---|---|---|
| 1 | `<cwd>/cubeide_build.config.json` | `<cwd>/fw_release.config.json` |
| 2 | `<cwd>/tools/cubeide_build.config.json` | `<cwd>/tools/fw_release.config.json` |
| 3 | `<script dir>/cubeide_build.config.json` | `<script dir>/fw_release.config.json` |
| 4 | `<script dir>/tools/cubeide_build.config.json` | `<script dir>/tools/fw_release.config.json` |
| 5 | `<script dir>/../cubeide_build.config.json` | - |
| 6 | `<script dir>/../tools/cubeide_build.config.json` | - |

Step 5 is what finds the config in the project directory when the scripts sit
in the `Tools/` submodule, whatever working directory CubeIDE runs the build
step from.

Relative paths inside the config are resolved against the **script
directory** (`Tools/`), not against the config file: a header in
`Application/` is `../Application/version.h`. Absolute paths are used as
they are.

## version.h

The header must define the three version numbers, and for the pre-build the
three date fields, as plain integer literals (decimal or `0x` hex, no `u`
suffix - the scripts read them with a regular expression):

```c
#define APP_FW_VERSION_MAJOR  1
#define APP_FW_VERSION_MINOR  2
#define APP_FW_VERSION_PATCH  3

#define APP_FW_BUILD_YEAR   0
#define APP_FW_BUILD_MONTH  0
#define APP_FW_BUILD_DAY    0
```

The macro names are free: the config maps them (`version.defines`,
`date.defines`). Commit the date fields as `0`, meaning "not stamped": the
pre-build overwrites the numbers in place, keeping any trailing comment, and
leaves the file modified after a Release build. `version_example.h` is a
complete reference header, including the packed 32-bit forms of version and
date.

## Configuration reference

`config-examples/` holds a complete `cubeide_build.config.json` and two
`fw_release.config.json` variants (application and bootloader). All keys are
optional except `paths.header`.

| Key | Default | Meaning |
|---|---|---|
| `paths.header` | - | Header with the version and date defines. |
| `paths.srec` | `""` | S-Record to process; the command-line argument takes precedence. |
| `version.defines.major` | `FW_VERSION_MAJOR` | Macro holding the major version. |
| `version.defines.minor` | `FW_VERSION_MINOR` | Macro holding the minor version. |
| `version.defines.build` | `FW_VERSION_BUILD` | Macro holding the patch (build) number. |
| `date.defines.year` | `FW_BUILD_YEAR` | Macro the pre-build stamps with the year. |
| `date.defines.month` | `FW_BUILD_MONTH` | Macro the pre-build stamps with the month. |
| `date.defines.day` | `FW_BUILD_DAY` | Macro the pre-build stamps with the day. |
| `behavior.insert_s0` | `true` | Write the version S0 record (`<s0_prefix> X.Y.Z`). |
| `behavior.s0_prefix` | `FW` | Text before the version in the S0 record. |
| `behavior.rename_mode` | `rename` | `copy` keeps the original `.srec`; `rename` moves it. |
| `behavior.quiet` | `false` | Accepted and ignored: the console output is always one line. |
| `outputs.write_log` | `false` | Append one line per build to the build log. |
| `outputs.log_path` | `<output dir>/build_info.log` | Build log file. |
| `outputs.write_version_file` | `false` | Write `X.Y.Z` to a file. |
| `outputs.version_file_path` | `<output dir>/fw_version.txt` | Version file. |
| `outputs.write_tool_version_file` | `false` | Write the tool version to a file. |
| `outputs.tool_version_file_path` | `<script dir>/<tool name>.version` | Tool version file. |
| `git.tag` | `false` | Create the annotated tag `vX.Y.Z` and push it. |
| `git.remote` | `origin` | Remote the tag is pushed to. |
| `github.release` | `false` | Create a GitHub release for `vX.Y.Z` with the S-Record attached. |
| `github.repository` | `""` | `owner/repo` of the release; required when `github.release` is on. |
| `github.token_env` | `GITHUB_TOKEN` | Environment variable holding the GitHub token. |
| `github.release_name` | `Firmware X.Y.Z` | Release title. |
| `github.release_notes_path` | `""` | File whose content becomes the release body. |
| `github.draft` | `false` | Create the release as a draft. |
| `github.prerelease` | `false` | Mark the release as a pre-release. |
| `github.generate_notes` | `true` | Let GitHub generate the release notes. |

`<output dir>` is the directory of the versioned S-Record.

## S0 record

The post-build keeps an S0 record on the first line (the header the linker
writes) as it is, removes any other S0 record - the one a previous run
inserted - and inserts one S0 record carrying `<s0_prefix> X.Y.Z` right
before the termination record (S7, S8 or S9). Running it twice on the same
file therefore leaves a single version record.

## GitHub release

With `github.release` on, the post-build creates the annotated `vX.Y.Z` tag if it
does not exist yet and pushes it (independently of `git.tag`), then creates the release
and uploads the versioned S-Record as an asset. The token in `token_env` needs
write access to the repository contents:

```bash
export GITHUB_TOKEN=<token>
```

## Logs and exit codes

Every post-build run writes a detailed log next to the script, `<tool name>.log`
(`cubeide_post_build.log` or `fw_release_tool.log`), with timestamped INFO,
WARNING and ERROR lines. The build log, when enabled, gets one line per build:

```text
2025-10-17T12:22:35.481920+00:00 | tool=1.0.2 | version=2.3.5 | S0=yes | action=copied | output=MyApp_v2.3.5.srec | out_dir=... | header=... | branch=main | commit=abc1234 | sha256=...
```

On failure the console shows `FAIL (see log)` or `FAIL vX.Y.Z (see log)`, and
the exit code says which step failed:

| Code | Step |
|---|---|
| 0 | Success |
| 1 | Config, header or S-Record error (missing file, missing define, invalid JSON) |
| 2 | Git tag creation or push (`git.tag`) |
| 3 | `github.release` on with an empty `github.repository` |
| 4 | Token variable `github.token_env` not set |
| 5 | Tag creation or push needed by the GitHub release |
| 6 | GitHub release creation or asset upload |
| 7 | S0 record handling |

The pre-build prints `OK build date YYYY-MM-DD -> version.h`, or
`FAIL cubeide_pre_build: <reason>` with exit code 1.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No configuration file found ...` or `cubeide_build.config.json not found ...` | Config file missing or misplaced | Put it in the project directory or in `Tools/` (see *Config discovery*). |
| `Define ... not found` | Macro names in the config differ from `version.h` | Fix `version.defines` or `date.defines`. |
| `Define ... not found` for a define that is there | Value is not a plain integer (`1u`, an expression) | Use a plain decimal or hex literal. |
| Exit code 2 or 5 | Not a git repository, or no push rights on the remote | Check `git remote -v` and the credentials. |
| Exit code 4 or 6 | Token missing, expired or without write access | Export a valid token in the variable named by `github.token_env`. |

## Development

The project uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run --frozen ruff check .
uv run --frozen ruff format .
uv run --frozen pyright
uv run --frozen pytest
```

CI runs the same checks and the tests on every pull request. `docs/overview.md`
describes how the scripts are put together.
