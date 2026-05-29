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

## Reddit — r/ClaudeAI (primary)  ← POST THIS FIRST

**How to post:** Use the **"Images & Video"** tab, upload `lifeline-demo.mp4`
(3.4 MB — autoplays in-feed). Paste the title. Put the body as the FIRST COMMENT
right after posting (video posts often don't take body text). Do NOT use the
"Link" tab — a bare URL has no video and no story, and gets far less traction.

**Title:**
I got tired of losing all my context when Claude hits its usage limit, so I built a tool that hands off to Codex/Gemini automatically

**Body (paste as the first comment):**

You know the moment: you're deep into a debugging session, Claude is mid-edit, and then — "Usage limit reached."

So you switch to another CLI. But it knows nothing. You spend 15 minutes re-explaining the project, the goal, what you already tried. By the time it's caught up, you've lost the thread.

I built Lifeline to kill that moment. When Claude Code hits its limit, one command captures the full state — the task, recent conversation, decisions, and your uncommitted git diff — and resumes you in another CLI (Codex or Gemini) that picks up exactly where you left off. Zero re-explanation.

It also redacts secrets (API keys, tokens, .env values) before any context leaves your machine — I didn't want to ship my own keys to another provider just to keep working.

It can also run as a wrapper that auto-detects the limit message and offers the handoff for you.

Open source, MIT, pure Python (no dependencies): https://github.com/AvnishR4j/lifeline

It's early and rough. I'm genuinely trying to find out: does this happen to you often enough that you'd use it? And which CLI pair matters most — Claude→Codex, Claude→Gemini, something else?

---

## Hacker News — Show HN  ← POST AFTER Reddit reactions come in

**How to post:** HN has no video upload. Put the repo as the post URL (or use a
text post and link both). Submit once, never repost. Reply to every comment fast;
be candid about limitations — HN rewards that, punishes hype. Best time: weekday
~8–10am US Eastern.

**Title:** Show HN: Lifeline – Resume your AI CLI session in another tool when you hit a limit

**URL:** https://github.com/AvnishR4j/lifeline

**Body (the text/first comment):**

When Claude Code hits its usage limit mid-task, you're forced to switch tools and lose all context. Lifeline captures the session state — task, recent turns, decisions, uncommitted git diff — scrubs any secrets, and resumes you in another CLI (Codex or Gemini) with one command. No re-explaining.

Technical notes for HN: it reads Claude Code's local session transcript (~/.claude/projects/*.jsonl), redacts secrets with local regex before anything is sent to another provider, and delivers the handoff inline as the seed prompt (not via a file — target CLIs like Gemini refuse to read gitignored paths). The auto-detection mode wraps the CLI in a PTY — manual pty.fork + select relay rather than pty.spawn, which hangs on non-tty stdin — to watch for the limit message while keeping the wrapped CLI fully interactive. The limit-detection patterns were pulled from the actual strings in the Claude Code binary, and guard against look-alikes ("Context limit reached", "Fast limit reached") that shouldn't trigger a handoff. Pure Python stdlib, no dependencies; macOS/Linux.

Demo (30s): https://github.com/AvnishR4j/lifeline/blob/main/lifeline-demo.mp4

Known limitations and where I'd love feedback: capture is currently Claude-specific (one-directional — see the roadmap for the any→any source-registry plan); it depends on transcript format and limit-message strings (fragile to upstream changes); and prompt-injection from session content into the resuming CLI is only partially mitigated. Curious whether people hit this pain often enough to want it, and what the right second source/target CLI is.

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
