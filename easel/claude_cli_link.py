"""Claude CLI 路线的续聊兜底：把 ~/.claude/projects/<工作区> 软链到隔离配置目录里的同名目录。

背景（OpenClaw 2026.9.7 实测）：续聊前 OpenClaw 先确认上一轮的 Claude Code 会话文件还在，
但它把路径写死成 $HOME/.claude/projects/<工作区>/<会话 id>.jsonl
（dist/claude-cli-project-dir-*.mjs 的 resolveClaudeCliProjectDirForWorkspace），不看传给 claude 的
CLAUDE_CONFIG_DIR。Easel 默认把 Claude Code 隔离到 ~/.claude-easel，会话文件其实写在
~/.claude-easel/projects/<工作区>/ —— OpenClaw 找不到就判 transcript-missing、重置会话，
隔一会儿再追问时 agent 只看得到当前这一条消息。网关日志里是这几行：
    claude-cli transcript probe v4 miss … expectedPath=…/.claude/projects/… fileExists=false
    cli session reset: provider=claude-cli reason=transcript-missing
把那个目录软链到隔离目录后，OpenClaw 能找到文件，照常 --resume。等 OpenClaw 按
CLAUDE_CONFIG_DIR 找文件了，这个软链就多余了，删掉即可。

只动 ~/.claude/projects 下 OpenClaw 工作区对应的那一个目录：原来是普通目录的，里面的东西先
挪进隔离目录（同名冲突就停下、什么都不覆盖）；已经是指向别处的软链就不碰。

用法：python -m easel.claude_cli_link [--check] [--config-dir DIR] [--workspace DIR]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import unicodedata
from pathlib import Path

_MAX_KEY_LEN = 200   # 与 OpenClaw 的 MAX_SANITIZED_PROJECT_LENGTH 一致


def _utf16_units(text: str) -> list[int]:
    """JS 的 charCodeAt 按 UTF-16 码元计：BMP 以外的字符算两个。"""
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def _hash36(text: str) -> str:
    """OpenClaw simpleHash36：hash = hash * 31 + charCode，按 uint32 截断，转 36 进制。"""
    h = 0
    for unit in _utf16_units(text):
        h = (h * 31 + unit) & 0xFFFFFFFF
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        h, r = divmod(h, 36)
        out = digits[r] + out
        if not h:
            return out


def canonical_workspace(workspace: str | os.PathLike) -> str:
    """与 OpenClaw canonicalizeWorkspaceDir 一致：绝对路径 → realpath → NFC。"""
    return unicodedata.normalize("NFC", os.path.realpath(os.path.abspath(os.fspath(workspace))))


def project_key(workspace: str | os.PathLike) -> str:
    """与 OpenClaw sanitizeClaudeCliProjectKey 一致：非字母数字换成 -，超长截断加哈希。

    JS 的正则替换和 length 都按 UTF-16 码元算：emoji 这类 BMP 以外的字符要换成两个 -。
    """
    ws = canonical_workspace(workspace)
    key = "".join(chr(u) if u < 128 and chr(u).isalnum() else "-" for u in _utf16_units(ws))
    if len(key) <= _MAX_KEY_LEN:
        return key
    return f"{key[:_MAX_KEY_LEN]}-{_hash36(ws)}"


def _home(home: str | os.PathLike | None) -> Path:
    # OpenClaw 取 process.env.HOME，没有才退 os.homedir()
    return Path(home) if home else Path(os.environ.get("HOME") or Path.home())


def link_paths(config_dir: str | os.PathLike, workspace: str | os.PathLike,
               home: str | os.PathLike | None = None) -> tuple[Path, Path]:
    """(OpenClaw 去找的目录, Claude Code 实际写会话的目录)。"""
    key = project_key(workspace)
    return _home(home) / ".claude" / "projects" / key, Path(config_dir).expanduser() / "projects" / key


def _skip_reason(config_dir: str | None, home: Path) -> str | None:
    if os.name == "nt":
        return "Windows 不走 Claude CLI 路线，跳过"
    if not config_dir or not config_dir.strip():
        return "共用个人 ~/.claude，不需要软链"
    cfg = Path(config_dir).expanduser()
    if not cfg.is_absolute():
        return f"CLAUDE_CONFIG_DIR={config_dir} 不是绝对路径，先按 easel doctor 的提示改好"
    if os.path.realpath(cfg) == os.path.realpath(home / ".claude"):
        return "CLAUDE_CONFIG_DIR 就是 ~/.claude，不需要软链"
    return None


def check_link(config_dir: str | None, workspace: str | os.PathLike,
               home: str | os.PathLike | None = None) -> tuple[bool, str]:
    """只读检查（easel doctor 用）。"""
    home_dir = _home(home)
    skip = _skip_reason(config_dir, home_dir)
    if skip:
        return True, skip
    link, target = link_paths(config_dir, workspace, home_dir)
    if link.is_symlink() and os.path.realpath(link) == os.path.realpath(target):
        return True, f"{link} → {target}"
    fix = "运行 python -m easel.claude_cli_link（或重跑 bash setup.sh）"
    if link.is_symlink():
        return False, f"{link} 指向 {os.readlink(link)}，不是 {target}；隔一会儿再追问会丢上下文。{fix}"
    return False, (f"OpenClaw 续聊时到 {link} 找会话文件，而 Claude Code 写在 {target}，"
                   f"隔一会儿再追问会丢上下文。{fix}")


def ensure_link(config_dir: str | None, workspace: str | os.PathLike,
                home: str | os.PathLike | None = None) -> tuple[bool, str]:
    """建软链（幂等）。返回 (是否就绪, 说明)。"""
    home_dir = _home(home)
    skip = _skip_reason(config_dir, home_dir)
    if skip:
        return True, skip
    link, target = link_paths(config_dir, workspace, home_dir)
    try:
        return _ensure(link, target)
    except OSError as exc:
        return False, f"建软链失败（{exc}）；{link} 和 {target} 里的文件都没删，处理后重试"


def _ensure(link: Path, target: Path) -> tuple[bool, str]:
    target.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if os.path.realpath(link) == os.path.realpath(target):
            return True, f"已就绪：{link} → {target}"
        return False, f"{link} 已是指向 {os.readlink(link)} 的软链，没动它；需要续聊请手动改指向 {target}"
    moved = 0
    if link.exists():
        if not link.is_dir():
            return False, f"{link} 是个文件，没动它；删掉或改名后重试"
        for entry in sorted(link.iterdir()):
            dest = target / entry.name
            if not dest.exists() and not dest.is_symlink():
                shutil.move(str(entry), str(dest))
                moved += 1
            elif entry.is_dir() and not entry.is_symlink() and not any(entry.iterdir()):
                entry.rmdir()   # 两边都有的空目录（如 memory/）
            else:
                return False, (f"{entry} 和 {dest} 同名，没有覆盖任何东西；"
                               f"挪走其中一个后重试（已挪过去 {moved} 个）")
        link.rmdir()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target, target_is_directory=True)
    extra = f"，挪入 {moved} 个原有文件" if moved else ""
    return True, f"已建软链：{link} → {target}{extra}"


def from_openclaw() -> tuple[bool, str | None]:
    """(是否走 Claude CLI runtime, gateway 里 claude 实际用的 CLAUDE_CONFIG_DIR；空串 = ~/.claude)。"""
    import json

    from easel.commands.doctor import CLAUDE_CLI_RUNTIME, _agent_runtime_id, _claude_config_dir
    from easel.openclaw_workspace import config_path

    try:
        cfg = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, None
    if not isinstance(cfg, dict) or _agent_runtime_id(cfg) != CLAUDE_CLI_RUNTIME:
        return False, None
    return True, _claude_config_dir(cfg)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Claude CLI 路线续聊兜底：软链 ~/.claude/projects/<工作区>")
    ap.add_argument("--check", action="store_true", help="只检查，不改动")
    ap.add_argument("--config-dir", help="Claude Code 配置目录（默认读 openclaw.json）")
    ap.add_argument("--workspace", help="OpenClaw 工作区目录（默认问 openclaw）")
    args = ap.parse_args(argv)

    config_dir = args.config_dir
    if config_dir is None:
        uses_cli, config_dir = from_openclaw()
        if not uses_cli:
            print("agent 没走 Claude CLI 路线，不需要软链")
            return 0
    workspace = args.workspace
    if workspace is None:
        from easel.openclaw_workspace import workspace_dir
        workspace = str(workspace_dir())
    ok, msg = (check_link if args.check else ensure_link)(config_dir, workspace)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
