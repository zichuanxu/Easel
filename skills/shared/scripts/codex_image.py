#!/usr/bin/env python3
"""codex_image.py — 用本机 Codex CLI 生图 / 改图（ChatGPT 登录，不需要 API key）。

ai_image.py 在 IMG_PROVIDER=codex-cli（或 --mode codex）时调用本模块，不单独作为命令行入口。

原理：`codex exec` 非交互跑一轮，让 Codex 用内建的图片生成工具出图。图片落在
$CODEX_HOME/generated_images/<thread_id>/，按 --json 事件流里的 thread_id 去取 ——
模型自己在回复里报的路径不可靠（实测常回「工具未返回路径」，但图其实已经存好了）。
Codex 以只读沙箱、临时空目录、--ephemeral（不写会话记录）运行，碰不到项目文件。

可调项（.env 或环境变量；默认值都在下面这几个常量里，改一处全局生效）：
    IMG_CODEX_MODEL    模型，默认 DEFAULT_MODEL
    IMG_CODEX_TIMEOUT  单张超时秒数，默认 DEFAULT_TIMEOUT
    IMG_CODEX_BIN      codex 可执行文件路径，默认自动查找（PATH + 常见安装目录）
    CODEX_HOME         Codex 数据目录，默认 ~/.codex（和 Codex CLI 自己的约定一致）
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_MODEL = "gpt-6.1-sol"
DEFAULT_TIMEOUT = 300          # 实测单张 60–75 秒，留足余量
LOGIN_CHECK_TIMEOUT = 20
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
INSTALL_HINT = "安装：npm i -g @openai/codex；登录：codex login（用 ChatGPT 账号）"

_WINDOWS = os.name == "nt"
# Windows 上 npm 装的 codex 是 .cmd 包装，参数要经 cmd.exe 再解析一遍：这些字符会被当成命令语法
_CMD_META = '"%^&|<>!'
_CMD_META_FULLWIDTH = str.maketrans({'"': "”", "%": "％", "^": "＾", "&": "＆",
                                     "|": "｜", "<": "＜", ">": "＞", "!": "！"})


class CodexImageError(RuntimeError):
    """Codex 生图失败：消息直接给用户看，写清原因和怎么修。"""


@dataclass(frozen=True)
class CodexConfig:
    bin: str
    model: str
    timeout: int
    home: Path


def codex_home(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("CODEX_HOME") or Path.home() / ".codex").expanduser()


def _candidate_dirs() -> list[Path]:
    """gateway / agent 起脚本时 PATH 未必包含用户 shell 里的这些目录。"""
    home = Path.home()
    dirs = [home / ".local" / "bin", codex_home() / "packages" / "standalone" / "current" / "bin",
            Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
            home / ".npm-global" / "bin", home / ".volta" / "bin", home / ".bun" / "bin"]
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(Path(appdata) / "npm")
    return dirs


def _is_batch(path: str) -> bool:
    return _WINDOWS and Path(path).suffix.lower() in (".cmd", ".bat")


def _prefer_exe(found: str) -> str:
    """Windows 上找到的是 npm 的 .cmd 包装时，尽量换成同一安装里的原生 codex.exe（不经 cmd.exe）。"""
    if not _is_batch(found):
        return found
    for exe in sorted(Path(found).parent.glob("node_modules/@openai/codex*/**/codex.exe")):
        return str(exe)
    return found


def find_codex(explicit: str | None = None) -> str | None:
    """IMG_CODEX_BIN（显式指定就只认它）→ PATH → 常见安装目录。找不到返回 None。"""
    if explicit:
        p = Path(explicit).expanduser()
        return str(p) if p.is_file() else None
    found = shutil.which("codex")
    if found:
        return _prefer_exe(found)
    for d in _candidate_dirs():
        found = shutil.which("codex", path=str(d))
        if found:
            return _prefer_exe(found)
    return None


def _positive_int(raw: str | None, default: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def load_config(env: Mapping[str, str] | None = None) -> CodexConfig:
    env = os.environ if env is None else env
    explicit = (env.get("IMG_CODEX_BIN") or "").strip() or None
    binary = find_codex(explicit)
    if not binary:
        where = f"IMG_CODEX_BIN={explicit} 不是文件。" if explicit else "找不到 codex 命令。"
        raise CodexImageError(f"{where}{INSTALL_HINT}")
    return CodexConfig(
        bin=binary,
        model=(env.get("IMG_CODEX_MODEL") or "").strip() or DEFAULT_MODEL,
        timeout=_positive_int(env.get("IMG_CODEX_TIMEOUT"), DEFAULT_TIMEOUT),
        home=codex_home(env),
    )


def login_status(cfg: CodexConfig) -> tuple[bool, str]:
    """`codex login status` 只读本地登录态，不发请求。返回 (已登录, 说明)。"""
    try:
        proc = subprocess.run([cfg.bin, "login", "status"], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=LOGIN_CHECK_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"无法运行 codex login status：{exc}"
    text = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    last = text[-1].strip() if text else ""
    return proc.returncode == 0, last or f"退出码 {proc.returncode}"


def quick_status(env: Mapping[str, str] | None = None) -> tuple[bool, str]:
    """不起子进程的快速状态（设置页用）：codex 在不在、本地有没有登录凭据。"""
    env = os.environ if env is None else env
    try:
        cfg = load_config(env)
    except CodexImageError:
        return False, "未安装 codex"
    if not (cfg.home / "auth.json").is_file():
        return False, "未登录（终端运行 codex login）"
    return True, "已配置"


def orientation(size: str) -> str:
    """把 --size（像素 1024x1536 或比例 9:16）换成给模型的画幅描述。"""
    m = re.fullmatch(r"\s*(\d+)\s*[x×:]\s*(\d+)\s*", size or "")
    if not m:
        return "方形（1:1）"
    w, h = int(m.group(1)), int(m.group(2))
    if w == 0 or h == 0 or w == h:
        return "方形（1:1）"
    return f"横版（宽:高 约 {w}:{h}）" if w > h else f"竖版（宽:高 约 {w}:{h}）"


def build_prompt(prompt: str, size: str, edit: bool) -> str:
    # 压成一行：Windows 上 codex 是 npm 的 .cmd 包装，多行参数会被截断
    body = " ".join((prompt or "").split())
    head = ("以附带的图片为基础，用图片生成工具编辑出恰好一张新图。" if edit
            else "使用图片生成工具生成恰好一张图片。")
    return (f"{head}画幅：{orientation(size)}。要求：{body}。"
            "只生成这一张，不要读写任何文件，不要运行命令。")


def _kill_tree(proc: subprocess.Popen) -> None:
    """连同 codex 拉起的子进程一起结束：只杀直接子进程会留下还在出图（占额度）的孤儿。"""
    try:
        if _WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=15)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def _run(cmd: list[str], timeout: int, cwd: str) -> subprocess.CompletedProcess:
    """起 codex（独立进程组）并等它结束；超时则结束整棵进程树后抛 TimeoutExpired。"""
    group = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if _WINDOWS
             else {"start_new_session": True})
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", cwd=cwd, **group)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def _events(stdout: str) -> list[dict]:
    out = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _thread_id(events: list[dict]) -> str | None:
    for ev in events:
        if ev.get("type") == "thread.started" and ev.get("thread_id"):
            return str(ev["thread_id"])
    return None


def _messages(events: list[dict]) -> list[str]:
    msgs = []
    for ev in events:
        item = ev.get("item") or {}
        if ev.get("type") == "item.completed" and item.get("type") == "agent_message":
            msgs.append(str(item.get("text") or "").strip())
    return [m for m in msgs if m]


def _errors(events: list[dict]) -> list[str]:
    errs = []
    for ev in events:
        if ev.get("type") in ("error", "turn.failed"):
            err = ev.get("error") if isinstance(ev.get("error"), dict) else {}
            errs.append(str(err.get("message") or ev.get("message") or ev)[:300])
    return errs


def _fresh_images(folder: Path, since: float) -> list[Path]:
    if not folder.is_dir():
        return []
    found = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.stat().st_mtime >= since]
    return sorted(found, key=lambda p: p.stat().st_mtime)


def _paths_in_messages(messages: list[str], since: float) -> list[Path]:
    """兜底：thread 目录里没有时，看模型回复里有没有提到本轮新生成的图片路径。"""
    out = []
    for msg in messages:
        for raw in re.findall(r"((?:[A-Za-z]:[\\/]|/)[^\s`'\"<>]+?\.(?:png|jpe?g|webp))", msg, flags=re.I):
            p = Path(raw)
            if p.is_file() and p.stat().st_mtime >= since:
                out.append(p)
    return out


def generate_one(cfg: CodexConfig, prompt: str, size: str, image: str | None = None) -> Path:
    """跑一轮 codex exec，返回生成的图片（位于 Codex 数据目录，调用方负责复制走）。"""
    since = time.time() - 1
    text = build_prompt(prompt, size, edit=bool(image))
    image_arg = str(Path(image).expanduser().resolve()) if image else ""
    if _is_batch(cfg.bin):
        # 经 cmd.exe 解析：引号、%、& 等会被当成命令语法，拼出额外命令 —— 提示词里换成全角
        text = text.translate(_CMD_META_FULLWIDTH)
        if any(c in image_arg for c in _CMD_META):
            raise CodexImageError(
                f"图片路径含有 {_CMD_META} 中的字符，Windows 上无法安全传给 codex，请先改名再试。")
    with tempfile.TemporaryDirectory(prefix="easel-codex-img-", ignore_cleanup_errors=True) as work:
        cmd = [cfg.bin, "exec", "--ephemeral", "--skip-git-repo-check",
               "--sandbox", "read-only", "--json", "-m", cfg.model, "-C", work]
        if image_arg:
            # 必须用 --image=<路径>：-i 会一口气吞掉后面的多个参数，把 prompt 也当成图片
            cmd.append(f"--image={image_arg}")
        cmd.append(text)
        try:
            proc = _run(cmd, cfg.timeout, work)
        except subprocess.TimeoutExpired:
            raise CodexImageError(
                f"Codex 生图超时（>{cfg.timeout}s）。可在 .env 调大 IMG_CODEX_TIMEOUT 后重试。") from None
        except OSError as exc:
            raise CodexImageError(f"无法启动 codex（{cfg.bin}）：{exc}。{INSTALL_HINT}") from None

    events = _events(proc.stdout)
    tid = _thread_id(events)
    images = _fresh_images(cfg.home / "generated_images" / tid, since) if tid else []
    if not images:
        images = _paths_in_messages(_messages(events), since)
    if images:
        return images[-1]

    reasons = _errors(events)
    msgs = _messages(events)
    if msgs:
        reasons.append(f"Codex 回复：{msgs[-1][:200]}")
    tail = (proc.stderr or "").strip().splitlines()[-3:]
    if proc.returncode != 0 and tail:
        reasons.append("stderr：" + " / ".join(t.strip() for t in tail)[:300])
    detail = "；".join(reasons) or f"codex 退出码 {proc.returncode}，没有产出图片"
    raise CodexImageError(
        f"Codex 没有生成图片（模型 {cfg.model}）：{detail}。"
        "确认已 codex login、账号有生图额度，或在 .env 换 IMG_CODEX_MODEL。")


def generate(cfg: CodexConfig, prompt: str, n: int, size: str,
             image: str | None = None, log=None) -> list[Path]:
    """逐张生成 n 张（codex 每轮只可靠地出一张）。"""
    out = []
    for i in range(max(1, n)):
        if log:
            log(f"[codex] 第 {i + 1}/{max(1, n)} 张（模型 {cfg.model}，约 1 分钟）…")
        out.append(generate_one(cfg, prompt, size, image))
    return out
