"""Cross-platform command resolution without unsafe shell-string execution."""

import ntpath
import os
import shutil
import subprocess


def resolved_argv(argv, windows=None):
    """Resolve executables and safely replace Windows batch shims when required."""
    argv = list(argv)
    if not argv:
        raise ValueError("Command cannot be empty.")
    windows = os.name == "nt" if windows is None else windows
    executable = shutil.which(argv[0]) or argv[0]
    if windows and ntpath.splitext(executable)[1].lower() in (".cmd", ".bat"):
        # Batch files re-parse arguments internally. npm also installs a
        # PowerShell companion beside each .cmd shim; invoking that directly
        # keeps arbitrary conversation text as data.
        powershell_shim = os.path.splitext(executable)[0] + ".ps1"
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not os.path.isfile(powershell_shim) or not powershell:
            raise OSError(
                f"Cannot safely launch Windows batch shim: {executable}. "
                "Install its PowerShell companion shim or a native executable."
            )
        return [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            powershell_shim,
            *argv[1:],
        ]
    return [executable, *argv[1:]]


def windows_command_line(argv):
    return subprocess.list2cmdline(resolved_argv(argv, windows=True))
