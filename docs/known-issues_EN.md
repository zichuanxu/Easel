# Known Issues

This page tracks known issues relevant to using Easel, along with recommended workarounds. If you hit something not listed here, please open an [Issue](https://github.com/ZJU-REAL/Easel/issues).

---

## Claude CLI route: after a pause, the agent forgets the conversation

- **Affects**: running the agent on the local Claude Code login (`EASEL_AGENT_RUNTIME=claude-cli`) with the default isolated config dir `~/.claude-easel`; observed on OpenClaw 2026.9.7.
- **Symptom**: after a task finishes, a follow-up in the same chat a while later is answered as if the chat were new (for example the agent repeats the profile settings and says there is no task in the message). An immediate follow-up, while the previous Claude Code process is still alive, is fine.
- **Gateway log** (`/tmp/easel-gateway.log`):

  ```
  claude-cli transcript probe v4 miss … expectedPath=~/.claude/projects/<workspace>/<id>.jsonl fileExists=false
  cli session reset: provider=claude-cli reason=transcript-missing
  ```

### Root cause

Before resuming, OpenClaw checks that the previous Claude Code session file exists, but it hardcodes the path to `~/.claude/projects/<workspace>/` and ignores the `CLAUDE_CONFIG_DIR` it passes to claude. Easel isolates Claude Code in `~/.claude-easel`, so the session file lives in `~/.claude-easel/projects/<workspace>/`; OpenClaw does not find it, resets the session, and the agent only sees the current message. The bug is in upstream OpenClaw, not in this repository.

### Workaround

`bash setup.sh` symlinks `~/.claude/projects/<workspace>` to `~/.claude-easel/projects/<workspace>`. Only that one directory is touched: files already in it are moved into the isolated dir first, and a name clash stops the move without overwriting anything. On an existing install, run once:

```bash
python -m easel.claude_cli_link
```

The "Claude CLI session resume" line of `easel doctor` checks the link. Once OpenClaw looks up session files under `CLAUDE_CONFIG_DIR`, the link can be deleted.

---

## Duplicate reply after an "ask_user" prompt in the CLI chat

- **Scope**: `easel chat` (terminal chat) only. **The Web workspace is unaffected.**
- **Symptom**: After the Agent raises an `ask_user` prompt and you answer it, the Agent's next reply may be rendered twice in the terminal (the content is correct — it just shows up twice).
- **Nature**: This is a **display-only** issue. It does not affect the actual conversation content, asset generation, or publishing results.

### Root cause

The issue lives in the **session projection** logic of upstream [OpenClaw](https://www.npmjs.com/package/openclaw), not in the Easel repository.

`easel chat` runs `openclaw tui` under the hood, and OpenClaw's gateway-client rebuilds the transcript in the terminal. When a live reply is mistakenly matched against another row (e.g. the `ask_user` prompt row) and the two do not share a transcript identity, the projection re-inserts the reply, causing the duplicate render.

We verified this root cause and reproduced it in upstream regression tests (3 related cases failed before the fix and all pass after it).

### Upstream fix status

The fix has been submitted to OpenClaw. Tracking PRs:

- openclaw#144730
- openclaw#144892

The fix uses a four-layer strategy: unique full-content match, required terminal evidence, a tentative recovery record, and keeping a distinct later final visible when tentative recovery cannot represent it.

### Workaround and upgrade

- **Recommended**: use the **Web workspace** (`easel web`, `http://localhost:7860` by default). The Web backend renders from the raw event stream itself and does not go through the session-projection logic above, so it is **unaffected** by this issue — and it offers a more complete experience (conversations, assets, accounts, profiles, content library, and publishing management) than the CLI.
- If you prefer `easel chat`: once upstream ships a release with the fix, upgrading OpenClaw resolves it:

  ```bash
  npm i -g openclaw@latest
  ```

- Easel installs the OpenClaw global CLI (a prebuilt artifact), so we **do not vendor the patch inside the Easel repo**; instead we track the latest upstream release, and we plan to add an OpenClaw minimum-version check to `easel doctor`.

## Overseas platform login needs a local desktop, ideally with Google Chrome

- **Affects**: TikTok / YouTube / Instagram / X / Threads on the Accounts page.
- **Behavior**: "登录" opens a Chrome window on the machine running Easel; you sign in there yourself (2FA included), within 10 minutes. Machines without a desktop (Linux servers, no `DISPLAY`) cannot show the window, so the button is disabled.
- **Google sign-in**: Google blocks automation Chromium ("This browser or app may not be secure"). Easel prefers the locally installed Google Chrome and falls back to Playwright's bundled Chromium, where YouTube sign-in will likely fail. Fix: install Google Chrome and sign in again.
- **Network**: overseas platforms are not forced to connect directly. `EASEL_PROXY` is used when set; otherwise the system network settings apply. Domestic platforms still connect directly.
- **Profiles**: `~/.easel-browser-profiles/<Platform>Profile` (e.g. `YouTubeProfile`). "退出" on the Accounts page deletes it.
