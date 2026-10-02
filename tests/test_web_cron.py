"""网页「定时任务」页：easel/gateway_cron 的规则 + /api/cron 接口。不连真 gateway（call 换成内存假实现）。"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import app as web  # noqa: E402
from easel import gateway_cron as gc  # noqa: E402

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=9)))


# ── 时间设置 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("expr", ["0 9 * * *", "30 8 * * 1", "0 9,21 * * *", "0,30 9 * * *",
                                  "0 */2 * * *", "15 10 1 * *", "  0   9 * * 1-5 ", "0,55 9,17 * * *",
                                  "0,30 * * * *", "0 9-12 * * *", "0 8-20/4 * * *", "0 9 * * 7"])
def test_cron_expr_accepted(expr):
    assert gc.build_schedule({"mode": "cron", "expr": expr}) == {"kind": "cron", "expr": " ".join(expr.split())}


@pytest.mark.parametrize("expr", ["* * * * *", "*/5 * * * *", "0,5 9 * * *", "0,55 * * * *",
                                  "0,55 9,10 * * *", "0 9 * *", "0 9 * * * *", "61 9 * * *", "0 9 * * MON",
                                  "0 9 * * *; rm", "0 24 * * *", "0 9/2 * * *", "0 */0 * * *"])
def test_cron_expr_rejected(expr):
    with pytest.raises(gc.CronInputError):
        gc.build_schedule({"mode": "cron", "expr": expr})


def test_every_bounds():
    assert gc.build_schedule({"mode": "every", "minutes": 10}) == {"kind": "every", "everyMs": 600_000}
    for bad in (9, 0, -5, 7 * 24 * 60 + 1, "abc", None, True, 12.7, float("inf"), float("nan")):
        with pytest.raises(gc.CronInputError):
            gc.build_schedule({"mode": "every", "minutes": bad})


def test_at_must_be_future_and_gets_timezone():
    s = gc.build_schedule({"mode": "at", "at": "2026-10-03T09:00+09:00"}, now=NOW)
    assert s == {"kind": "at", "at": "2026-10-03T09:00:00+09:00"}
    naive = gc.build_schedule({"mode": "at", "at": "2027-01-01T09:00"}, now=NOW)
    assert naive["at"].startswith("2027-01-01T09:00:00") and len(naive["at"]) > 19   # 补上了本机时区
    for bad in ("2026-10-02T11:00+09:00", "明天", ""):
        with pytest.raises(gc.CronInputError):
            gc.build_schedule({"mode": "at", "at": bad}, now=NOW)


@pytest.mark.parametrize("spec", [None, "0 9 * * *", {"mode": "command", "command": "rm -rf /"},
                                  {"mode": "stream"}, {}])
def test_unknown_schedule_modes_rejected(spec):
    with pytest.raises(gc.CronInputError):
        gc.build_schedule(spec)


def test_add_params_only_agent_turn():
    p = gc.build_add_params(" 每日热点 ", " 收集今天的 AI 热点 ", {"mode": "cron", "expr": "0 9 * * *"})
    assert p["name"] == "每日热点" and p["payload"]["kind"] == "agentTurn"
    assert p["payload"]["message"] == "收集今天的 AI 热点"
    assert p["sessionTarget"] == "isolated" and p["delivery"] == {"mode": "none"}
    assert "declarationKey" not in p           # 带了就成了「声明式」任务，网页反而管不了
    for name, msg in (("", "x"), ("x" * 61, "x"), ("ok", ""), ("ok", "x" * 4001)):
        with pytest.raises(gc.CronInputError):
            gc.build_add_params(name, msg, {"mode": "every", "minutes": 60})


def test_system_jobs_detected():
    assert gc.is_system({"declarationKey": "memory-core:x", "payload": {"kind": "agentTurn"}})
    assert gc.is_system({"payload": {"kind": "heartbeat"}})
    assert not gc.is_system({"payload": {"kind": "agentTurn", "message": "hi"}})


# ── 接口（假 gateway）─────────────────────────────────────────────────


class FakeGateway:
    def __init__(self):
        self.jobs = {
            "sys": {"id": "sys", "name": "Heartbeat", "enabled": True, "createdAtMs": 1,
                    "declarationKey": "heartbeat:main", "schedule": {"kind": "every", "everyMs": 1800000},
                    "payload": {"kind": "heartbeat"}, "state": {}},
        }
        self.calls: list[tuple[str, dict]] = []
        self.down = False

    def __call__(self, method, params, timeout=15.0):
        self.calls.append((method, params))
        if self.down:
            raise gc.CronGatewayError("connection refused")
        if method == "cron.list":
            return {"jobs": list(self.jobs.values())}
        if method == "cron.add":
            jid = f"j{len(self.jobs)}"
            job = {**params, "id": jid, "createdAtMs": 100 + len(self.jobs),
                   "state": {"nextRunAtMs": 999}}
            self.jobs[jid] = job
            return job
        if method == "cron.update":
            self.jobs[params["id"]].update(params["patch"])
            return {}
        if method == "cron.remove":
            self.jobs.pop(params["id"])
            return {}
        if method == "cron.run":
            return {"ok": True}
        if method == "cron.runs":
            return {"entries": [{"ts": 5, "runAtMs": 4, "status": "ok", "summary": "整理好了 3 个选题",
                                 "durationMs": 1200, "model": "claude"}]}
        raise AssertionError(method)


@pytest.fixture
def gw(monkeypatch):
    fake = FakeGateway()
    monkeypatch.setattr(gc, "call", fake)
    return fake


def run(coro):
    return asyncio.run(coro)


def test_create_list_pause_resume_run_delete(gw):
    res = run(web.api_cron_create(web.CronCreateRequest(
        name="每日热点", message="收集今天的 AI 热点，整理成 3 个选题", schedule={"mode": "cron", "expr": "0 9 * * *"})))
    jid = res["job"]["id"]
    assert res["warning"] == "" and res["job"]["nextRunAtMs"] == 999
    jobs = run(web.api_cron_list())["jobs"]
    assert [j["id"] for j in jobs] == [jid, "sys"]          # 自己的在前，系统任务在后
    assert jobs[1]["system"] is True and jobs[0]["system"] is False
    run(web.api_cron_pause(jid))
    assert gw.jobs[jid]["enabled"] is False
    run(web.api_cron_resume(jid))
    assert gw.jobs[jid]["enabled"] is True
    run(web.api_cron_run(jid))
    assert ("cron.run", {"id": jid, "mode": "force"}) in gw.calls
    runs = run(web.api_cron_runs(jid))["runs"]
    assert runs == [{"runAtMs": 4, "status": "ok", "durationMs": 1200, "summary": "整理好了 3 个选题",
                     "error": "", "model": "claude"}]
    run(web.api_cron_delete(jid))
    assert jid not in gw.jobs


def test_system_job_is_read_only(gw):
    for fn in (web.api_cron_pause, web.api_cron_resume, web.api_cron_run, web.api_cron_delete):
        with pytest.raises(HTTPException) as e:
            run(fn("sys"))
        assert e.value.status_code == 403
    assert "sys" in gw.jobs and gw.jobs["sys"]["enabled"] is True


def test_missing_job_404(gw):
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_pause("nope"))
    assert e.value.status_code == 404


def test_bad_input_400_without_calling_gateway(gw):
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_create(web.CronCreateRequest(
            name="刷屏", message="x", schedule={"mode": "cron", "expr": "* * * * *"})))
    assert e.value.status_code == 400
    assert gw.calls == []


def test_publish_words_warn(gw):
    res = run(web.api_cron_create(web.CronCreateRequest(
        name="自动发", message="每天把草稿发布到小红书", schedule={"mode": "every", "minutes": 1440})))
    assert "发布" in res["warning"] and "小红书" in res["warning"]


def test_gateway_down_502(gw):
    gw.down = True
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_list())
    assert e.value.status_code == 502 and "easel gateway start" in e.value.detail


def test_at_more_than_ten_years_ahead_rejected():
    with pytest.raises(gc.CronInputError):
        gc.build_schedule({"mode": "at", "at": "2099-01-01T09:00+09:00"}, now=NOW)


class _FakeClient:
    """模拟 GatewayClient：_rpc 抛出 gateway_questions 风格的错误。"""
    error: Exception | None = None

    def __init__(self, timeout=15.0):
        pass

    def _rpc(self, method, params):
        raise self.error

    def close(self):
        pass


@pytest.mark.parametrize("err,expect", [
    ('cron.add not supported by this gateway: {"code": "INVALID_REQUEST", "message": "schedule.at is too far"}',
     gc.CronRejectedError),
    ('cron.update failed: {"code": "NOT_FOUND", "message": "job not found"}', gc.CronRejectedError),
    ('gateway connect failed: {"code": "NOT_PAIRED"}', gc.CronGatewayError),
    ("cron.list timed out", gc.CronGatewayError),
])
def test_call_separates_rejection_from_connection_failure(monkeypatch, err, expect):
    import easel.gateway_questions as gq
    _FakeClient.error = gq.GatewayQuestionError(err)
    monkeypatch.setattr(gq, "GatewayClient", _FakeClient)
    method = err.split(" ")[0] if err.startswith("cron.") else "cron.list"
    with pytest.raises(expect) as e:
        gc.call(method, {})
    if expect is gc.CronRejectedError:
        assert "OpenClaw 拒绝了" in str(e.value)


def test_connection_refused_is_gateway_error(monkeypatch):
    import easel.gateway_questions as gq
    _FakeClient.error = ConnectionRefusedError(61, "Connection refused")
    monkeypatch.setattr(gq, "GatewayClient", _FakeClient)
    with pytest.raises(gc.CronGatewayError):
        gc.call("cron.list", {})


def test_rejection_becomes_400(monkeypatch):
    def boom(*_a, **_k):
        raise gc.CronRejectedError("OpenClaw 拒绝了：bad")

    monkeypatch.setattr(gc, "call", boom)
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_list())
    assert e.value.status_code == 400 and "OpenClaw 拒绝了" in e.value.detail


def test_truncated_rejection_still_parsed(monkeypatch):
    import easel.gateway_questions as gq
    long = 'cron.update not supported by this gateway: {"code": "INVALID_REQUEST", "message": "Automation not found: no-such-job. List automations and retry with a current job id. For cross-session management, use a fresh authen'
    _FakeClient.error = gq.GatewayUnsupportedError(long)
    monkeypatch.setattr(gq, "GatewayClient", _FakeClient)
    with pytest.raises(gc.CronRejectedError) as e:
        gc.call("cron.update", {})
    assert "Automation not found: no-such-job" in str(e.value) and str(e.value).endswith("…")



def test_one_shot_jobs_kept_after_run():
    p = gc.build_add_params("一次", "做一次", {"mode": "at", "at": "2027-01-01T09:00+09:00"}, now=NOW)
    assert p["deleteAfterRun"] is False


def test_rejection_message_unescapes_unicode(monkeypatch):
    import easel.gateway_questions as gq
    _FakeClient.error = gq.GatewayQuestionError(
        'cron.add failed: {"code": "INVALID_REQUEST", "message": "\\u6bcf\\u65e5 is bad\\nline2"}')
    monkeypatch.setattr(gq, "GatewayClient", _FakeClient)
    with pytest.raises(gc.CronRejectedError) as e:
        gc.call("cron.add", {})
    assert "每日 is bad\nline2" in str(e.value)


def test_unavailable_code_is_gateway_error(monkeypatch):
    import easel.gateway_questions as gq
    _FakeClient.error = gq.GatewayQuestionError('cron.list failed: {"code": "UNAVAILABLE", "message": "starting"}')
    monkeypatch.setattr(gq, "GatewayClient", _FakeClient)
    with pytest.raises(gc.CronGatewayError):
        gc.call("cron.list", {})


def test_command_jobs_are_read_only(gw):
    gw.jobs["cmd"] = {"id": "cmd", "name": "shell", "enabled": True, "createdAtMs": 5,
                      "schedule": {"kind": "every", "everyMs": 3600000},
                      "payload": {"kind": "command", "argv": ["rm", "-rf", "/"]}, "state": {}}
    job = next(j for j in run(web.api_cron_list())["jobs"] if j["id"] == "cmd")
    assert job["readonly"] is True and job["system"] is False
    for fn in (web.api_cron_run, web.api_cron_pause, web.api_cron_delete):
        with pytest.raises(HTTPException) as e:
            run(fn("cmd"))
        assert e.value.status_code == 403
    assert not any(c[0] == "cron.run" for c in gw.calls)


def test_run_now_not_run_is_409(gw, monkeypatch):
    jid = run(web.api_cron_create(web.CronCreateRequest(
        name="x", message="y", schedule={"mode": "every", "minutes": 60})))["job"]["id"]
    real = gw.__call__

    def busy(method, params, timeout=15.0):
        if method == "cron.run":
            return {"ok": True, "ran": False, "reason": "already-running"}
        return real(method, params, timeout)
    monkeypatch.setattr(gc, "call", busy)
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_run(jid))
    assert e.value.status_code == 409 and "正在运行" in e.value.detail


def test_never_firing_schedule_removed(gw, monkeypatch):
    real = gw.__call__

    def no_next(method, params, timeout=15.0):
        res = real(method, params, timeout)
        if method == "cron.add":
            res["state"] = {}
        return res
    monkeypatch.setattr(gc, "call", no_next)
    with pytest.raises(HTTPException) as e:
        run(web.api_cron_create(web.CronCreateRequest(
            name="2月31", message="y", schedule={"mode": "cron", "expr": "0 9 31 2 *"})))
    assert e.value.status_code == 400 and "永远不会到" in e.value.detail
    assert [j for j in gw.jobs if j != "sys"] == []
