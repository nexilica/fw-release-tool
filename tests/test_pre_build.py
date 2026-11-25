import datetime
import json
from pathlib import Path

import pytest

import cubeide_pre_build

HEADER = """#define APP_FW_VERSION_MAJOR  1
#define APP_FW_BUILD_YEAR   0   /* stamped */
#define APP_FW_BUILD_MONTH  0x0
#define APP_FW_BUILD_DAY    0
"""


def write_project(root: Path, header_text: str) -> Path:
    """Write a header and a cubeide_build.config.json pointing at it; return the header path."""
    header = root / "version.h"
    header.write_text(header_text, encoding="utf-8")
    config = {
        "paths": {"header": str(header)},
        "date": {
            "defines": {
                "year": "APP_FW_BUILD_YEAR",
                "month": "APP_FW_BUILD_MONTH",
                "day": "APP_FW_BUILD_DAY",
            }
        },
    }
    (root / "cubeide_build.config.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    return header


def test_pre_build_stamps_today_into_the_mapped_defines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    header = write_project(tmp_path, HEADER)
    monkeypatch.chdir(tmp_path)

    rc = cubeide_pre_build.main()

    today = datetime.date.today()
    assert rc == 0
    assert header.read_text(encoding="utf-8") == (
        "#define APP_FW_VERSION_MAJOR  1\n"
        f"#define APP_FW_BUILD_YEAR   {today.year}   /* stamped */\n"
        f"#define APP_FW_BUILD_MONTH  {today.month}\n"
        f"#define APP_FW_BUILD_DAY    {today.day}\n"
    )
    assert capsys.readouterr().out.startswith(f"OK build date {today.isoformat()}")


def test_pre_build_fails_and_leaves_header_untouched_when_a_define_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = HEADER.replace("APP_FW_BUILD_DAY", "OTHER_DAY")
    header = write_project(tmp_path, text)
    monkeypatch.chdir(tmp_path)

    rc = cubeide_pre_build.main()

    assert rc == 1
    assert header.read_text(encoding="utf-8") == text
    assert capsys.readouterr().out.startswith("FAIL cubeide_pre_build:")
