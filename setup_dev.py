#!/usr/bin/env python3
"""
Development helper script to mirror the local `protobuf` package into
each relevant subdirectory as a folder symlink.

RUN THIS FILE ON YOUR PC BEFORE STARTING TO WRITE CODE. GAME WOULD NOT RUN OTHERWISE
"""

from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Mapping, Any

if os.name == "nt":
    import winreg

os.chdir(Path(__file__).parent)


PROTOS_DIR_NAME = "protobuf"
LINK_NAME = PROTOS_DIR_NAME
WINDOWS_DEV_MODE_URL = (
    "https://learn.microsoft.com/en-us/windows/advanced-settings/developer-mode"
)
CONFIG_JSONC_NAME = "config.jsonc"
CONFIG_PY_NAME = "config.py"
AUTH_CRYPTO_PY_NAME = "auth_crypto.py"

# ANSI color helpers
GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"


def _rel(path: Path) -> str:
    """Format a path relative to the current working directory."""
    try:
        return os.path.relpath(path, start=Path.cwd())
    except Exception:
        # Fallback to string form if something unexpected happens.
        return str(path)


def info(label: str, msg: str) -> None:
    print(f"{label} {msg}")


def success(label: str, msg: str) -> None:
    # Success-style messages like [CREATE], [WRITE], etc.
    print(f"{GREEN}{label} {msg}{RESET}")


def error(label: str, msg: str) -> None:
    # Error-style messages like [ERROR], [FATAL].
    print(f"{RED}{label} {msg}{RESET}")


def iter_target_directories(root: Path) -> Iterable[Path]:
    """
    Yield immediate subdirectories for which we should create symlinks
    and config files (i.e. skip dunder/hidden dirs and the protobuf dir itself).
    """
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith("__") or name.startswith("."):
            continue
        if name == PROTOS_DIR_NAME:
            # Do not create symlink / config.py inside the protobuf dir itself.
            continue
        yield entry


def get_source_protobuf_dir(root: Path) -> Path:
    src = root / PROTOS_DIR_NAME
    if not src.exists():
        raise FileNotFoundError(f"Source '{PROTOS_DIR_NAME}' directory not found at {src}")
    if not src.is_dir():
        raise NotADirectoryError(f"Expected '{src}' to be a directory")
    return src


def ensure_symlink(
    target_dir: Path,
    source_protobuf_dir: Path,
) -> None:
    """
    Ensure a `protobuf` symlink exists inside `target_dir` pointing to
    `source_protobuf_dir`.

    If a correct symlink already exists, do nothing.
    If a conflicting file/folder exists, print a warning and skip.
    """
    link_path = target_dir / LINK_NAME

    if link_path.is_symlink():
        return

    if link_path.exists():
        info(
            "[INFO]",
            f"Path {_rel(link_path)} already exists and is not a symlink; "
            f"Please remove {link_path.name} manually and rerun this script",
        )
        exit(1)

    rel_target = os.path.relpath(source_protobuf_dir, start=target_dir)

    try:
        os.symlink(rel_target, link_path, target_is_directory=True)
        success("[CREATE]", f"Symlink {_rel(link_path)} -> {rel_target}")
    except OSError as exc:
        handle_symlink_error(exc, link_path)


def handle_symlink_error(exc: OSError, link_path: Path) -> None:
    is_windows = os.name == "nt"

    if is_windows and exc.errno in {
        errno.EPERM,      # Operation not permitted
        getattr(errno, "EACCES", 13),  # Permission denied
        1314,             # ERROR_PRIVILEGE_NOT_HELD (Win32 specific)
    }:
        # Likely case: symlink privilege unavailable (Developer Mode off or
        # not running elevated, depending on Windows version/settings).
        error(
            "[ERROR]",
            (
                f"Failed to create symlink at '{_rel(link_path)}': {exc}.\n"
                "On Windows, this often happens when Developer Mode is not enabled "
                "or the process lacks symlink privileges.\n"
                "To enable Developer Mode, open 'Settings' → 'Privacy & security' "
                "→ 'For developers', turn on Developer Mode, then restart your "
                "terminal or IDE if needed.\n"
                f"More details: {WINDOWS_DEV_MODE_URL}"
            ),
        )
        exit(1)
    else:
        error("[ERROR]", f"Failed to create symlink at '{_rel(link_path)}': {exc!r}")


def load_config_from_jsonc(root: Path) -> Mapping[str, Any]:
    config_path = root / CONFIG_JSONC_NAME
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file '{CONFIG_JSONC_NAME}' not found at {_rel(config_path)}"
        )

    lines: list[str] = []
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith("//"):
            continue
        lines.append(raw_line)

    json_text = "\n".join(lines)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse {CONFIG_JSONC_NAME} as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level object in {CONFIG_JSONC_NAME}, got {type(data)!r}")

    return data


