"""Exact session tracking and the registry used by ``lifeline switch``."""

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import sources

ACTIVE_DIR = Path.home() / ".lifeline" / "active"


def _windows_pid_alive(pid: int) -> bool:
    """Check a Windows process without sending it a console control signal."""
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    error_access_denied = 5
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == error_access_denied


class AmbiguousSessionError(RuntimeError):
    def __init__(self, candidates: Iterable[Path]):
        self.candidates = list(candidates)
        super().__init__(
            "Multiple sessions match this Lifeline launch:\n"
            + "\n".join(f"  - {path}" for path in self.candidates)
        )


def list_sessions(source_name: str) -> List[Path]:
    source = sources.get_source(source_name)
    if not source.root.exists():
        return []
    if source_name == "codex":
        paths = list(source.root.rglob("rollout-*.jsonl"))
        if not paths:
            paths = list(source.root.rglob("*.jsonl"))
    elif source_name == "gemini":
        paths = list(source.root.rglob("chats/session-*.jsonl"))
        if not paths:
            paths = list(source.root.rglob("chats/*.jsonl"))
    else:
        paths = list(source.root.rglob("*.jsonl"))
    return [path.resolve() for path in paths if path.is_file()]


def session_id(path: Path) -> Optional[str]:
    """Read a session identifier without parsing the complete transcript."""
    try:
        with path.open(errors="ignore") as stream:
            for index, line in enumerate(stream):
                if index >= 40:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                value = entry.get("sessionId")
                if value:
                    return str(value)
                if entry.get("type") == "session_meta":
                    value = (entry.get("payload") or {}).get("id")
                    if value:
                        return str(value)
    except OSError:
        return None
    return None


def session_cwd(source_name: str, path: Path) -> Optional[str]:
    try:
        cwd = sources.get_source(source_name).parse(path).get("cwd")
        return str(Path(cwd).resolve()) if cwd else None
    except (OSError, ValueError):
        return None


def snapshot(source_name: str) -> Dict[str, int]:
    result = {}
    for path in list_sessions(source_name):
        try:
            result[str(path)] = path.stat().st_mtime_ns
        except OSError:
            pass
    return result


def _selector_value(command: List[str], names: Iterable[str]) -> Optional[str]:
    names = tuple(names)
    for index, arg in enumerate(command[1:], start=1):
        for name in names:
            if arg == name and index + 1 < len(command):
                value = command[index + 1]
                return value if not value.startswith("-") else None
            if arg.startswith(name + "="):
                return arg.split("=", 1)[1]
    return None


def _uuid_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def requested_session_id(source_name: str, command: List[str]) -> Optional[str]:
    if source_name in ("claude", "gemini"):
        explicit = _selector_value(command, ("--session-id",))
        if explicit:
            return explicit
        return _uuid_value(_selector_value(command, ("--resume", "-r")))
    if source_name == "codex" and len(command) > 2 and command[1] == "resume":
        return _uuid_value(command[2]) if not command[2].startswith("-") else None
    return None


def command_cwd(source_name: str, command: List[str], default: Path) -> Path:
    """Return the workspace the CLI was asked to use, when it exposes one."""
    if source_name == "codex":
        value = _selector_value(command, ("--cd", "-C"))
        if value:
            path = Path(value).expanduser()
            return (default / path).resolve() if not path.is_absolute() else path.resolve()
    return default.resolve()


def prepare_command(source_name: str, command: List[str]):
    """Return (command, expected session id), pinning fresh supported launches."""
    command = list(command)
    requested = requested_session_id(source_name, command)
    if requested:
        return command, requested

    if source_name == "claude":
        has_selector = any(
            arg in ("--continue", "-c", "--resume", "-r", "--session-id")
            or arg.startswith(("--resume=", "--session-id="))
            for arg in command[1:]
        )
    elif source_name == "gemini":
        has_selector = any(
            arg in ("--resume", "-r", "--session-id", "--session-file")
            or arg.startswith(("--resume=", "--session-id=", "--session-file="))
            for arg in command[1:]
        )
    else:
        has_selector = True

    # Claude supports pinning a newly created session with --session-id.
    # Gemini CLI 0.46+ rejects that flag, so Gemini sessions are discovered
    # from the newly created transcript and matching workspace instead.
    if source_name == "claude" and not has_selector:
        expected = str(uuid.uuid4())
        return [*command, "--session-id", expected], expected
    return command, None


