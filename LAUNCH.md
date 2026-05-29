# Launch posts (validation drafts)

The goal of posting is **not** upvotes — it's signal. Watch for comments like
"I need this" / "does it do X" (real demand) vs "neat" (polite indifference).
Reply to every comment; that's where you learn what to build next.

## Links (paste where each draft says [link] / [demo video])

- **Repo:** https://github.com/AvnishR4j/lifeline
- **Release page (share this on HN):** https://github.com/AvnishR4j/lifeline/releases/tag/v0.1.0
- **Demo video (direct file):** https://github.com/AvnishR4j/lifeline/releases/download/v0.1.0/lifeline-demo.mov

> Posting tip: on **Reddit and X, upload the .mov directly to the post** so it
> autoplays natively (use the GitHub link only as a backup). On **Hacker News**,
> there are no video uploads — use the release-page link above.

---

## Reddit — r/ClaudeAI (primary)

**Title:** I got tired of losing all my context when Claude hits its usage limit, so I built a tool that hands off to Codex automatically

**Body:**

You know the moment: you're deep into a debugging session, Claude is mid-edit,
and then — *"Usage limit reached. Resets at 2pm."*

So you switch to another CLI. But it knows nothing. You spend 15 minutes
re-explaining the project, the goal, what you already tried. By the time it's
caught up, you've lost the thread.

I built **Lifeline** to kill that moment. When your AI CLI hits its limit, one
command captures the full state — the task, recent conversation, decisions, and
your uncommitted `git diff` — and resumes you in another CLI (Codex today) that
picks up exactly where you left off. Zero re-explanation.

It also **redacts secrets** (API keys, tokens, `.env` values) before any context
leaves your machine — I didn't want to ship my own keys to another provider just
to keep working.

30-second demo: (upload the .mov directly to this post; backup link:
https://github.com/AvnishR4j/lifeline/releases/download/v0.1.0/lifeline-demo.mov )
Code (MIT, ~600 lines of Python): https://github.com/AvnishR4j/lifeline

It's early and rough. I'm genuinely trying to find out: **does this happen to
you often enough that you'd use this?** And which CLI pair matters most to you —
Claude→Codex, Claude→Gemini, something else?

---

## Hacker News — Show HN

**Title:** Show HN: Lifeline – Resume your AI CLI session in another tool when you hit a limit

**Body:**

When Claude Code (or any paid AI CLI) hits its usage limit mid-task, you're
forced to switch tools and lose all context. Lifeline captures the session state
— task, recent turns, decisions, uncommitted git diff — scrubs any secrets, and
resumes you in another CLI with one command. No re-explaining.

Technical notes for HN: it reads the local session transcript, redacts secrets
with local regex before anything is sent to another provider, and the
auto-detection mode wraps the CLI in a PTY (manual pty.fork + select relay, not
pty.spawn, which hangs on non-tty stdin) to watch for the limit message while
keeping the wrapped CLI fully interactive.

Repo: https://github.com/AvnishR4j/lifeline
Demo: https://github.com/AvnishR4j/lifeline/releases/tag/v0.1.0

Known limitations and where I'd love feedback: it depends on the CLI's
transcript format and limit-message strings (fragile to upstream changes), and
prompt-injection from session content into the resuming CLI is only partially
mitigated. Curious whether people hit this pain often enough to want it, and what
the right second target CLI is.

---

## X / Twitter (thread)

1/ When your AI coding CLI hits its usage limit mid-task, you lose everything
switching tools. I built Lifeline to fix that. One command → resume in another
CLI with full context. Zero re-explanation. 🧵 (attach the .mov directly here so
it autoplays; backup: https://github.com/AvnishR4j/lifeline/releases/tag/v0.1.0 )

2/ It captures the task, recent conversation, decisions, and your uncommitted
git diff — then hands off to Codex (more CLIs coming).

3/ And it redacts your API keys / tokens / .env secrets *before* anything leaves
your machine. Switching tools shouldn't mean leaking secrets.

4/ Open source, MIT, ~600 lines of Python:
github.com/AvnishR4j/lifeline
Does this happen to you too? What CLI pair should I support next?

---

## After posting — what to measure

- Comments expressing real need vs. polite interest (track the ratio).
- Most-requested second target CLI (Gemini? Cursor?).
- GitHub stars in 48h (weak signal, but directional).
- Anyone who installs and reports back (strongest signal — chase these people).