def write_config_py(target_dir: Path, config: Mapping[str, Any]) -> None:
    """
    Creates a dynamic config.py that reads from config.json at runtime,
    and copies the JSON file so the script can find it.
    """
    config_py_path = target_dir / CONFIG_PY_NAME
    json_target_path = target_dir / "config.json"

    # 1. מעתיק את הנתונים לקובץ config.json נקי בתוך התיקייה
    with open(json_target_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

    # 2. כותב את הקוד הדינמי לתוך config.py
    dynamic_code = """import json
import os
import sys

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE_PATH = os.path.join(get_base_dir(), 'config.json')

try:
    with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
except FileNotFoundError:
    print(f"[FATAL ERROR] Could not find config.json at {CONFIG_FILE_PATH}")
    print("Please make sure 'config.json' is in the same folder as the game.exe")
    sys.exit(1)
except json.JSONDecodeError:
    print("[FATAL ERROR] 'config.json' is corrupted or formatted incorrectly!")
    sys.exit(1)

ZONE_HOSTS = config_data.get("ZONE_HOSTS", ["127.0.0.1"])
REDIS_HOST = config_data.get("REDIS_HOST", "127.0.0.1")
REDIS_PASSWORD = config_data.get("REDIS_PASSWORD", "")
ZONE_TCP_PORT = config_data.get("ZONE_TCP_PORT", 8085)
ZONE_UDP_PORT = config_data.get("ZONE_UDP_PORT", 8086)
AUTH_HOST = config_data.get("AUTH_HOST", "127.0.0.1")
AUTH_PORT = config_data.get("AUTH_PORT", 9999)
CHAT_HOST = config_data.get("CHAT_HOST", "127.0.0.1")
CHAT_PORT = config_data.get("CHAT_PORT", 8888)
ZONE_HOST_MAP = config_data.get("ZONE_HOST_MAP", {"0": "127.0.0.1"})
"""

    config_py_path.write_text(dynamic_code, encoding="utf-8")
    success("[WRITE]", f"{_rel(config_py_path)} (Dynamic Version)")
    success("[WRITE]", f"{_rel(json_target_path)}")


def copy_auth_crypto(root: Path, target_dir: Path) -> None:
    """
    Copy the shared auth_crypto.py from the project root into `target_dir`
    so the module can be imported when running from that directory.
    """
    source = root / AUTH_CRYPTO_PY_NAME
    if not source.exists():
        return
    dest = target_dir / AUTH_CRYPTO_PY_NAME
    shutil.copy2(source, dest)
    success("[WRITE]", f"{_rel(dest)}")


def refresh_windows_path() -> None:
    """
    Refresh the PATH environment variable from the Windows registry.
    This allows newly installed programs to be found without restarting the terminal.
    """
    if os.name != "nt":
        return
    
    try:
        # Read PATH from both user and system registry
        user_path = ""
        system_path = ""
        
        # User PATH
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                access=winreg.KEY_READ
            ) as key:
                user_path = winreg.QueryValueEx(key, "Path")[0]
        except (FileNotFoundError, OSError):
            pass
        
        # System PATH
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                access=winreg.KEY_READ
            ) as key:
                system_path = winreg.QueryValueEx(key, "Path")[0]
        except (FileNotFoundError, OSError):
            pass
        
        # Combine and update os.environ (system PATH first, then user PATH)
        path_parts = []
        if system_path:
            path_parts.append(system_path)
        if user_path:
            path_parts.append(user_path)
        
        if path_parts:
            combined_path = os.pathsep.join(path_parts)
            os.environ["PATH"] = combined_path
            info("[INFO]", "Refreshed PATH from Windows registry")
    except Exception as exc:
        info("[INFO]", f"Could not refresh PATH from registry: {exc}")


