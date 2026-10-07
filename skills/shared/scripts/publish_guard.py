#!/usr/bin/env python3
"""publish_guard.py — 发布前闸门：重复发布拦截 + 平台冷却（fail-stop）。

背景：同一条视频被重复发 3 次、发布失败后 agent 又连续重试 ~10 次，结果账号被平台封了投稿功能。
本模块把这两类事故变成确定性的硬拦截（纯 stdlib，可 `import publish_guard`，也可当 CLI 用）：

  1. 重复发布拦截：同一平台、同一媒体内容（sha256）或同一标题（归一化后）在窗口期内已发过 → exit 8。
     平台隔离：同一条视频发到不同平台是正常跨发，不拦。
     数据源：本模块的账本 outputs/_publish/ledger.jsonl + 既有发布日志 outputs/_analytics/publish-log.json。
  2. 平台冷却：检测到平台处罚/限流提示（或用户手动设置）后，该平台进入冷却，期间一律拒绝发布 → exit 9。
     冷却默认「直到用户手动解除」；只有用户在对话里明确要求才可 `cooldown clear`。

注意：这里**不做**发布频率限制，也不做任何后台抓取；只在发布入口做「重复」与「冷却」两道闸。

库用法（发布脚本在真发前调用）::

    import publish_guard
    publish_guard.guard_before_publish("douyin", [video_path], title, allow_repost=args.allow_repost)
    ...  # 发布
    publish_guard.record_publish("douyin", [video_path], title, url=url, project=project)
    # 检测到 toast 处罚文本时：
    if publish_guard.classify_block_text(toast_text):
        publish_guard.on_block_detected("douyin", toast_text)
        sys.exit(publish_guard.EXIT_COOLDOWN)

CLI::

    python skills/shared/scripts/publish_guard.py status [--platform X]
    python skills/shared/scripts/publish_guard.py check --platform X --title T [--media F ...] [--allow-repost]
    python skills/shared/scripts/publish_guard.py cooldown set --platform X --reason "…"
    python skills/shared/scripts/publish_guard.py cooldown clear --platform X

退出码：8 = 重复拦截（EXIT_DUPLICATE），9 = 平台冷却（EXIT_COOLDOWN）。
（与既有退出码不冲突：content_guard 7；overseas 2/3/5/6；xhs 6。）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import output_paths  # noqa: E402

EXIT_DUPLICATE = 8
EXIT_COOLDOWN = 9
DEFAULT_WINDOW_DAYS = 30

# 测试 / 特殊场景可覆盖；None = 用 outputs/_publish/ 与 outputs/_analytics/ 下的默认位置。
LEDGER_PATH: Path | None = None
COOLDOWN_PATH: Path | None = None
PUBLISH_LOG_PATH: Path | None = None


# --------------------------------------------------------------------------- #
# 平台名映射（平台码 ↔ publish-log 里的中文展示名）
# --------------------------------------------------------------------------- #
try:  # 复用 calendar_ops 的映射（与 web/app.py LOGIN_RUNNERS 的 name 对齐），不自造一份
    from calendar_ops import PLATFORM_NAMES as _CAL_NAMES  # noqa: E402
except Exception:  # pragma: no cover - 兜底，保持模块可独立使用
    _CAL_NAMES = {
        "xiaohongshu": "小红书", "douyin": "抖音", "kuaishou": "快手",
        "weixin-channels": "微信视频号", "zhihu": "知乎", "bilibili": "B站",
        "tiktok": "TikTok", "youtube": "YouTube", "instagram": "Instagram", "x": "X", "threads": "Threads",
    }

# 平台码 → 全部已知的展示名/别名（publish-log 是人/LLM 写的，名字不统一：视频号 / 微信视频号 …）
PLATFORM_ALIASES: dict[str, set[str]] = {pid: {name} for pid, name in _CAL_NAMES.items()}
for _pid, _extra in {
    "xiaohongshu": {"xhs", "小红书", "红书"},
    "douyin": {"抖音"},
    "kuaishou": {"快手"},
    "weixin-channels": {"视频号", "微信视频号", "channels", "wechat-channels"},
    "zhihu": {"知乎"},
    "bilibili": {"b站", "哔哩哔哩", "bili", "bilibili"},
    "tiktok": {"tiktok"},
    "youtube": {"youtube", "油管"},
    "instagram": {"instagram", "ins"},
    "x": {"x", "twitter", "推特", "x/twitter"},
    "threads": {"threads"},
    "wechat-mp": {"公众号", "微信公众号", "wechat-mp", "wechat_mp", "wechat"},
}.items():
    PLATFORM_ALIASES.setdefault(_pid, set()).update(_extra)

_ALIAS_TO_ID = {a.casefold(): pid for pid, names in PLATFORM_ALIASES.items() for a in names}
_ALIAS_TO_ID.update({pid: pid for pid in PLATFORM_ALIASES})


def canonical_platform(name: str) -> str:
    """平台码 / 中文展示名 / 别名 → 平台码；未知名字返回小写去空白后的原串（仍可做平台隔离）。"""
    key = (name or "").strip().casefold()
    return _ALIAS_TO_ID.get(key, key)


def platform_display(platform: str) -> str:
    return _CAL_NAMES.get(canonical_platform(platform), platform)


# --------------------------------------------------------------------------- #
# 路径 + 原子读写
# --------------------------------------------------------------------------- #
def _system_path(rel: str) -> Path:
    return output_paths.validate_output_path(rel, allow_system=True)


def ledger_path() -> Path:
    return Path(LEDGER_PATH) if LEDGER_PATH else _system_path("outputs/_publish/ledger.jsonl")


def cooldown_path() -> Path:
    return Path(COOLDOWN_PATH) if COOLDOWN_PATH else _system_path("outputs/_publish/cooldown.json")


def publish_log_path() -> Path:
    return Path(PUBLISH_LOG_PATH) if PUBLISH_LOG_PATH else _system_path("outputs/_analytics/publish-log.json")


def _atomic_write_text(path: Path, text: str) -> None:
    """tmp + os.replace 原子写，UTF-8。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _now() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def _parse_dt(value) -> datetime | None:
    """宽松解析 ISO / 常见日期串 / epoch 秒；无时区的按本地时间。失败返回 None。"""
    if value is None or value == "":
        return None
    dt: datetime | None = None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return None
    else:
        s = str(value).strip()
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
    if dt is None:
        return None
    return dt.astimezone() if dt.tzinfo is None else dt


