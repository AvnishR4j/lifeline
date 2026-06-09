"""Lifeline command-line entry point.

`lifeline <command> [args...]` dispatches to the existing modules. It only
rewrites argv and calls each module's existing main() — no logic lives here, so
`python3 watch.py …` / `python3 handoff.py …` keep working exactly as before.
"""

import sys

import session_tracker

SUPPORTED_CLIS = ("claude", "codex", "gemini")
DEFAULT_TARGETS = {
    "claude": "codex",
    "codex": "claude",
    "gemini": "codex",
}

USAGE = """\
lifeline — when your AI hits its limit, your work shouldn't.

usage: lifeline <command> [args...]

commands:
  claude     Start Claude under Lifeline protection; choose Codex or Gemini fallback.
  codex      Start Codex under Lifeline protection; choose Claude or Gemini fallback.
  gemini     Start Gemini under Lifeline protection; choose Codex or Claude fallback.
  switch     Switch a live Lifeline-protected session to another CLI right now.
             e.g. lifeline switch claude
  watch      Wrap an AI CLI and auto-detect its usage-limit message, then
             offer to resume the session in another CLI.
             e.g. lifeline watch -- claude
  handoff    Capture a Claude/Codex/Gemini session and resume it in another CLI
             right now (no wrapper needed).
             e.g. lifeline handoff --from codex --to gemini
  doctor     Check CLI installs, session roots, parser health, and the supported
             bidirectional handoff matrix.

Run `lifeline <command> --help` for command-specific options.
"""


def _version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("lifeline")
    except Exception:
        return "0.2.0"


def _extract_target(args):
    """Return (target, remaining CLI args), validating friendly --to syntax."""
    remaining = []
    target = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            remaining.extend(args[i + 1:])
            break
        if arg == "--to":
            if target is not None or i + 1 >= len(args):
                raise ValueError("Use exactly one `--to {claude,codex,gemini}`.")
            target = args[i + 1]
            i += 2
            continue
        if arg.startswith("--to="):
            if target is not None:
                raise ValueError("Use exactly one `--to {claude,codex,gemini}`.")
            target = arg.split("=", 1)[1]
            i += 1
            continue
        remaining.append(arg)
        i += 1
    return target, remaining


def _choose_target(source: str, input_fn=input, output=None) -> str:
    """Prompt for a fallback target, or use the deterministic default."""
    output = output or sys.stderr
    choices = [cli for cli in SUPPORTED_CLIS if cli != source]
    default = DEFAULT_TARGETS[source]
    ordered = [default] + [choice for choice in choices if choice != default]

    if not sys.stdin.isatty():
        return default

    output.write(f"\nStart {source.title()} under Lifeline protection.\n")
    output.write(f"When {source.title()} hits its limit, switch to:\n")
    for index, target in enumerate(ordered, start=1):
        default_label = " (default)" if target == default else ""
        output.write(f"  {index}. {target.title()}{default_label}\n")

    while True:
        try:
            answer = input_fn(f"Choose [1-{len(ordered)}] (default 1): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            output.write(f"\nUsing default: {default.title()}\n")
            return default
        if not answer:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(ordered):
            return ordered[int(answer) - 1]
        if answer in ordered:
            return answer
        output.write(
            f"Invalid choice. Enter 1-{len(ordered)} or "
            f"{'/'.join(ordered)}.\n"
        )


def _friendly_watch_args(source: str, args):
    explicit_target, cli_args = _extract_target(args)
    if explicit_target is not None:
        if explicit_target not in SUPPORTED_CLIS:
            raise ValueError(
                f"Unsupported target {explicit_target!r}. "
                f"Choose claude, codex, or gemini."
            )
        if explicit_target == source:
            raise ValueError(
                f"Source and target are both '{source}'. Pick a different --to."
            )
        target = explicit_target
    else:
        target = _choose_target(source)

    return [
        f"lifeline {source}",
        "--yes",
        "--new-terminal",
        "--to",
        target,
        "--",
        source,
        *cli_args,
    ]


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(_version())
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd in SUPPORTED_CLIS:
        import watch

        try:
            sys.argv = _friendly_watch_args(cmd, rest)
        except ValueError as e:
            sys.stderr.write(f"lifeline {cmd}: {e}\n")
            return 2
        return watch.main()
    if cmd == "switch":
        if not rest or rest[0] not in ("claude", "codex", "gemini"):
            sys.stderr.write(
                "usage: lifeline switch {claude,codex,gemini} [handoff options]\n"
            )
            return 2
        target, handoff_args = rest[0], rest[1:]
        if "--from" in handoff_args or "--session-file" in handoff_args:
            sys.stderr.write(
                "lifeline switch uses the exact live protected session. For manual "
                "source/file selection, use `lifeline handoff`.\n"
            )
            return 2
        try:
            active = session_tracker.choose_active_session(target)
        except RuntimeError as e:
            sys.stderr.write(f"lifeline switch: {e}\n")
            return 2
        import handoff

        sys.argv = [
            "lifeline switch",
            "--to", target,
            "--from", active["source"],
            "--session-file", active["session_path"],
            *handoff_args,
        ]
        return handoff.main()
    if cmd == "watch":
        import watch

        sys.argv = ["lifeline watch", *rest]
        return watch.main()
    if cmd == "handoff":
        import handoff

        sys.argv = ["lifeline handoff", *rest]
        return handoff.main()
    if cmd == "doctor":
        import doctor

        sys.argv = ["lifeline doctor", *rest]
        return doctor.main()

    sys.stderr.write(f"lifeline: unknown command {cmd!r}\n\n")
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
