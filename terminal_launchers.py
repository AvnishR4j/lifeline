"""Open an already-redacted handoff in a new platform terminal."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def launcher_name() -> str:
    if sys.platform == "darwin":
        return "terminal-app"
    if os.name == "nt":
        if shutil.which("wt.exe"):
            return "windows-terminal"
        if shutil.which("powershell.exe") or shutil.which("pwsh.exe"):
            return "powershell"
        return "cmd"
    return "after-exit"


def supports_new_terminal() -> bool:
    return sys.platform == "darwin" or os.name == "nt"


def launch_new_terminal(target: str, handoff_path: Path, handoff_script: Path):
    launcher = [
        sys.executable,
        str(handoff_script.resolve()),
        "--resume-file",
        str(handoff_path.resolve()),
        "--to",
        target,
    ]
    if sys.platform == "darwin":
        return _launch_macos(launcher)
    if os.name == "nt":
        return _launch_windows(launcher)
    raise OSError("Immediate new-terminal handoff is unavailable on this platform.")


def _launch_macos(launcher):
    if shutil.which("osascript") is None:
        raise OSError("Could not find osascript, required to open Terminal.app.")
    command = f"cd {shlex.quote(str(Path.cwd()))} && {shlex.join(launcher)}"
    script = (
        'tell application "Terminal"\n'
        "activate\n"
        f"do script {_applescript_string(command)}\n"
        "end tell"
    )
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, check=False
    )
    _raise_on_failure(result, "Terminal.app")


def _launch_windows(launcher):
    cwd = str(Path.cwd())
    attempts = []
    wt = shutil.which("wt.exe")
    if wt:
        attempts.append([wt, "-d", cwd, *launcher])
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if powershell:
        arguments = ", ".join(_powershell_quote(value) for value in launcher[1:])
        attempts.append(
            [
                powershell,
                "-NoProfile",
                "-Command",
                f"Start-Process -WorkingDirectory {_powershell_quote(cwd)} "
                f"-FilePath {_powershell_quote(launcher[0])} "
                f"-ArgumentList @({arguments})",
            ]
        )
    cmd = shutil.which("cmd.exe")
    if cmd:
        attempts.append(
            [cmd, "/c", "start", "", "/d", cwd, *launcher]
        )

    failures = []
    for argv in attempts:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return
        failures.append(result.stderr.strip() or result.stdout.strip() or str(argv[0]))
    detail = "; ".join(failures) if failures else "no supported terminal launcher found"
    raise OSError(f"Failed to open a new Windows terminal: {detail}")


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _raise_on_failure(result, label):
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise OSError(f"Failed to open {label}: {detail}")
