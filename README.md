# fw_release_tool

**NXL-FW-Release-Tool** is a Python-based **post-build script for automatic release management** for STM32 projects (STM32CubeIDE/Eclipse).

This tool automates firmware release generation and management:
- Reads the **firmware version** from a `version.h` file (with customizable `#define` names)
- Optionally inserts an **S0 record** into the S-Record
- Renames or copies the `.srec` file to `Name_vX.Y.Z.srec`
- Writes detailed logs and version files
- Can automatically create **Git tags** and **GitHub releases**

Console output: only the final result  
```
OK v1.2.3 -> Firmware_v1.2.3.srec (tool 1.0.0)
```
or  
```
FAIL (see log)
```

---

## 🛠 CubeIDE pre/post-build scripts (build-date stamping)

In addition to `fw_release_tool.py` (the original post-build tool, unchanged),
this repo ships a CubeIDE build-step pair that also stamps the **build date**:

| Script | CubeIDE step | Does |
|---|---|---|
| `cubeide_pre_build.py` | Pre-build | Injects today's date into `version.h` (`date.defines` → `FW_BUILD_YEAR/MONTH/DAY`), so the date is compiled into the binary. |
| `cubeide_post_build.py` | Post-build | Independent copy of `fw_release_tool.py`: reads the version from `version.h`, stamps the S0 record and renames the `.srec`. |

Both read **one shared config**, `cubeide_build.config.json` (same schema as
`fw_release.config.json` plus a `date.defines` block). See
`config-examples/cubeide_build.config.json` and `version_example.h` for the
exact macro names. Names are per-project — map them in the config to a prefixed
header (e.g. `CANNECT_FW_VERSION_MAJOR`, `CANNECT_FW_BUILD_YEAR`).

CubeIDE *Project ▸ Properties ▸ C/C++ Build ▸ Settings ▸ Build Steps*:

```bash
# Pre-build
python3 "${ProjDirPath}/Tools/cubeide_pre_build.py"
# Post-build
python3 "${ProjDirPath}/Tools/cubeide_post_build.py" "${ProjDirPath}/Release/${BuildArtifactFileBaseName}.srec"
```

> `cubeide_pre_build.py` rewrites `version.h` in place on every build, so the
> file shows as modified afterwards (enable it on the Release config only).

---

## 📁 Typical Project Structure

```
your-fw-project/
├─ Core/
│  └─ Src/
│     └─ Dev/
│        └─ version.h
├─ Release/
│  ├─ <build output>
│  └─ ...
├─ Tools/
│  ├─ fw_release_tool.py
│  └─ fw_release.config.json
└─ ...
```

> All **paths in the configuration file are relative to the script directory** (`Tools/`).

---

## ⚙️ Installation and Integration in STM32CubeIDE

1. Copy `Tools/fw_release_tool.py` and `Tools/fw_release.config.json` into your repository.
2. Open **STM32CubeIDE** → *Project → Properties → C/C++ Build → Settings → Build Steps → Post-build steps*
3. Add this post-build command:

```bash
python3 "${ProjDirPath}/Tools/fw_release_tool.py" "${ProjDirPath}/Release/${BuildArtifactFileBaseName}.srec"
```

---

## 🧩 Configuration File (`fw_release.config.json`)

This file controls the full behavior of the script.  
Example configuration:

```json
{
  "paths": {
    "header": "../Core/Src/Dev/version.h",
    "srec": ""  // optional: leave empty and pass .srec path via CLI
  },
  "version": {
    "defines": {
      "major": "FW_VERSION_MAJOR",
      "minor": "FW_VERSION_MINOR",
      "build": "FW_VERSION_BUILD"
    }
  },
  "behavior": {
    "insert_s0": true,                 // insert S0 record with text "FW X.Y.Z"
    "s0_prefix": "FW",
    "rename_mode": "rename",           // "rename" or "copy"
    "quiet": false                     // if true, console output reduced to "OK vX.Y.Z"
  },
  "outputs": {
    "write_log": true,                 // enable CI one-line log
    "log_path": "../Release/build_info.log",
    "write_version_file": true,        // writes fw_version.txt
    "version_file_path": "../Release/fw_version.txt",
    "write_tool_version_file": true,   // writes script version file
    "tool_version_file_path": ""       // empty -> tools/fw_release_tool.version
  },
  "git": {
    "tag": false,                      // true -> create/push Git tag vX.Y.Z
    "remote": "origin"
  },
  "github": {
    "release": false,                  // true -> create GitHub release
    "repository": "owner/repo",        // e.g. "nexilica/my-firmware"
    "token_env": "GITHUB_TOKEN",       // environment variable with token
    "release_name": "",
    "release_notes_path": "",
    "draft": false,
    "prerelease": false,
    "generate_notes": true
  }
}
```

