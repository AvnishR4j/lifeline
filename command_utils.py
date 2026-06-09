"""Cross-platform command resolution without shell-string execution."""

import ntpath
import os
import shutil
import subprocess


def resolved_argv(argv, windows=None):
    """Resolve executables and wrap Windows cmd/bat shims when required."""
    argv = list(argv)
    if not argv:
        raise ValueError("Command cannot be empty.")
    windows = os.name == "nt" if windows is None else windows
    executable = shutil.which(argv[0]) or argv[0]
    if windows and ntpath.splitext(executable)[1].lower() in (".cmd", ".bat"):
        command = subprocess.list2cmdline([executable, *argv[1:]])
        shell = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        return [shell, "/d", "/s", "/c", command]
    return [executable, *argv[1:]]


def windows_command_line(argv):
    return subprocess.list2cmdline(resolved_argv(argv, windows=True))