# --------------------------------------------------------------------------- #
# 指纹 / 标题归一化
# --------------------------------------------------------------------------- #
def media_fingerprint(paths) -> str:
    """媒体内容指纹：对给定文件（按传入顺序）流式计算 sha256；空列表返回 ""。
    文件不存在 / 读不了时抛 OSError（调用方应已校验过路径）。"""
    paths = [p for p in (paths or []) if p]
    if not paths:
        return ""
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        h.update(b"\x00")  # 文件边界，避免拼接歧义
    return h.hexdigest()


_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}
_EP_RE = re.compile(r"第([零〇一二三四五六七八九十百两]+)([期集话篇弹])")


def _cn_to_int(s: str) -> int | None:
    """中文数字（到 999）→ int；不认识返回 None。支持「十二」「一百零三」，也支持逐位写法「一零」。"""
    if not s:
        return None
    if all(c in _CN_DIGITS for c in s):
        return int("".join(str(_CN_DIGITS[c]) for c in s))
    total, cur = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            cur = _CN_DIGITS[ch]
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        elif ch == "百":
            total += (cur or 1) * 100
            cur = 0
        else:
            return None
    return total + cur


def normalize_title(title: str) -> str:
    """标题归一化：NFKC → 第X期/集/话/篇/弹里的中文数字转阿拉伯数字 → 去掉空白/标点/符号 → 小写。
    「跟着动画学JLPT N2 ｜ 第二期」与「跟着动画学JLPT N2｜第2期」归一化后相同。"""
    s = unicodedata.normalize("NFKC", title or "")

    def _ep(m: re.Match) -> str:
        n = _cn_to_int(m.group(1))
        return f"第{n}{m.group(2)}" if n is not None else m.group(0)

    s = _EP_RE.sub(_ep, s)
    out = [ch for ch in s if unicodedata.category(ch)[0] not in ("Z", "P", "S", "C")]
    return "".join(out).casefold()


# --------------------------------------------------------------------------- #
# 账本 + 重复检测
# --------------------------------------------------------------------------- #
def _read_ledger() -> list[dict]:
    p = ledger_path()
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue  # 坏行忽略，不让账本损坏卡死发布
        if isinstance(d, dict):
            rows.append(d)
    return rows