@dataclass
class SessionTracker:
    source_name: str
    target: str
    command: List[str]
    cwd: Path
    registry: "ActiveRegistry"

    def __post_init__(self):
        self.cwd = self.cwd.resolve()
        self.before = snapshot(self.source_name)
        self.expected_id = requested_session_id(self.source_name, self.command)
        self.session_path = None
        self.ambiguity = []
        self._last_poll = 0.0
        self.record_path = self.registry.create(
            {
                "source": self.source_name,
                "target": self.target,
                "cwd": str(self.cwd),
                "watcher_pid": os.getpid(),
                "launched_at": time.time(),
                "session_id": self.expected_id,
                "session_path": None,
                "status": "resolving",
            }
        )

    def observe(self, force=False) -> Optional[Path]:
        now = time.monotonic()
        if not force and now - self._last_poll < 0.5:
            return self.session_path
        self._last_poll = now

        paths = list_sessions(self.source_name)
        if self.expected_id:
            matches = [path for path in paths if session_id(path) == self.expected_id]
        else:
            changed = []
            for path in paths:
                try:
                    if self.before.get(str(path)) != path.stat().st_mtime_ns:
                        changed.append(path)
                except OSError:
                    pass
            cwd = str(self.cwd)
            matches = [
                path for path in changed
                if session_cwd(self.source_name, path) == cwd
            ]

        if len(matches) == 1:
            self.session_path = matches[0]
            self.ambiguity = []
            self.registry.update(
                self.record_path,
                session_path=str(self.session_path),
                session_id=session_id(self.session_path) or self.expected_id,
                status="active",
            )
        elif len(matches) > 1:
            self.session_path = None
            self.ambiguity = sorted(matches, key=str)
            self.registry.update(
                self.record_path,
                session_path=None,
                status="ambiguous",
                candidates=[str(path) for path in self.ambiguity],
            )
        return self.session_path

    def require_session(self, prompt=True, input_fn=input, output=None) -> Path:
        path = None
        for _ in range(6):
            path = self.observe(force=True)
            if path or self.ambiguity:
                break
            time.sleep(0.1)
        if path:
            return path
        if self.ambiguity:
            if prompt and sys.stdin.isatty():
                output = output or sys.stderr
                output.write("\nChoose the exact session Lifeline should hand over:\n")
                for index, candidate in enumerate(self.ambiguity, start=1):
                    output.write(f"  {index}. {candidate}\n")
                while True:
                    try:
                        answer = input_fn(
                            f"Choose [1-{len(self.ambiguity)}]: "
                        ).strip()
                    except (EOFError, KeyboardInterrupt):
                        raise RuntimeError("Session selection cancelled.")
                    if answer.isdigit() and 1 <= int(answer) <= len(self.ambiguity):
                        self.session_path = self.ambiguity[int(answer) - 1]
                        self.registry.update(
                            self.record_path,
                            session_path=str(self.session_path),
                            session_id=session_id(self.session_path),
                            status="active",
                        )
                        return self.session_path
                    output.write(
                        f"Invalid choice. Enter 1-{len(self.ambiguity)}.\n"
                    )
            raise AmbiguousSessionError(self.ambiguity)
        raise RuntimeError(
            f"Lifeline could not identify the exact {self.source_name} session yet."
        )

    def close(self):
        self.registry.remove(self.record_path)


class ActiveRegistry:
    def __init__(self, root: Path = ACTIVE_DIR):
        self.root = Path(root)

    def _ensure(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    def create(self, data: dict) -> Path:
        self._ensure()
        path = self.root / f"{data['source']}-{data['watcher_pid']}-{uuid.uuid4().hex}.json"
        self._write(path, data)
        return path

    def update(self, path: Path, **values):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        data.update(values)
        self._write(path, data)

    @staticmethod
    def _write(path: Path, data: dict):
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(data, stream, sort_keys=True)
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def remove(self, path: Path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _pid_alive(pid) -> bool:
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid <= 0:
            return False
        if os.name == "nt":
            return _windows_pid_alive(pid)
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False

    def live(self) -> List[dict]:
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                self.remove(path)
                continue
            if not isinstance(data, dict):
                self.remove(path)
                continue
            if not self._pid_alive(data.get("watcher_pid")):
                self.remove(path)
                continue
            if data.get("source") not in sources.SUPPORTED_SOURCES:
                self.remove(path)
                continue
            if data.get("target") not in sources.SUPPORTED_SOURCES:
                self.remove(path)
                continue
            session_path = data.get("session_path")
            if session_path is not None and not isinstance(session_path, str):
                self.remove(path)
                continue
            candidates = data.get("candidates", [])
            if not isinstance(candidates, list) or not all(
                isinstance(candidate, str) for candidate in candidates
            ):
                self.remove(path)
                continue
            if not session_path and data.get("session_id") and data.get("source"):
                matches = [
                    candidate for candidate in list_sessions(data["source"])
                    if session_id(candidate) == data["session_id"]
                ]
                if len(matches) == 1:
                    session_path = str(matches[0])
                    data.update(session_path=session_path, status="active")
                    self._write(path, data)
            if session_path and not Path(session_path).is_file():
                self.remove(path)
                continue
            data["_record_path"] = str(path)
            records.append(data)
        return sorted(records, key=lambda item: item.get("launched_at", 0), reverse=True)


def choose_active_session(target: str, registry=None, input_fn=input, output=None) -> dict:
    """Choose a live, exactly-resolved protected session for a manual switch."""
    registry = registry or ActiveRegistry()
    output = output or sys.stderr
    choices = []
    for record in registry.live():
        if record.get("source") == target:
            continue
        if record.get("session_path"):
            choices.append(record)
        else:
            for candidate in record.get("candidates", []):
                choice = dict(record)
                choice["session_path"] = candidate
                choice["_ambiguous_record"] = record.get("_record_path")
                choices.append(choice)

    if not choices:
        raise RuntimeError(
            "No live Lifeline-protected session is ready to switch. Start one with "
            "`lifeline claude`, `lifeline codex`, or `lifeline gemini`."
        )
    if len(choices) == 1:
        return choices[0]

    if not sys.stdin.isatty():
        raise RuntimeError(
            "Multiple live Lifeline sessions match. Run `lifeline switch` in an "
            "interactive terminal so you can choose one."
        )

    output.write("\nChoose the session to hand over:\n")
    for index, record in enumerate(choices, start=1):
        location = record.get("cwd") or "(unknown directory)"
        if record.get("_ambiguous_record"):
            location = record["session_path"]
        output.write(
            f"  {index}. {record['source'].title()} in {location}\n"
        )
    while True:
        try:
            answer = input_fn(f"Choose [1-{len(choices)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Session selection cancelled.")
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        output.write(f"Invalid choice. Enter 1-{len(choices)}.\n")
