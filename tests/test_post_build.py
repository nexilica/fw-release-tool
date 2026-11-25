import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

import cubeide_post_build
import fw_release_tool

TOOLS = [
    pytest.param(
        cubeide_post_build, "cubeide_build.config.json", id="cubeide_post_build"
    ),
    pytest.param(fw_release_tool, "fw_release.config.json", id="fw_release_tool"),
]

HEADER = """#define APP_FW_VERSION_MAJOR  1
#define APP_FW_VERSION_MINOR  2
#define APP_FW_VERSION_PATCH  0x0A
"""

SREC_HEADER_S0 = "S00F000068656C6C6F202020202000003C\n"
STALE_S0 = "S00B0000464F4F20302E302E30F3\n"
DATA = "S1130000285F245F2212226A000424290008237C2A\n"
TERMINATION = "S9030000FC\n"


def srec_bytes(line: str) -> bytes:
    """Decode the count..checksum hex field of an S-Record line."""
    return bytes.fromhex(line.strip()[2:])


def write_project(root: Path, config_name: str, header_text: str) -> Path:
    """Write a header, an S-Record and the tool config; return the S-Record path."""
    header = root / "version.h"
    header.write_text(header_text, encoding="utf-8")
    srec = root / "Firmware.srec"
    srec.write_text(SREC_HEADER_S0 + STALE_S0 + DATA + TERMINATION, encoding="utf-8")
    config = {
        "paths": {"header": str(header), "srec": ""},
        "version": {
            "defines": {
                "major": "APP_FW_VERSION_MAJOR",
                "minor": "APP_FW_VERSION_MINOR",
                "build": "APP_FW_VERSION_PATCH",
            }
        },
        "behavior": {"insert_s0": True, "s0_prefix": "APP", "rename_mode": "copy"},
        "outputs": {"write_log": False},
    }
    (root / config_name).write_text(json.dumps(config), encoding="utf-8")
    return srec


@pytest.mark.parametrize(("tool", "config_name"), TOOLS)
def test_post_build_copies_the_srec_with_one_version_s0_before_termination(
    tool: ModuleType,
    config_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    srec = write_project(tmp_path, config_name, HEADER)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [tool.__name__, str(srec)])

    tool.main()

    output = tmp_path / "Firmware_v1.2.10.srec"
    lines = output.read_text(encoding="utf-8").splitlines(keepends=True)
    version_s0 = lines[2]
    record = srec_bytes(version_s0)
    assert srec.exists()
    assert lines[0] == SREC_HEADER_S0
    assert [line for line in lines if line.startswith("S0")] == [
        SREC_HEADER_S0,
        version_s0,
    ]
    assert lines[1] == DATA
    assert lines[3] == TERMINATION
    assert record[0] == len(record) - 1
    assert record[1:3] == b"\x00\x00"
    assert record[3:-1] == b"APP 1.2.10"
    assert sum(record) & 0xFF == 0xFF
    assert capsys.readouterr().out.startswith("OK v1.2.10 -> Firmware_v1.2.10.srec")


@pytest.mark.parametrize(("tool", "config_name"), TOOLS)
def test_post_build_exits_1_when_a_version_define_is_missing(
    tool: ModuleType,
    config_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    srec = write_project(
        tmp_path, config_name, HEADER.replace("APP_FW_VERSION_PATCH", "OTHER")
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [tool.__name__, str(srec)])

    with pytest.raises(SystemExit) as exit_info:
        tool.main()

    assert exit_info.value.code == 1
    assert not (tmp_path / "Firmware_v1.2.10.srec").exists()
    assert capsys.readouterr().out == "FAIL (see log)\n"
