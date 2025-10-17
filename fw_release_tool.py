#!/usr/bin/env python3
import re
import sys
import os
import json
import shutil
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from urllib import request, parse, error
import logging

# ============================ Tool version ============================
TOOL_NAME = "fw_release_tool"
TOOL_VERSION = "1.0.1"  # <— aggiorna qui quando cambi lo script


# ============================ Logging Setup ============================

def setup_script_logger() -> logging.Logger:
    """Initialize a file logger in the script directory with timestamped lines and levels."""
    script_dir = Path(__file__).resolve().parent
    log_path = script_dir / f"{TOOL_NAME}.log"

    logger = logging.getLogger(TOOL_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z"
    )
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ====================== Core parsing / SREC utilities ======================

def parse_version_from_header(hdr_path: Path, names: dict, log: logging.Logger):
    """
    Parse version macros from header using custom define names.
    Accepts decimal or hex literals (e.g., 12, 0x0C).
    names = {"major": "...", "minor": "...", "build": "..."}
    """
    text = hdr_path.read_text(encoding="utf-8", errors="ignore")

    def pick(define_name: str) -> int:
        # Match: #define NAME <number>   (dec or 0xhex). Ignore trailing comments.
        m = re.search(
            rf'^\s*#define\s+{re.escape(define_name)}\s+([0-9]+|0[xX][0-9a-fA-F]+)\b',
            text, re.M
        )
        if not m:
            raise RuntimeError(f"Define {define_name} not found in {hdr_path}")
        literal = m.group(1)
        return int(literal, 0)  # base=0 => auto-dec/hex

    maj = pick(names.get("major", "FW_VERSION_MAJOR"))
    minr = pick(names.get("minor", "FW_VERSION_MINOR"))
    bld = pick(names.get("build", "FW_VERSION_BUILD"))
    log.info("Parsed version from header: major=%d, minor=%d, build=%d (defines=%s)", maj, minr, bld, names)
    return maj, minr, bld


def srec_s0(text: str, addr: int = 0x0000) -> str:
    """Build a valid Motorola S-Record S0 line containing the given text."""
    data = text.encode("ascii")
    addr_hi = (addr >> 8) & 0xFF
    addr_lo = (addr & 0xFF)
    count = 2 + len(data) + 1  # address(2) + data + checksum
    total = count + addr_hi + addr_lo + sum(data)
    checksum = (~total) & 0xFF
    return f"S0{count:02X}{addr:04X}{data.hex().upper()}{checksum:02X}\n"


def inject_single_s0(srec_path: Path, s0_line: str, log: logging.Logger) -> tuple[bool, int]:
    """
    Ensure exactly one S0 record exists in the SREC file.
    Removes all existing S0 lines and inserts a single new one
    before the termination record (S7/S8/S9).

    Returns: (inserted: bool, removed_count: int)
    """
    text = srec_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines(True)

    # Remove all existing S0 lines
    removed = 0
    new_lines = []
    for line in lines:
        if line.startswith("S0"):
            removed += 1
        else:
            new_lines.append(line)

    # Find termination record
    term_idx = None
    for i in range(len(new_lines) - 1, -1, -1):
        if new_lines[i].startswith(("S7", "S8", "S9")):
            term_idx = i
            break

    # Insert our single S0
    insert_at = term_idx if term_idx is not None else len(new_lines)
    if term_idx is None:
        log.warning("No termination record (S7/S8/S9) found; appending S0 at the end.")

    new_lines.insert(insert_at, s0_line)
    srec_path.write_text("".join(new_lines), encoding="utf-8")

    log.info("S0 handling: removed=%d, inserted=1, position=%s", removed, insert_at)
    return True, removed



# ============================ Logging helpers ============================

def write_ci_log(log_path: Path, *, version: str, s0_inserted: bool,
                 action: str, output_file: Path, header_path: Path,
                 branch: str = "", commit: str = "", sha256: str = "",
                 tool_version: str = "", log: logging.Logger = None):
    """Append one structured line to the build log (CI-friendly)."""
    ts = datetime.now(timezone.utc).isoformat()
    line = (f"{ts} | tool={tool_version} | version={version} | S0={'yes' if s0_inserted else 'no'} | "
            f"action={action} | output={output_file.name} | out_dir={output_file.parent} | "
            f"header={header_path} | branch={branch} | commit={commit} | sha256={sha256}\n")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)
    if log:
        log.info("Appended CI log: %s", log_path)


