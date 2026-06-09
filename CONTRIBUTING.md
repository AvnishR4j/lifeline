# Contributing

Use Python 3.9 or newer and keep runtime dependencies platform-specific and minimal.

Before opening a pull request:

```bash
python -m unittest discover -s tests -v
python watch.py --selftest
python -m compileall -q .
python -m build
python -m twine check dist/*
```

Never commit raw AI transcripts, handoff files, API keys, or other credentials.
Parser fixtures must be synthetic or fully sanitized. Compatibility reports should
include CLI versions and `lifeline doctor` output with private paths removed.
