# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Easel is a social-media content workbench built as an integration layer on top of **OpenClaw**, a Node.js agent CLI and gateway installed with `npm i -g openclaw`. The agent runs inside the OpenClaw gateway. It routes each request to a skill (`skills/openclaw/<name>/SKILL.md` plus scripts) across five layers: discover → plan → produce → publish → attribute. Easel provides:

- a Python CLI (`easel/`)
- a FastAPI + React web workbench (`web/`)
- the skill library
- account profiles (`profiles/`)
- output/project management (`outputs/`)

Docs, code comments, SKILL.md files, and commit messages are written in Chinese. Match that.

## Commands

```bash
bash setup.sh          # idempotent installer (Windows: .\setup.ps1): .venv, openclaw, `easel` profile, frontend build, skill sync, gateway
source .venv/bin/activate

# Checks CI runs (ubuntu + windows, Python 3.12) — run before committing
python scripts/validate_skills.py          # SKILL frontmatter/layout, output-path and publish-safety contracts
python scripts/validate_skill_commands.py  # `python ...` commands in SKILL.md vs the scripts' real argparse
python -m pytest                           # from repo root; NOT `pytest tests/` (that skips skills/**/tests/)
python -m pytest tests/test_gateway_endpoint.py -q
python -m pytest tests/test_core.py -k resolve_input

# Frontend (web/frontend: React 19 + Vite + TypeScript)
cd web/frontend && npm run build   # tsc -b && vite build → web/frontend/dist/ (what `easel web` serves)
cd web/frontend && npm run lint    # oxlint

# Runtime
easel doctor | easel ping | easel chat | easel web [--port 7860]
easel skill <name> -i "<text or file path>" [-p <profile>]
easel gateway start|stop|restart|status|logs   # wraps scripts/gateway.sh (gateway.ps1 on Windows)
bash openclaw/sync.sh                          # push skills + workspace prompts into the OpenClaw workspace
```

No Python linter or formatter is configured in the repo.

## Architecture

### Everything goes through the OpenClaw agent

Easel never runs a skill itself. Every entry point builds a message and hands it to the agent under the isolated `--profile easel`. The agent then reads the SKILL.md and runs the scripts.

- `easel chat` calls `openclaw tui`. It must be `tui`: the `chat` alias forces local mode, which conflicts with the running gateway.
- `easel skill` calls `openclaw agent --message "请执行 /<skill>，内容如下：..."`.
- The web backend (`/api/chat/stream`) uses one of two transports, set by `EASEL_CHAT_TRANSPORT`:
  - `http` (default): talks to the resident gateway's OpenAI-compatible `/v1/chat/completions`.
  - `cli`: spawns `openclaw agent` on every turn.

  The transport is pinned per session and must never switch mid-session, because the two paths write different transcripts and switching loses the history.
- Streaming tokens and thinking come from tailing the gateway's raw-stream file (`EASEL_RAW_STREAM_PATH`, default `/tmp/easel-raw-stream.jsonl`). This default must stay identical in `web/app.py` and `scripts/gateway.sh`.
- `easel/gateway_questions.py` turns the agent's `ask_user` calls into web question cards. It talks to the gateway over WebSocket RPC with an Ed25519 device key, and disables itself for the rest of the process if the gateway doesn't support it.

OpenClaw state lives in `~/.openclaw-easel/`: `openclaw.json`, and session transcripts under `agents/main/sessions/`. The gateway log is `/tmp/easel-gateway.log`. `openclaw/openclaw.json5` is reference-only; `setup.sh` writes the real config with `openclaw config set`.

### Single-source-of-truth modules — never re-hardcode these values

- `easel/timeouts.py` — every timeout, shared by the CLI, web, and skill entry points.
- `easel/gateway_endpoint.py` — gateway port, host, and URLs.
  - Non-default OpenClaw profiles do **not** use port 18789. The port is `20000 + fnv1a32(profile) % 40000`, hashed case-sensitively, so `easel` → 37289.
  - Resolution order: env (`OPENCLAW_GATEWAY_PORT`, `EASEL_GATEWAY_PORT`) → `openclaw.json` → profile hash.
  - Stdlib-only, because `gateway.sh` calls it through the system `python3 -c`.