def run(cmd, cwd=None, log: logging.Logger = None):
    """Run a command and return (rc, stdout, stderr)."""
    if log:
        log.info("Executing command: %s", " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, text=True)
    out, err = p.communicate()
    if log:
        lvl = logging.INFO if p.returncode == 0 else logging.ERROR
        log.log(lvl, "Command finished with rc=%d, stdout='%s', stderr='%s'", p.returncode, out.strip(), err.strip())
    return p.returncode, out.strip(), err.strip()


# ============================ Git / GitHub ============================

def git_tag_and_push(version_tag: str, message: str, remote: str, log: logging.Logger):
    """Create an annotated tag and push it to the remote."""
    rc, out, err = run(["git", "rev-parse", "--is-inside-work-tree"], log=log)
    if rc != 0 or out != "true":
        raise RuntimeError(f"Not a git repository: {err or out}")

    rc, out, err = run(["git", "tag", "-l", version_tag], log=log)
    if out.strip() == version_tag:
        log.info("Git tag '%s' already exists; skipping creation.", version_tag)
    else:
        rc, out, err = run(["git", "tag", "-a", version_tag, "-m", message or version_tag], log=log)
        if rc != 0:
            raise RuntimeError(f"Failed to create git tag: {err or out}")
        log.info("Created git tag: %s", version_tag)

    rc, out, err = run(["git", "push", remote, version_tag], log=log)
    if rc != 0:
        raise RuntimeError(f"Failed to push git tag: {err or out}")
    log.info("Pushed git tag '%s' to remote '%s'.", version_tag, remote)


def http_json(method: str, url: str, token: str, payload: dict, log: logging.Logger, extra_headers: dict = None):
    """Make an HTTP request with JSON payload and Bearer token."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            log.info("HTTP %s %s -> %d", method, url, resp.getcode())
            return resp.getcode(), json.loads(body) if body else {}
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        log.error("GitHub API error %d at %s: %s", e.code, url, detail)
        raise RuntimeError(f"GitHub API error {e.code} at {url}: {detail}") from None


def http_upload_asset(upload_url_template: str, asset_path: Path, token: str, log: logging.Logger):
    """Upload a release asset to the GitHub uploads endpoint."""
    base = upload_url_template.split("{")[0]
    name = asset_path.name
    qs = parse.urlencode({"name": name})
    url = f"{base}?{qs}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = asset_path.read_bytes()
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            log.info("Uploaded asset '%s' -> HTTP %d", asset_path.name, resp.getcode())
            return resp.getcode(), json.loads(body) if body else {}
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        log.error("GitHub asset upload error %d at %s: %s", e.code, url, detail)
        raise RuntimeError(f"GitHub asset upload error {e.code} at {url}: {detail}") from None


def create_github_release(*, owner_repo: str, token: str, tag: str, name: str,
                          body: str, draft: bool, prerelease: bool,
                          generate_notes: bool, asset: Path, log: logging.Logger):
    """Create a GitHub release and optionally upload an asset."""
    api_base = "https://api.github.com"
    url = f"{api_base}/repos/{owner_repo}/releases"
    payload = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": draft,
        "prerelease": prerelease,
        "generate_release_notes": generate_notes,
    }
    status, data = http_json("POST", url, token, payload, log=log)
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create release: HTTP {status}")

    log.info("Created GitHub Release '%s' for tag '%s'.", name, tag)
    if asset and asset.exists():
        status, _ = http_upload_asset(data["upload_url"], asset, token, log=log)
        if status not in (200, 201):
            raise RuntimeError(f"Failed to upload asset: HTTP {status}")
        log.info("Uploaded asset: %s", asset.name)
    return data


# ============================ Config handling ============================

def find_config_path(script_dir: Path) -> Path:
    """
    Auto-discover a JSON config file.
    Search order (relative to execution CWD first, then script directory):
      1) CWD/fw_release.config.json
      2) CWD/tools/fw_release.config.json
      3) <script_dir>/fw_release.config.json
      4) <script_dir>/tools/fw_release.config.json
    """
    cwd = Path.cwd()
    candidates = [
        cwd / "fw_release.config.json",
        cwd / "tools" / "fw_release.config.json",
        script_dir / "fw_release.config.json",
        script_dir / "tools" / "fw_release.config.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("No configuration file found in execution path or script folder.")


def load_config_auto(log: logging.Logger, script_dir: Path):
    """Load configuration from auto-discovered JSON file. Returns (dict, path)."""
    cfg_file = find_config_path(script_dir)
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Invalid JSON in config '{cfg_file}': {e}")
    log.info("Loaded config from: %s", cfg_file)
    return cfg, cfg_file


def cfg_get(cfg: dict, key_path: str, default=None):
    """Deep-get helper using dotted key path."""
    cur = cfg
    for k in key_path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def resolve_from_script(path_str: str, script_dir: Path) -> Path:
    """Resolve a config path relative to the script directory (if relative), or use as-is if absolute."""
    p = Path(path_str)
    if not p.is_absolute():
        p = (script_dir / p).resolve()
    return p


# ============================ Main ============================

def main():
    logger = setup_script_logger()
    script_dir = Path(__file__).resolve().parent
    logger.info("%s starting (tool_version=%s)", TOOL_NAME, TOOL_VERSION)
    try:
        import argparse
        parser = argparse.ArgumentParser(
            description="Versioned SREC tool (config-driven): insert S0, rename/copy, logging, optional git tag and GitHub release."
        )
        parser.add_argument("srec", nargs="?", help="Path to the .srec produced by the build (optional; can be set in config).")
        args = parser.parse_args()

        cfg, cfg_file = load_config_auto(log=logger, script_dir=script_dir)

        # -------- Resolve paths strictly relative to the script directory --------
        header_path_str = cfg_get(cfg, "paths.header", "")
        if not header_path_str:
            raise SystemExit("Missing 'paths.header' in config.")
        header_path = resolve_from_script(header_path_str, script_dir)

        # SREC: CLI positional overrides config
        srec_path_str = args.srec or cfg_get(cfg, "paths.srec", "")
        if not srec_path_str:
            raise SystemExit("SREC path not provided (CLI) and 'paths.srec' missing in config.")
        srec_path = resolve_from_script(srec_path_str, script_dir)

        # Behavior
        insert_s0 = bool(cfg_get(cfg, "behavior.insert_s0", True))
        s0_prefix = cfg_get(cfg, "behavior.s0_prefix", "FW")
        rename_mode = cfg_get(cfg, "behavior.rename_mode", "rename")  # rename|copy
        quiet = bool(cfg_get(cfg, "behavior.quiet", False))

        # Outputs
        write_log_enabled = bool(cfg_get(cfg, "outputs.write_log", False))
        log_path_str = cfg_get(cfg, "outputs.log_path", "")
        write_version_file = bool(cfg_get(cfg, "outputs.write_version_file", False))
        version_file_path_str = cfg_get(cfg, "outputs.version_file_path", "")
        write_tool_version_file = bool(cfg_get(cfg, "outputs.write_tool_version_file", False))
        tool_version_file_path_str = cfg_get(cfg, "outputs.tool_version_file_path", "")

        # Git / GitHub
        git_tag_enabled = bool(cfg_get(cfg, "git.tag", False))
        git_remote = cfg_get(cfg, "git.remote", "origin")

        gh_release_enabled = bool(cfg_get(cfg, "github.release", False))
        gh_repo = cfg_get(cfg, "github.repository", "")
        gh_token_env = cfg_get(cfg, "github.token_env", "GITHUB_TOKEN")
        gh_release_name = cfg_get(cfg, "github.release_name", "")
        gh_notes_path = cfg_get(cfg, "github.release_notes_path", "")
        gh_draft = bool(cfg_get(cfg, "github.draft", False))
        gh_prerelease = bool(cfg_get(cfg, "github.prerelease", False))
        gh_generate_notes = bool(cfg_get(cfg, "github.generate_notes", True))

        # Version define names
        define_names = {
            "major": cfg_get(cfg, "version.defines.major", "FW_VERSION_MAJOR"),
            "minor": cfg_get(cfg, "version.defines.minor", "FW_VERSION_MINOR"),
            "build": cfg_get(cfg, "version.defines.build", "FW_VERSION_BUILD"),
        }
        logger.info("Using version defines: %s", define_names)

        logger.info("Header: %s", header_path)
        logger.info("Input SREC: %s", srec_path)
        logger.info("Behavior: insert_s0=%s, s0_prefix='%s', rename_mode=%s", insert_s0, s0_prefix, rename_mode)
        logger.info("Outputs: write_log=%s, version_file=%s, tool_version_file=%s",
                    write_log_enabled, write_version_file, write_tool_version_file)
        logger.info("Git: tag=%s, remote=%s", git_tag_enabled, git_remote)
        logger.info("GitHub: release=%s, repo=%s, token_env=%s", gh_release_enabled, gh_repo, gh_token_env)

        # Parse version
        major, minor, build = parse_version_from_header(header_path, define_names, log=logger)
        version_str = f"{major}.{minor}.{build}"
        version_tag = f"v{version_str}"

        # S0
        s0_inserted = False
        removed_s0 = 0
        if insert_s0:
            s0 = srec_s0(f"{s0_prefix} {version_str}")
            try:
                s0_inserted, removed_s0 = inject_single_s0(srec_path, s0_line=s0, log=logger)
                logger.info("S0 record refreshed (removed=%d, inserted=%s)", removed_s0, s0_inserted)
            except Exception as e:
                logger.error("Failed to handle S0 record: %s", e)
                print(f"FAIL v{version_str} (see log)")
                sys.exit(7)
        else:
            logger.info("S0 insertion disabled by config.")
        

        # Rename/copy
        new_name = srec_path.with_name(f"{srec_path.stem}_v{version_str}{srec_path.suffix}")
        if rename_mode == "copy":
            shutil.copy2(srec_path, new_name)
            action = "copied"
            logger.info("Copied file to: %s", new_name)
        else:
            shutil.move(srec_path, new_name)
            action = "renamed"
            logger.info("Renamed file to: %s", new_name)

        # SHA256
        sha256 = hashlib.sha256(new_name.read_bytes()).hexdigest()
        logger.info("SHA256 of output: %s", sha256)

        # Version file (relative to script if provided)
        if write_version_file:
            vf = resolve_from_script(version_file_path_str, script_dir) if version_file_path_str else (new_name.parent / "fw_version.txt")
            vf.parent.mkdir(parents=True, exist_ok=True)
            vf.write_text(version_str, encoding="utf-8")
            logger.info("Wrote version file: %s", vf)

        # Tool version file (optional)
        if write_tool_version_file:
            tvf = resolve_from_script(tool_version_file_path_str, script_dir) if tool_version_file_path_str else (script_dir / f"{TOOL_NAME}.version")
            tvf.parent.mkdir(parents=True, exist_ok=True)
            tvf.write_text(TOOL_VERSION, encoding="utf-8")
            logger.info("Wrote tool version file: %s", tvf)

        # Git info
        rc, branch, _ = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], log=logger)
        rc2, commit, _ = run(["git", "rev-parse", "--short", "HEAD"], log=logger)
        branch = branch if rc == 0 else ""
        commit = commit if rc2 == 0 else ""
        if not branch or not commit:
            logger.warning("Could not resolve branch and/or commit (is this a git repo?)")

        # CI log (one-line)
        if write_log_enabled:
            ci_log_path = resolve_from_script(log_path_str, script_dir) if log_path_str else (new_name.parent / "build_info.log")
            try:
                write_ci_log(
                    ci_log_path,
                    version=version_str,
                    s0_inserted=s0_inserted,
                    action=action,
                    output_file=new_name,
                    header_path=header_path,
                    branch=branch,
                    commit=commit,
                    sha256=sha256,
                    tool_version=TOOL_VERSION,
                    log=logger
                )
            except Exception as e:
                logger.warning("Failed to write CI log '%s': %s", ci_log_path, e)

        # Git tag
        if git_tag_enabled:
            try:
                git_tag_and_push(version_tag, message=f"Firmware {version_str}", remote=git_remote, log=logger)
            except Exception as e:
                logger.error("Git tag/push failed: %s", e)
                print(f"FAIL v{version_str} (see log)")
                sys.exit(2)

        # GitHub release
        if gh_release_enabled:
            if not gh_repo:
                logger.error("GitHub release requested but 'github.repository' is empty in config.")
                print(f"FAIL v{version_str} (see log)")
                sys.exit(3)
            token = os.environ.get(gh_token_env, "")
            if not token:
                logger.error("GitHub release requested but token env '%s' is not set.", gh_token_env)
                print(f"FAIL v{version_str} (see log)")
                sys.exit(4)

            # ensure tag exists remotely (create if missing)
            try:
                git_tag_and_push(version_tag, message=f"Firmware {version_str}", remote=git_remote, log=logger)
            except Exception as e:
                logger.error("Needed to create/push tag for release but failed: %s", e)
                print(f"FAIL v{version_str} (see log)")
                sys.exit(5)

            body = ""
            if gh_notes_path:
                try:
                    body = resolve_from_script(gh_notes_path, script_dir).read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning("Could not read release notes '%s': %s", gh_notes_path, e)

            try:
                create_github_release(
                    owner_repo=gh_repo,
                    token=token,
                    tag=version_tag,
                    name=(gh_release_name or f"Firmware {version_str}"),
                    body=body,
                    draft=gh_draft,
                    prerelease=gh_prerelease,
                    generate_notes=gh_generate_notes,
                    asset=new_name,
                    log=logger
                )
            except Exception as e:
                logger.error("GitHub release failed: %s", e)
                print(f"FAIL v{version_str} (see log)")
                sys.exit(6)

        # Final minimal console output (success) — include tool version for traceability
        print(f"OK v{version_str} -> {new_name.name} (tool {TOOL_VERSION})")

    except SystemExit as se:
        logging.getLogger(TOOL_NAME).error("SystemExit: %s", se)
        print("FAIL (see log)")
        raise
    except Exception as e:
        logging.getLogger(TOOL_NAME).exception("Unhandled exception: %s", e)
        print("FAIL (see log)")
        sys.exit(1)


if __name__ == "__main__":
    main()
# EOF