"""Lifeline command-line entry point.

`lifeline <command> [args...]` dispatches to the existing modules. It only
rewrites argv and calls each module's existing main() — no logic lives here, so
`python3 watch.py …` / `python3 handoff.py …` keep working exactly as before.
"""

import sys

USAGE = """\
lifeline — when your AI hits its limit, your work shouldn't.

usage: lifeline <command> [args...]

commands:
  watch      Wrap an AI CLI and auto-detect its usage-limit message, then
             offer to resume the session in another CLI.
             e.g. lifeline watch -- claude
  handoff    Capture the current Claude session and resume it in another CLI
             right now (no wrapper needed).
             e.g. lifeline handoff --to gemini

Run `lifeline <command> --help` for command-specific options.
"""


def _version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("lifeline")
    except Exception:
        return "0.1.0"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(_version())
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd == "watch":
        import watch

        sys.argv = ["lifeline watch", *rest]
        return watch.main()
    if cmd == "handoff":
        import handoff

        sys.argv = ["lifeline handoff", *rest]
        return handoff.main()

    sys.stderr.write(f"lifeline: unknown command {cmd!r}\n\n")
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
