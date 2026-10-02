"""网页「定时任务」页与 OpenClaw 定时任务（cron）之间的薄封装。

走 gateway 的 WebSocket RPC（复用 gateway_questions.GatewayClient），比每次起 `openclaw cron` CLI
（实测约 9 秒）快得多。

边界：
- 网页只能新建「到点让 agent 做一件事」（agentTurn）这一种任务。命令 / 脚本 / 流式 / on-exit 那几种
  是在 gateway 上直接跑 shell，网页没有登录鉴权，不能开这个口子。
- OpenClaw 和插件自己声明的任务（心跳、记忆整理……都带 declarationKey）只读：不能暂停、删除、改。
- 间隔不能短于 MIN_INTERVAL_MIN 分钟，cron 表达式的「分钟」位必须写死数字（不许 * 或 */n）。

纯函数（build_schedule / normalize_job / normalize_run）不碰网络，便于单测；RPC 调用都在 call() 里。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from easel.timeouts import TIMEOUT_CHAT

MIN_INTERVAL_MIN = 10
MAX_AHEAD = timedelta(days=365 * 10)     # gateway 拒绝 10 年以后的一次性任务
MAX_INTERVAL_MIN = 7 * 24 * 60
NAME_MAX = 60
MESSAGE_MAX = 4000
CREATED_BY = "由 Easel 网页创建"

_CRON_FIELD = re.compile(r"^[0-9*,/\-]+$")
_MINUTE_FIELD = re.compile(r"^[0-9]{1,2}(,[0-9]{1,2})*$")


class CronInputError(ValueError):
    """用户填的东西不合规（给 400）。"""


def _expand_hours(field: str) -> list[int] | None:
    """展开「小时」位：数字、*、*/n、a-b、a-b/n 及其逗号列表 → 小时集合；看不懂返回 None。"""
    hours: set[int] = set()
    for part in field.split(","):
        m = re.fullmatch(r"(\*|\d{1,2}(?:-\d{1,2})?)(?:/(\d{1,2}))?", part)
        if not m:
            return None
        rng, step = m.group(1), int(m.group(2) or 1)
        if step < 1:
            return None
        if rng == "*":
            lo, hi = 0, 23
        elif "-" in rng:
            lo, hi = (int(x) for x in rng.split("-"))
        else:
            lo = hi = int(rng)
            if m.group(2):          # 「9/2」这种写法 croner 不认
                return None
        if not 0 <= lo <= hi <= 23:
            return None
        hours.update(range(lo, hi + 1, step))
    return sorted(hours)


def _min_gap_minutes(minutes: list[int], hours: list[int]) -> int | None:
    """一天里按这些小时 × 分钟运行，相邻两次的最短间隔（含跨午夜）；只跑一次返回 None。"""
    times = sorted(h * 60 + m for h in hours for m in minutes)
    if len(times) < 2:
        return None
    gaps = [b - a for a, b in zip(times, times[1:])] + [times[0] + 1440 - times[-1]]
    return min(gaps)


def build_schedule(spec: dict, now: datetime | None = None) -> dict:
    """网页表单的时间设置 → OpenClaw 的 schedule。

    spec：
      {"mode": "cron", "expr": "0 9 * * *"}          每天 / 每周 / 自定义都转成 cron 表达式
      {"mode": "every", "minutes": 120}              每隔 N 分钟
      {"mode": "at", "at": "2026-10-03T09:00"}       只运行一次（没带时区按本机时区）
    """
    if not isinstance(spec, dict):
        raise CronInputError("时间设置格式不对")
    mode = spec.get("mode")
    if mode == "cron":
        expr = " ".join(str(spec.get("expr") or "").split())
        fields = expr.split(" ")
        if len(fields) != 5 or not all(_CRON_FIELD.match(f) for f in fields):
            raise CronInputError("cron 表达式要 5 段（分 时 日 月 周），只能用数字和 * , / -")
        if not _MINUTE_FIELD.match(fields[0]):
            raise CronInputError(f"「分钟」那一段要写具体数字（如 0 或 0,30），不能用 * 或 */n："
                                 f"两次运行间隔不能短于 {MIN_INTERVAL_MIN} 分钟")
        minutes = sorted({int(m) for m in fields[0].split(",")})
        if minutes[-1] > 59:
            raise CronInputError("「分钟」只能是 0–59")
        hours = _expand_hours(fields[1])
        if hours is None:
            raise CronInputError("「小时」那一段写法不对（0–23，可用 * , - /）")
        gap = _min_gap_minutes(minutes, hours)
        if gap is not None and gap < MIN_INTERVAL_MIN:
            raise CronInputError(f"两次运行间隔不能短于 {MIN_INTERVAL_MIN} 分钟")
        return {"kind": "cron", "expr": expr}
    if mode == "every":
        raw = spec.get("minutes")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw != raw or raw in (float("inf"), float("-inf")):
            raise CronInputError("间隔要填分钟数")
        if raw != int(raw):
            raise CronInputError("间隔要填整数分钟")
        minutes = int(raw)
        if not MIN_INTERVAL_MIN <= minutes <= MAX_INTERVAL_MIN:
            raise CronInputError(f"间隔要在 {MIN_INTERVAL_MIN} 分钟到 7 天之间")
        return {"kind": "every", "everyMs": minutes * 60_000}
    if mode == "at":
        raw = str(spec.get("at") or "").strip()
        try:
            when = datetime.fromisoformat(raw)
        except ValueError:
            raise CronInputError("运行时间格式不对") from None
        when = when.astimezone() if when.tzinfo is None else when
        now = now or datetime.now().astimezone()
        if when <= now:
            raise CronInputError("运行时间要在将来")
        if when - now > MAX_AHEAD:
            raise CronInputError("运行时间不能超过 10 年以后")
        return {"kind": "at", "at": when.isoformat(timespec="seconds")}
    raise CronInputError("不认识的时间设置")


def build_add_params(name: str, message: str, schedule_spec: dict, now: datetime | None = None) -> dict:
    name = (name or "").strip()
    message = (message or "").strip()
    if not name or len(name) > NAME_MAX:
        raise CronInputError(f"名称不能为空，最多 {NAME_MAX} 个字")
    if not message or len(message) > MESSAGE_MAX:
        raise CronInputError(f"要 agent 做的事不能为空，最多 {MESSAGE_MAX} 个字")
    return {
        "name": name,
        "description": CREATED_BY,
        "enabled": True,
        "deleteAfterRun": False,          # 一次性任务 OpenClaw 默认跑完就删，删了运行记录就没处看了
        "schedule": build_schedule(schedule_spec, now),
        "sessionTarget": "isolated",      # 每次运行一个新会话，不混进对话页的会话
        "wakeMode": "now",
        "payload": {"kind": "agentTurn", "message": message, "timeoutSeconds": TIMEOUT_CHAT},
        "delivery": {"mode": "none"},     # 结果看运行记录，不往聊天渠道推
    }


def is_system(job: dict) -> bool:
    """OpenClaw / 插件声明的任务（带 declarationKey）或心跳。"""
    payload = job.get("payload") or {}
    return bool(job.get("declarationKey")) or payload.get("kind") == "heartbeat"


def is_readonly(job: dict) -> bool:
    """网页只能管「让 agent 做事」（agentTurn）的非系统任务。命令 / 脚本 / 系统事件类任务（多半是命令行建的）
    一律只读：在网页上点「立即运行」就等于从没有鉴权的网页在 gateway 上跑 shell。"""
    return is_system(job) or (job.get("payload") or {}).get("kind") != "agentTurn"


def normalize_job(job: dict) -> dict:
    state = job.get("state") or {}
    payload = job.get("payload") or {}
    return {
        "id": job.get("id"),
        "name": job.get("displayName") or job.get("name") or "",
        "description": job.get("description") or "",
        "enabled": bool(job.get("enabled")),
        "system": is_system(job),
        "readonly": is_readonly(job),
        "kind": payload.get("kind") or "",
        "message": payload.get("message") or payload.get("text") or "",
        "schedule": job.get("schedule") or {},
        "nextRunAtMs": job.get("nextRunAtMs") or state.get("nextRunAtMs"),
        "lastRunAtMs": job.get("lastRunAtMs") or state.get("lastRunAtMs"),
        "lastRunStatus": job.get("lastRunStatus") or state.get("lastRunStatus") or "",
        "lastError": job.get("lastRunError") or state.get("lastError") or "",
        "lastDurationMs": state.get("lastDurationMs"),
        "runningAtMs": state.get("runningAtMs"),
        "createdAtMs": job.get("createdAtMs"),
    }


def normalize_run(entry: dict) -> dict:
    return {
        "runAtMs": entry.get("runAtMs") or entry.get("ts"),
        "status": entry.get("status") or "",
        "durationMs": entry.get("durationMs"),
        "summary": entry.get("summary") or "",
        "error": entry.get("error") or "",
        "model": entry.get("model") or "",
    }


# --------------------------------------------------------------------------- #
# RPC
# --------------------------------------------------------------------------- #
class CronGatewayError(RuntimeError):
    """连不上 gateway / 连接中出错（给 502）。"""


class CronRejectedError(CronInputError):
    """gateway 收到了请求但拒绝了（参数不合规、任务不存在……，给 400）。message 是 gateway 的原话。"""


_UNAVAILABLE_CODES = {"UNAVAILABLE", "TIMEOUT", "SHUTTING_DOWN"}
_CODE_RE = re.compile(r'"code":\s*"([^"]+)"')
_MSG_RE = re.compile(r'"message":\s*"((?:[^"\\]|\\.)*)("?)')


def _rejection(err: Exception) -> str | None:
    """GatewayClient 把 gateway 的错误包成 `<method> failed/not supported: {json}`，而且 JSON 只留前 200 个字符
    （可能被截断，不能 json.loads）。用正则取 code / message；取不到返回 None。"""
    text = str(err)
    code = _CODE_RE.search(text)
    if not code:
        return None
    msg = _MSG_RE.search(text)
    if not msg:
        return code.group(1)
    body = msg.group(1)
    try:
        body = json.loads(f'"{body}"')      # 还原 \uXXXX / \n 等转义（中文任务名会被转义）
    except ValueError:
        body = body.replace('\\"', '"')
    return body if msg.group(2) else body + "…"


def call(method: str, params: dict, timeout: float = 15.0):
    """同步调一次 gateway RPC（调用方放进线程里跑）。
    gateway 回了错误 → CronRejectedError；连不上 / 超时 / 缺依赖 → CronGatewayError。"""
    try:
        from easel.gateway_questions import GatewayClient, GatewayQuestionError
    except Exception as e:  # noqa: BLE001  缺 websocket-client 等依赖
        raise CronGatewayError(f"缺少 gateway 连接依赖：{e}") from e
    client = GatewayClient(timeout=timeout)
    try:
        return client._rpc(method, params)
    except GatewayQuestionError as e:
        # 「<method> failed / not supported: {...}」是这次请求被拒；「gateway connect failed」是没连上
        reason = _rejection(e) if str(e).startswith(f"{method} ") else None
        code = _CODE_RE.search(str(e))
        if reason is not None and not (code and code.group(1) in _UNAVAILABLE_CODES):
            raise CronRejectedError(f"OpenClaw 拒绝了：{reason}") from e
        raise CronGatewayError(str(e)) from e
    except Exception as e:  # noqa: BLE001  连接被拒、超时……
        raise CronGatewayError(str(e)) from e
    finally:
        client.close()


def list_jobs() -> list[dict]:
    payload = call("cron.list", {"includeDisabled": True, "limit": 200}) or {}
    jobs = [normalize_job(j) for j in payload.get("jobs") or []]
    jobs.sort(key=lambda j: (j["readonly"], -(j["createdAtMs"] or 0)))
    return jobs


def get_job(job_id: str) -> dict | None:
    return next((j for j in list_jobs() if j["id"] == job_id), None)


def add_job(params: dict) -> dict:
    res = call("cron.add", params) or {}
    job = res.get("job") if isinstance(res.get("job"), dict) else res
    return normalize_job(job)


def set_enabled(job_id: str, enabled: bool) -> None:
    call("cron.update", {"id": job_id, "patch": {"enabled": enabled}})


def remove_job(job_id: str) -> None:
    call("cron.remove", {"id": job_id})


def run_now(job_id: str) -> dict:
    """立即运行。gateway 没真跑（如任务正在运行）时回 {ran: false, reason}，原样交给调用方。"""
    return call("cron.run", {"id": job_id, "mode": "force"}) or {}


def list_runs(job_id: str, limit: int = 20) -> list[dict]:
    payload = call("cron.runs", {"id": job_id, "limit": max(1, min(limit, 100)), "sortDir": "desc"}) or {}
    return [normalize_run(e) for e in payload.get("entries") or []]