def ensure_protoc(source_protobuf_dir: Path) -> str:
    """
    Ensure the `protoc` compiler is available.

    Returns the command/path to use when invoking protoc.
    """
    # If already on PATH, just use it.
    existing = shutil.which("protoc")
    if existing:
        return existing

    # Not found: install according to README guidance.
    # On Linux, download the specific release zip and unpack it into a
    # persistent directory under the protobuf folder, then use that binary.
    if os.name != "nt":
        install_dir = source_protobuf_dir / ".protoc"
        bin_dir = install_dir / "bin"
        protoc_path = bin_dir / "protoc"

        if not protoc_path.exists():
            url = (
                "https://github.com/protocolbuffers/protobuf/releases/download/"
                "v33.4/protoc-33.4-linux-x86_64.zip"
            )
            info("[INFO]", f"Downloading protoc from {url}")
            install_dir.mkdir(parents=True, exist_ok=True)
            zip_path = install_dir / "protoc-33.4-linux-x86_64.zip"

            try:
                urllib.request.urlretrieve(url, zip_path)
            except Exception as exc:
                error("[FATAL]", f"Failed to download protoc: {exc}")
                raise SystemExit(1)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(install_dir)
            except Exception as exc:
                error("[FATAL]", f"Failed to unpack protoc archive: {exc}")
                raise SystemExit(1)

        if protoc_path.exists():
            return str(protoc_path)

        error(
            "[FATAL]",
            "Failed to set up protoc on Linux. Please follow protobuf/README.md manually.",
        )
        raise SystemExit(1)

    # Windows: follow README and use winget to install protobuf.
    info("[INFO]", "protoc not found. Attempting installation via winget on Windows...")
    try:
        # Show output in real-time
        completed = subprocess.run(
            ["winget", "install", "protobuf", "-e"],
            check=False,
            text=True,
        )
    except OSError as exc:
        error("[FATAL]", f"Failed to invoke winget to install protoc: {exc}")
        raise SystemExit(1)

    if completed.returncode != 0:
        error(
            "[FATAL]",
            "winget failed to install protobuf. Please install protoc manually "
            "as described in protobuf/README.md.",
        )
        raise SystemExit(completed.returncode)

    # Refresh PATH from registry after installation
    info("[INFO]", "Refreshing PATH to detect newly installed protoc...")
    refresh_windows_path()

    # Re-check PATH after install and refresh.
    new_path = shutil.which("protoc")
    if not new_path:
        error(
            "[FATAL]",
            "protobuf installed via winget but protoc is still not on PATH. "
            "You may need to restart your terminal or add it to PATH manually.",
        )
        raise SystemExit(1)

    return new_path


def ensure_python_protobuf() -> None:
    """
    Ensure the Python 'protobuf' package is installed, using the
    current interpreter's pip module.
    """
    try:
        import google.protobuf  # type: ignore  # noqa: F401
    except ImportError:
        info("[INFO]", "Python package 'protobuf' not found; installing via pip...")
        try:
            # Show output in real-time
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "install", "protobuf"],
                check=False,
            )
        except OSError as exc:
            error("[FATAL]", f"Failed to invoke pip to install protobuf: {exc}")
            raise SystemExit(1)

        if completed.returncode != 0:
            error(
                "[FATAL]",
                "pip failed to install the 'protobuf' package. "
                "Please install it manually with:\n"
                f"  {sys.executable} -m pip install protobuf",
            )
            raise SystemExit(completed.returncode)


def compile_protobufs(source_protobuf_dir: Path) -> None:
    """
    Compile *.proto files in the protobuf directory using protoc.

    Equivalent to running inside the protobuf dir:
        protoc --python_out=. --pyi_out=. *.proto
    """
    # Ensure protoc binary and Python package are available.
    protoc_cmd = ensure_protoc(source_protobuf_dir)
    ensure_python_protobuf()

    proto_files = sorted(source_protobuf_dir.glob("*.proto"))
    if not proto_files:
        info("[INFO]", f"No .proto files found in {_rel(source_protobuf_dir)}; skipping compile.")
        return

    cmd = [
        protoc_cmd,
        "--python_out=.",
        "--pyi_out=.",
        *[p.name for p in proto_files],
    ]

    info(
        "[INFO]",
        f"Compiling {len(proto_files)} .proto file(s) in {_rel(source_protobuf_dir)} with protoc.",
    )

    try:
        # Show output in real-time
        completed = subprocess.run(
            cmd,
            cwd=source_protobuf_dir,
            check=False,
            text=True,
        )
    except OSError as exc:
        error("[FATAL]", f"Failed to invoke protoc: {exc}")
        raise SystemExit(1)

    if completed.returncode != 0:
        error(
            "[FATAL]",
            f"protoc exited with status {completed.returncode}.",
        )
        raise SystemExit(completed.returncode)

    success("[CREATE]", f"Generated Python code from .proto files in {_rel(source_protobuf_dir)}")


def main() -> None:
    root = Path.cwd()
    # First, locate protobuf dir.
    try:
        source_protobuf_dir = get_source_protobuf_dir(root)
    except (FileNotFoundError, NotADirectoryError) as exc:
        error("[FATAL]", f"{exc}")
        raise SystemExit(1)

    # Load shared config.
    try:
        config_mapping = load_config_from_jsonc(root)
    except (FileNotFoundError, ValueError) as exc:
        error("[FATAL]", f"{exc}")
        raise SystemExit(1)

    info("[INFO]", f"Source protobuf directory: {_rel(source_protobuf_dir)}")
    info("[INFO]", f"Configuration source: {_rel(root / CONFIG_JSONC_NAME)}")

    # Then compile protobufs once, before touching target dirs.
    compile_protobufs(source_protobuf_dir)

    any_processed = False
    for target_dir in iter_target_directories(root):
        any_processed = True
        ensure_symlink(target_dir, source_protobuf_dir)
        write_config_py(target_dir, config_mapping)
        copy_auth_crypto(root, target_dir)

    if not any_processed:
        info("[INFO]", "No eligible subdirectories found; nothing to do.")
    
    info(f"{GREEN}[INFO]", f"Finished setup successfully!{RESET}")


if __name__ == "__main__":
    main()