def record_publish(platform: str, media_paths, title: str, url: str = "", project: str = "") -> dict:
    """发布成功后记一笔账（追加到 ledger.jsonl，原子重写）。返回写入的记录。"""
    try:
        fp = media_fingerprint(media_paths)
    except OSError:
        fp = ""  # 媒体文件此刻读不了不应让「已发布」的记账失败
    entry = {
        "platform": canonical_platform(platform),
        "title": title or "",
        "norm_title": normalize_title(title or ""),
        "fingerprint": fp,
        "files": [str(p) for p in (media_paths or [])],
        "url": url or "",
        "project": project or "",
        "published_at": _now().isoformat(),
    }
    rows = _read_ledger()
    rows.append(entry)
    _atomic_write_text(ledger_path(), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return entry


def _read_publish_log() -> list[dict]:
    p = publish_log_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    return [e for e in (entries or []) if isinstance(e, dict)]


def find_duplicate(platform: str, media_paths, title: str, window_days: int = DEFAULT_WINDOW_DAYS) -> dict | None:
    """同一平台、窗口期内是否已发过相同内容：媒体指纹相同，或归一化标题相同。

    平台隔离（跨平台发同一条视频不算重复）。数据源 = 账本 + publish-log。
    命中返回 {"source": "ledger"|"publish-log", "reason": "media"|"title", "platform", "title",
    "published_at", "url"}，否则 None。同时命中时媒体指纹优先、更近的优先。"""
    pid = canonical_platform(platform)
    fp = media_fingerprint(media_paths) if media_paths else ""
    ntitle = normalize_title(title or "")
    cutoff = _now() - timedelta(days=window_days)
    hits: list[tuple[int, datetime, dict]] = []

    def consider(source: str, row: dict, row_fp: str, row_ntitle: str) -> None:
        if canonical_platform(str(row.get("platform", ""))) != pid:
            return
        ts = _parse_dt(row.get("published_at") or row.get("logged_at"))
        if ts is None or ts < cutoff:
            return
        if fp and row_fp and fp == row_fp:
            reason, rank = "media", 0
        elif ntitle and row_ntitle and ntitle == row_ntitle:
            reason, rank = "title", 1
        else:
            return
        hits.append((rank, ts, {
            "source": source, "reason": reason, "platform": pid,
            "title": row.get("title", ""), "published_at": row.get("published_at") or row.get("logged_at", ""),
            "url": row.get("url", ""),
        }))

    for r in _read_ledger():
        consider("ledger", r, r.get("fingerprint", ""), r.get("norm_title") or normalize_title(r.get("title", "")))
    for e in _read_publish_log():
        consider("publish-log", e, "", normalize_title(e.get("title", "")))
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0], -h[1].timestamp()))
    return hits[0][2]


