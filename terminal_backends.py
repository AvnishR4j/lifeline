"""Interactive terminal backends for protected CLI sessions."""

import os
import shutil
import sys
import threading
import time

import command_utils


def is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in open("/proc/version", errors="ignore").read().lower()
    except OSError:
        return False


def backend_name() -> str:
    return "windows-conpty" if os.name == "nt" else "unix-pty"


def run_wrapped(command, watcher, on_detect=None, on_activity=None) -> int:
    if os.name == "nt":
        return _run_windows(command, watcher, on_detect, on_activity)
    return _run_unix(command, watcher, on_detect, on_activity)


def _run_unix(command, watcher, on_detect=None, on_activity=None) -> int:
    # Imported lazily so Lifeline remains importable on native Windows.
    import fcntl
    import pty
    import select
    import signal
    import termios
    import tty

    stdin_fd = sys.stdin.fileno()
    stdin_is_tty = sys.stdin.isatty()
    initial_winsize = None
    if stdin_is_tty:
        try:
            initial_winsize = fcntl.ioctl(
                stdin_fd, termios.TIOCGWINSZ, b"\0" * 8
            )
        except OSError:
            pass

    pid, master_fd = pty.fork()
    if pid == 0:
        if initial_winsize is not None:
            try:
                fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSWINSZ, initial_winsize)
            except OSError:
                pass
        os.execvp(command[0], command)
        os._exit(127)

    saved = None
    previous_sigwinch = None
    if stdin_is_tty:
        sync_window_size(master_fd, stdin_fd)

        def _resize_handler(_signum, _frame):
            sync_window_size(master_fd, stdin_fd)

        previous_sigwinch = signal.getsignal(signal.SIGWINCH)
        signal.signal(signal.SIGWINCH, _resize_handler)
        saved = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)

    try:
        while True:
            watch_fds = [master_fd] + ([stdin_fd] if stdin_is_tty else [])
            try:
                rlist, _, _ = select.select(watch_fds, [], [])
            except (OSError, ValueError):
                break

            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 1024)
                except OSError:
                    data = b""
                if not data:
                    break
                if on_activity is not None:
                    on_activity()
                _feed_and_notify(watcher, data, on_detect)
                os.write(sys.stdout.fileno(), data)

            if stdin_is_tty and stdin_fd in rlist:
                data = os.read(stdin_fd, 1024)
                if data:
                    os.write(master_fd, data)
    finally:
        if saved is not None:
            termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, saved)
        if previous_sigwinch is not None:
            signal.signal(signal.SIGWINCH, previous_sigwinch)
        os.close(master_fd)

    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return status


def sync_window_size(master_fd: int, source_fd: int) -> bool:
    """Copy Unix terminal dimensions to a child PTY."""
    if os.name == "nt":
        return False
    import fcntl
    import termios

    try:
        winsize = fcntl.ioctl(source_fd, termios.TIOCGWINSZ, b"\0" * 8)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        return True
    except OSError:
        return False


def _run_windows(command, watcher, on_detect=None, on_activity=None) -> int:
    try:
        import winpty
    except ImportError as exc:
        raise OSError(
            "Native Windows automatic protection requires pywinpty. "
            "Reinstall Lifeline with `py -m pip install --upgrade lifeline`."
        ) from exc

    PTY = winpty.PTY
    read_errors = (EOFError, OSError)
    winpty_error = getattr(winpty, "WinptyError", None)
    if isinstance(winpty_error, type) and issubclass(winpty_error, Exception):
        read_errors += (winpty_error,)

    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    process = PTY(columns, rows)
    process.spawn(command_utils.windows_command_line(command))
    stop = threading.Event()

    def _forward_input():
        import msvcrt

        while not stop.is_set() and process.isalive():
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    key = _windows_special_key(msvcrt.getwch())
                try:
                    process.write(key)
                except read_errors + (TypeError,):
                    return
            else:
                time.sleep(0.01)

    input_thread = None
    if sys.stdin.isatty():
        input_thread = threading.Thread(target=_forward_input, daemon=True)
        input_thread.start()

    try:
        while process.isalive():
            try:
                text = process.read()
            except read_errors:
                break
            if not text:
                time.sleep(0.01)
                continue
            _emit_windows_output(text, watcher, on_detect, on_activity)
            new_columns, new_rows = shutil.get_terminal_size(
                fallback=(columns, rows)
            )
            if (new_columns, new_rows) != (columns, rows):
                columns, rows = new_columns, new_rows
                process.set_size(columns, rows)
        # ConPTY can retain the child's final output after its process exits.
        try:
            trailing = process.read()
        except read_errors:
            trailing = None
        if trailing:
            _emit_windows_output(trailing, watcher, on_detect, on_activity)
    except KeyboardInterrupt:
        try:
            process.write("\x03")
        except read_errors + (TypeError,):
            pass
    finally:
        stop.set()
        if input_thread is not None:
            input_thread.join(timeout=0.2)

    try:
        return int(process.get_exitstatus())
    except read_errors + (AttributeError, TypeError, ValueError):
        return 0


def _feed_and_notify(watcher, data: bytes, on_detect=None):
    was_detected = watcher.detected
    watcher.feed(data)
    if watcher.detected and not was_detected and on_detect is not None:
        on_detect(watcher)


def _emit_windows_output(text, watcher, on_detect=None, on_activity=None):
    if isinstance(text, bytes):
        data = text
        text = text.decode("utf-8", "replace")
    else:
        data = text.encode("utf-8", "replace")
    if on_activity is not None:
        on_activity()
    _feed_and_notify(watcher, data, on_detect)
    sys.stdout.write(text)
    sys.stdout.flush()


def _windows_special_key(code: str) -> str:
    """Translate msvcrt extended keys into terminal escape sequences."""
    return {
        "H": "\x1b[A",  # up
        "P": "\x1b[B",  # down
        "M": "\x1b[C",  # right
        "K": "\x1b[D",  # left
        "G": "\x1b[H",  # home
        "O": "\x1b[F",  # end
        "I": "\x1b[5~",  # page up
        "Q": "\x1b[6~",  # page down
        "R": "\x1b[2~",  # insert
        "S": "\x1b[3~",  # delete
    }.get(code, "")