### 📘 Path Reference
| Field | Description | Relative to |
|--------|--------------|--------------|
| `paths.header` | Header with version defines | `Tools/` |
| `paths.srec` | Optional `.srec` path | `Tools/` |
| `outputs.log_path` | CI one-line log file | `Tools/` |
| `outputs.version_file_path` | `fw_version.txt` file | `Tools/` |
| `outputs.tool_version_file_path` | Tool version file | `Tools/` |
| `github.release_notes_path` | Optional release notes file | `Tools/` |

---

## 🔢 Firmware Version

The header file must contain three numeric defines (decimal or hexadecimal):

```c
#define FW_VERSION_MAJOR  1
#define FW_VERSION_MINOR  0
#define FW_VERSION_BUILD  2
```

Define names can be customized in `version.defines` inside the configuration file.

---

## 🪵 Logging and Traceability

- **Detailed log**: `Tools/fw_release_tool.log`  
  (INFO/WARNING/ERROR + timestamp)
- **CI log** (if enabled): single-line per build  
  ```
  2025-10-17T14:22:35Z | tool=1.0.0 | version=2.3.5 | S0=yes | action=renamed | output=MyApp_v2.3.5.srec | branch=main | commit=abc1234 | sha256=...
  ```
- **Firmware version file**: contains only `X.Y.Z`
- **Tool version file**: contains the script version (`1.0.0`)

---

## 🚀 Advanced Options

### 🔖 Git Tag
Enable with:
```json
"git": { "tag": true, "remote": "origin" }
```
> Requires a valid Git repository with push permissions.

### 🐙 GitHub Release
Enable with:
```json
"github": {
  "release": true,
  "repository": "owner/repo",
  "token_env": "GITHUB_TOKEN"
}
```
Set your access token as an environment variable:
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxx
```

---

## ⚠️ Troubleshooting

| Problem | Likely Cause | Solution |
|----------|---------------|-----------|
| `FAIL (see log)` | generic error | check `Tools/fw_release_tool.log` |
| `Config file not found` | file missing or misplaced | ensure it's in `Tools/` or CWD |
| `Define not found` | mismatched define names | update `version.defines` in config |
| `Git error` | invalid repo or no remote | verify `git remote -v` works |
| `GitHub API error` | missing or invalid token | export `GITHUB_TOKEN` with `contents:write` permissions |

---

## 🧾 Example Output

Console output:
```
OK v1.2.3 -> MyFirmware_v1.2.3.srec (tool 1.0.0)
```

`Tools/fw_release_tool.log`:
```
2025-10-17T14:25:02+0200 | INFO | Parsed version from header: major=1, minor=2, build=3
2025-10-17T14:25:02+0200 | INFO | S0 record inserted with text: 'FW 1.2.3'
2025-10-17T14:25:02+0200 | INFO | Renamed file to: MyFirmware_v1.2.3.srec
...
```

---

## 🔄 Changelog

### v1.0.0 (2025-10-17)
- First stable version of `fw_release_tool`
- Features:
  - Configurable version parsing from header file
  - Optional S0 record insertion into `.srec`
  - Automatic rename/copy of `.srec` file
  - Detailed logging with timestamp and levels
  - CI-friendly single-line logging
  - Optional Git tag creation and push
  - Optional GitHub release creation and asset upload
  - Firmware and tool version file generation
  - Fully JSON-configurable with paths relative to `Tools/`

---