# --------------------------------------------------------------------------- #
# 冷却
# --------------------------------------------------------------------------- #
def _read_cooldowns() -> dict:
    p = cooldown_path()
    if not p.is_file():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def set_cooldown(platform: str, reason: str, evidence: str = "", until=None) -> dict:
    """让某平台进入冷却。until=None：直到用户手动解除；否则为 datetime / ISO 串 / epoch 秒（到点自动失效）。"""
    pid = canonical_platform(platform)
    until_dt = _parse_dt(until) if until is not None else None
    if until is not None and until_dt is None:
        raise ValueError(f"无法解析 until：{until!r}")
    rec = {
        "platform": pid, "reason": reason, "evidence": evidence,
        "since": _now().isoformat(),
        "until": until_dt.isoformat() if until_dt else None,
    }
    data = _read_cooldowns()
    data[pid] = rec
    _atomic_write_text(cooldown_path(), json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return rec


def active_cooldown(platform: str) -> dict | None:
    """该平台当前生效的冷却记录；没有、或带 until 且已过期则 None（过期记录不自动删除，只视为无效）。"""
    rec = _read_cooldowns().get(canonical_platform(platform))
    if not isinstance(rec, dict):
        return None
    until = _parse_dt(rec.get("until")) if rec.get("until") else None
    if until is not None and until <= _now():
        return None
    return rec


def clear_cooldown(platform: str) -> bool:
    """解除冷却。只应在用户于对话中明确要求时调用。返回是否真的删了一条记录。"""
    pid = canonical_platform(platform)
    data = _read_cooldowns()
    if pid not in data:
        return False
    del data[pid]
    _atomic_write_text(cooldown_path(), json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return True


# --------------------------------------------------------------------------- #
# 处罚/限流提示识别（只应用于 toast / 通知元素的文本，不要喂整页文本）
# --------------------------------------------------------------------------- #
_ACT = r"(?:投稿|发布|发文|发帖|发视频|上传)"
_BAN = r"(?:封禁|封停|限制|冻结|禁用|关闭|暂停|禁止)"
_BLOCK_PATTERNS = [
    # 「视频投稿功能已封禁」「发布功能被限制」「投稿权限已被冻结」
    re.compile(rf"{_ACT}(?:功能|权限)[^。，,；;\n]{{0,6}}?(?:已|被|暂时|暂)*被?{_BAN}"),
    # 「你的投稿已被限制」「发文被冻结」：动作词后 8 字内出现「已被/被 + 处罚」
    re.compile(rf"{_ACT}[^。，,；;\n]{{0,8}}?(?:已被|被){_BAN}"),
    # 操作过于频繁 / 请求太频繁
    re.compile(r"(?:操作|请求|访问|发布|提交)(?:过于|太|过)频繁"),
    # 账号异常 / 存在风险
    re.compile(r"(?:账号|账户|帐号)(?:存在)?(?:异常|风险)"),
    re.compile(r"(?:账号|账户|帐号)存在[^。，,；;\n]{0,4}风险"),
    # 已被封禁 / 禁言 / 封号
    re.compile(r"(?:已被|被)(?:封禁|封号|封停|禁言)"),
    re.compile(r"(?:账号|账户|帐号)(?:已)?被?(?:封禁|封号|封停|禁言|冻结)"),
]


def classify_block_text(text: str) -> str | None:
    """判断一段 toast/通知文本是不是平台的处罚/限流提示。是则返回命中的原文片段，否则 None。

    保守：只匹配「功能/账号 已被 封禁·限制·冻结」「操作过于频繁」「账号异常/存在风险」这类明确处罚句式；
    「请勿发布违规内容」「违规内容将被处理」之类的普通提示不会命中。
    **只能**用在 toast / 通知元素的文本上——整页文本里的规则说明可能误伤。"""
    s = unicodedata.normalize("NFKC", text or "")
    if not s.strip():
        return None
    for pat in _BLOCK_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(0)
    return None


# --------------------------------------------------------------------------- #
# 发布入口闸门
# --------------------------------------------------------------------------- #
def _eprint(*parts) -> None:
    print(*parts, file=sys.stderr)


def guard_before_publish(platform: str, media_paths, title: str, *, allow_repost: bool = False) -> None:
    """发布脚本在真发（--exec）前调用。先查冷却，再查重复；拦下则打印中文说明并 sys.exit。

    冷却 → EXIT_COOLDOWN(9)，任何参数都绕不过（只有用户能解除）。
    重复 → EXIT_DUPLICATE(8)；allow_repost=True 时放行（仅当用户在对话里明确要求重发同一内容）。"""
    name = platform_display(platform)
    cd = active_cooldown(platform)
    if cd:
        _eprint(f"⛔ {name} 当前处于冷却期，已停止发布。")
        _eprint(f"   原因：{cd.get('reason') or '（未记录）'}")
        if cd.get("evidence"):
            _eprint(f"   平台提示原文：{cd['evidence']}")
        _eprint(f"   起始：{cd.get('since', '')}；"
                + (f"到期：{cd['until']}" if cd.get("until") else "到期：无（需用户手动解除）"))
        _eprint("   不要重试、不要换方式绕过。请先把情况告知用户，只有用户在对话里明确要求才可解除冷却"
                "（publish_guard.py cooldown clear）。")
        sys.exit(EXIT_COOLDOWN)
    dup = find_duplicate(platform, media_paths, title)
    if dup:
        how = "媒体文件内容完全相同" if dup["reason"] == "media" else "标题相同（忽略标点/期号写法）"
        _eprint(f"⛔ 检测到重复发布：{name} 在 {dup['published_at']} 已发过{how}的内容。")
        _eprint(f"   上一条：「{dup['title']}」" + (f" {dup['url']}" if dup.get("url") else "")
                + f"（来源：{dup['source']}）")
        if allow_repost:
            _eprint("   已带 --allow-repost，按用户明确要求的重发处理，继续。")
            return
        _eprint("   默认不重复发布。仅当用户在对话中明确要求「再发一次同样的内容」时，才可加 --allow-repost；"
                "否则请告知用户并停止。")
        sys.exit(EXIT_DUPLICATE)


def on_block_detected(platform: str, text: str) -> dict:
    """在 toast/通知里识别到处罚/限流文本后调用：把该平台设为冷却（手动解除），打印中文错误并返回记录。
    调用方随后应 sys.exit(EXIT_COOLDOWN)，且不得重试。"""
    hit = classify_block_text(text) or ""
    rec = set_cooldown(platform, reason=f"平台提示处罚/限制：{hit or (text or '').strip()[:60]}",
                       evidence=(text or "").strip()[:500])
    name = platform_display(platform)
    _eprint(f"⛔ {name} 返回了处罚/限制提示：{(text or '').strip()[:200]}")
    _eprint(f"   已自动把 {name} 设为冷却（需用户手动解除），后续发布一律拒绝。请不要重试，先向用户汇报并去平台消息中心查看详情。")
    return rec


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _cmd_status(a) -> int:
    pids = [canonical_platform(a.platform)] if a.platform else None
    cds = _read_cooldowns()
    shown = False
    for pid, rec in sorted(cds.items()):
        if pids and pid not in pids:
            continue
        live = active_cooldown(pid)
        state = "冷却中" if live else "已过期"
        until = rec.get("until") or "需手动解除"
        print(f"[{state}] {platform_display(pid)}（{pid}）起 {rec.get('since')} 到 {until}：{rec.get('reason')}")
        shown = True
    if not shown:
        print("无冷却记录" + (f"（{platform_display(pids[0])}）" if pids else ""))
    counts: dict[str, int] = {}
    for r in _read_ledger():
        pid = canonical_platform(str(r.get("platform", "")))
        if pids and pid not in pids:
            continue
        counts[pid] = counts.get(pid, 0) + 1
    print("账本记录：" + ("，".join(f"{platform_display(k)} {v} 条" for k, v in sorted(counts.items())) or "无"))
    return 0


def _cmd_check(a) -> int:
    # 复用 guard_before_publish 的判定，但转成退出码而不是直接 exit，便于 CLI 反馈
    try:
        guard_before_publish(a.platform, a.media or [], a.title, allow_repost=a.allow_repost)
    except SystemExit as e:
        return int(e.code or 0)
    print(f"✅ {platform_display(a.platform)}：无冷却、无重复，可以继续。")
    return 0


def _cmd_cooldown(a) -> int:
    if a.action == "set":
        until = None
        if a.hours:
            until = _now() + timedelta(hours=a.hours)
        rec = set_cooldown(a.platform, a.reason, a.evidence or "", until=until)
        print(f"已设置冷却：{platform_display(a.platform)}，到期：{rec['until'] or '需手动解除'}")
        return 0
    if clear_cooldown(a.platform):
        print(f"已解除 {platform_display(a.platform)} 的冷却。")
    else:
        print(f"{platform_display(a.platform)} 本来就没有冷却记录。")
    print("提醒：解除冷却只应在用户于对话中明确要求时执行；平台处罚未必已解除，再发前请先向用户确认。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="发布前闸门：重复拦截 + 平台冷却")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="查看冷却与账本概况")
    st.add_argument("--platform")
    ck = sub.add_parser("check", help="发布前预检：冷却/重复（8=重复，9=冷却，0=可发）")
    ck.add_argument("--platform", required=True)
    ck.add_argument("--title", required=True)
    ck.add_argument("--media", nargs="*", default=[])
    ck.add_argument("--allow-repost", action="store_true", help="仅在用户明确要求重发同一内容时使用")
    cd = sub.add_parser("cooldown", help="手动设置/解除平台冷却")
    cds = cd.add_subparsers(dest="action", required=True)
    cs = cds.add_parser("set")
    cs.add_argument("--platform", required=True)
    cs.add_argument("--reason", required=True)
    cs.add_argument("--evidence", default="")
    cs.add_argument("--hours", type=float, default=0, help="冷却小时数；不填=直到手动解除")
    cc = cds.add_parser("clear")
    cc.add_argument("--platform", required=True)
    a = ap.parse_args(argv)
    return {"status": _cmd_status, "check": _cmd_check, "cooldown": _cmd_cooldown}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