- `easel/openclaw_workspace.py` — the workspace directory the agent actually reads.
  - The layout changed between OpenClaw 2026.6.x (`~/.openclaw/workspace-easel`) and 2026.9.x (`~/.openclaw-easel/workspace`).
  - It asks `openclaw status --json` first. Its `__main__` must print exactly one line, because `sync.sh` and `setup.ps1` read that line as the path.
- `easel/openclaw_workspace.py` `state_dir()` / `config_path()` — the `~/.openclaw-easel` state dir, overridable via `EASEL_OPENCLAW_STATE_DIR`. Resolve it at call time. A hardcoded `Path.home()/".openclaw-easel"` is how the web tests once rewrote a developer's real `openclaw.json`.
- `easel/openclaw_cmd.py` — `openclaw_base_cmd()`. Never spawn a literal `"openclaw"`: on Windows that is a `.cmd` shim, which breaks CreateProcess and multi-line messages.
- `easel/persona.py` — profiles are injected inline as a message prefix (`我当前使用的画像是「X」。`), never through a global USER.md or MEMORY.md. The agent reads `profiles/<X>/*.md` itself.

### The agent reads synced copies, not this repo

`openclaw/sync.sh` (and the equivalent step in `setup.ps1`) copies:

- `skills/openclaw/*` → `<workspace>/skills/`, removing skills that no longer exist in the repo
- `skills/shared/` → `<workspace>/shared/`
- `openclaw/workspace/{AGENTS,SOUL}.md` into the workspace, appending the runtime project-root path to AGENTS.md

It also empties the global `MEMORY.md` and symlinks `profiles/` (as `easel-profiles`) and `outputs/` into the workspace.

**After you edit a skill or the workspace prompts, re-run sync before testing through the agent.**

Prompt layering is described in `docs/prompt-stack.md`: SOUL.md (persona) → AGENTS.md (routing, orchestration, publish-safety rules; the most important file) → CONTEXT.md → each SKILL, loaded on demand.

### Skill contract (`docs/SKILL-SPEC.md`, enforced by the validators)

- **SKILL.md format:** keep it under 200 lines. Frontmatter allows only:
  - `name`
  - `description` — in Chinese, stating what the skill does, when it should trigger, and its boundary with neighboring skills
  - `layer` — one of `discover/plan/produce/publish/attribute/general`
  - optionally `metadata.openclaw`

  Put provenance in `EASEL-META.md`, domain knowledge in `references/`, and executables in `scripts/`.
- **Shared scripts:** cross-skill scripts live in `skills/shared/scripts/` and are run from the project root (`cd <root> && python skills/shared/scripts/<x>.py ...`).
- **Changing a script's CLI:** update every SKILL.md that documents it, or `validate_skill_commands.py` fails.
- **Outputs:** one project per `outputs/<human-readable topic>/`.
  - Deliverables go in the project root. Intermediates go in `assets/`.
  - Metadata goes in `.easel.json`, written through `skills/shared/scripts/manifest.py` (`meta`, `record`, `latest`, `read`).
  - New scripts must call `output_paths.validate_output_path()` before writing.
  - `_`-prefixed directories (`_login`, `_publish`, `_scratch`, …) hold system state.
  - Generic topic names (`test`, `tmp`, `xhs`, …) and loose files directly under `outputs/` are rejected.
- **Publishing and commenting scripts:**
  - Dry-run by default; send for real only with `--exec`.
  - Call `content_guard.guard_or_die(...)` before sending. Secrets make it exit with code 7 (fail-closed).
  - Register every new publisher in `PUBLISH_SCRIPT_CONTRACTS` in `scripts/validate_skills.py`.
- **Adding a skill:** also add it to `docs/skill-function-mapping.md` (which tracks the skill count) and `web/frontend/src/lib/skillDisplayNames.ts` (the Chinese display name).

### Web backend (`web/app.py`)

`web/app.py` is a single ~4k-line FastAPI module. It serves `web/frontend/dist/`, falling back to `web/static/index.html`, and binds `0.0.0.0:7860` with **no auth**. These safeguards stand in for auth:

- The `local_write_guard` middleware allows non-GET requests only with a local `Origin`, or with no `Origin` from a loopback peer.
- TrustedHost and CORS allowlists (`EASEL_EXTRA_ORIGINS`, `EASEL_EXTRA_HOSTS`, `VSCODE_PROXY_URI`).
- Path-traversal checks on the file, output, and media routes.
- SSRF and value guards on writes to `.env`. `setup.sh` sources `.env`, so an injected value there becomes code execution.

The 定时任务 page (`/api/cron*`) manages OpenClaw cron jobs over gateway RPC through `easel/gateway_cron.py`. It only creates agentTurn jobs (never command/script jobs, which would run shell on the gateway), keeps plugin-declared system jobs read-only, and enforces a 10-minute minimum interval.

`tests/test_web_security.py` covers these safeguards. Keep it passing whenever you touch `.env` writes, tool installs, or file routes.

The frontend calls the API through paths relative to the current page (no Vite proxy). To check a UI change, run `npm run build` and then `easel web`.

### Tests

Tests put `web/` and `skills/shared/scripts/` on `sys.path`, then import `web/app.py` as `app` and shared scripts by bare module name (pytest runs with `--import-mode=importlib`). Tests must never call real models or platforms, and must never touch the user's `.env` or OpenClaw config. Sandbox with `tmp_path` and `monkeypatch`, for example `monkeypatch.setattr(web, "ENV_FILE", tmp_env)`.

The root `conftest.py` has an autouse fixture that points `EASEL_OPENCLAW_STATE_DIR` at a temp dir for every test. It lives at the repo root because a `tests/conftest.py` collides with `skills/openclaw/skill-wechat-publisher/tests/conftest.py`: both directories have an `__init__.py`, so both files get the module name `tests.conftest`.

The agent can run through OpenClaw's `claude-cli` runtime instead of an API key, using the local Claude Code login. Opt in with `EASEL_AGENT_RUNTIME=claude-cli` in `.env` (or setup wizard option 4, or Settings → 对话 → 本机 Agent 「一键接入」 for Claude Code, which writes the same config through `easel/claude_cli_route.py` and records `EASEL_AGENT_RUNTIME` in `.env`; keep its rules in step with `setup.sh`). `setup.sh` then writes:

- `agents.defaults.models["anthropic/<model>"].agentRuntime.id = "claude-cli"`
- `env.vars.CLAUDE_CONFIG_DIR`, default `~/.claude-easel`. `EASEL_CLAUDE_CONFIG_DIR=shared` disables isolation.

The isolated dir keeps personal `~/.claude` plugins, hooks and CLAUDE.md out of the agent.

Constraints:
- OpenClaw passes `env.vars` literally, so the path must be absolute.
- Changing the dir needs a gateway `restart`, and old sessions need `/reset`.
- In shell scripts, write `${VAR}` before full-width punctuation. macOS bash 3.2 under a UTF-8 locale otherwise swallows the bytes into the variable name, and `set -u` aborts; a static test enforces this.

`easel doctor` checks the route with `claude auth status --json`.

## Conventions

- Commit and PR titles look like `fix(gateway): <中文描述>`. Allowed prefixes are `feat/fix/docs/chore/polish`. One concern per PR.
- OpenClaw bugs get fixed upstream, not patched here. Surface environment problems through `easel doctor` checks or `docs/known-issues.md`.
- Register any third-party asset or skill in `docs/ACKNOWLEDGMENTS.md`.
- CI runs on Windows too. Keep file I/O explicitly UTF-8, and keep POSIX-only assumptions out of Python code paths.
