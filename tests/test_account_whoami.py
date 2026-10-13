"""账号校验（whoami）接口。来自上游，按本分支的防封策略改过：
国内浏览器平台只有手动校验（manual=1）才起浏览器、小红书一律不起，所以用例用知乎等平台并带 manual=1；
登录 runner 占着 profile 时返回 pending 而不是 409；结果带 loginTs（登录标记指纹）。"""
import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

import web.app as web


@pytest.fixture
def account_state(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "LOGIN_DIR", tmp_path)
    monkeypatch.setattr(web, "LOGIN_PROCESSES", {})
    monkeypatch.setattr(web, "_WHOAMI_CACHE", {})
    monkeypatch.setattr(web, "_WHOAMI_LOCK", threading.Lock())
    monkeypatch.setattr(web, "_WHOAMI_TASKS", {})
    return tmp_path


def test_whoami_does_not_start_browser_during_login(account_state, monkeypatch):
    web.LOGIN_PROCESSES["zhihu"] = SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: pytest.fail("login owns profile"))
    result = asyncio.run(web.api_account_whoami("zhihu", manual=1))
    assert not result["loggedIn"]
    assert not web._WHOAMI_CACHE


def test_whoami_waits_for_successful_login_to_release_profile(account_state, monkeypatch):
    web._write_login_marker("weixin-channels", "success")
    events = []
    process = SimpleNamespace(poll=lambda: None if not events else 0,
                              wait=lambda **kwargs: events.append("released"))
    web.LOGIN_PROCESSES["weixin-channels"] = process
    def run(*args, **kwargs):
        assert events == ["released"]
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "loggedIn": True, "name": "Own channel", "avatar": "https://self.test/channel.png",
        }))

    monkeypatch.setattr(web.subprocess, "run", run)
    result = asyncio.run(web.api_account_whoami("weixin-channels", manual=1, force=True))
    assert result["name"] == "Own channel"
    assert result["avatar"] == "https://self.test/channel.png"


def test_whoami_reports_profile_save_timeout_without_caching_empty_identity(account_state, monkeypatch):
    web._write_login_marker("weixin-channels", "success")
    def wait(**kwargs):
        raise web.subprocess.TimeoutExpired("login", 8)

    web.LOGIN_PROCESSES["weixin-channels"] = SimpleNamespace(poll=lambda: None, wait=wait)
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: pytest.fail("profile still locked"))
    # 本分支不报 409：返回 pending（loginTs 为 null，前端等登录标记再变后重新校验），同样不起浏览器、不缓存
    result = asyncio.run(web.api_account_whoami("weixin-channels", manual=1, force=True))
    assert result["pending"] is True and result["loginTs"] is None
    assert not web._WHOAMI_CACHE


def test_mp_whoami_reads_backend_account_not_configured_label(account_state, monkeypatch):
    web._write_login_marker("wechat-oa-mp", "success")
    monkeypatch.setattr(web, "_wechat_web_account", lambda: {"name": "Configured label"})
    def run(command, **kwargs):
        assert command[-2:] == ["whoami", "--no-proxy"]
        assert command[1].endswith("weixin_mp_stats.py")
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "loggedIn": True, "name": "Actual MP account", "avatar": "https://self.test/mp.png",
        }))

    monkeypatch.setattr(web.subprocess, "run", run)
    result = asyncio.run(web.api_account_whoami("wechat-oa", manual=1, force=True))
    assert result["name"] == "Actual MP account"
    assert result["avatar"] == "https://self.test/mp.png"
    assert (account_state / "wechat-oa-mp.json").exists()
    assert not (account_state / "wechat-oa.json").exists()


def test_mp_expired_session_can_use_appid_without_faking_backend_login(account_state, monkeypatch):
    web._write_login_marker("wechat-oa-mp", "success")
    monkeypatch.setattr(web, "_wechat_has_credentials", lambda: True)
    monkeypatch.setattr(web, "_wechat_web_account", lambda: {"name": "Configured label"})
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn":false,"name":"","avatar":""}'))
    result = asyncio.run(web.api_account_whoami("wechat-oa", manual=1, force=True))
    # loginTs 是本分支给前端的登录标记指纹；mp 标记已删，所以是 null
    assert result == {"loggedIn": True, "name": "Configured label", "avatar": "", "loginTs": None}
    assert not (account_state / "wechat-oa-mp.json").exists()


def test_douyin_whoami_does_not_use_model_proxy(account_state, monkeypatch):
    def run(command, **kwargs):
        assert command[-2:] == ["whoami", "--no-proxy"]
        return SimpleNamespace(returncode=0, stdout='{"loggedIn":false,"name":"","avatar":""}')

    monkeypatch.setattr(web.subprocess, "run", run)
    assert not asyncio.run(web.api_account_whoami("douyin", manual=1, force=True))["loggedIn"]


def test_whoami_network_error_preserves_success_marker(account_state, monkeypatch):
    web._write_login_marker("zhihu", "success")
    initial = (account_state / "zhihu.json").read_bytes()
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({"loggedIn": False, "error": "maintenance"})))
    with pytest.raises(web.HTTPException) as error:
        asyncio.run(web.api_account_whoami("zhihu", manual=1))
    assert error.value.status_code == 502
    assert (account_state / "zhihu.json").read_bytes() == initial
    assert not web._WHOAMI_CACHE


def test_whoami_result_before_new_login_cannot_remove_success_marker(account_state, monkeypatch):
    def run(*args, **kwargs):
        web._write_login_marker("zhihu", "success")
        return SimpleNamespace(returncode=0, stdout='{"loggedIn": false}')

    monkeypatch.setattr(web.subprocess, "run", run)
    assert asyncio.run(web.api_account_whoami("zhihu", manual=1))["loggedIn"]
    assert (account_state / "zhihu.json").exists()
    assert not web._WHOAMI_CACHE


def test_whoami_invalid_boolean_is_not_a_verified_logout(account_state, monkeypatch):
    web._write_login_marker("zhihu", "success")
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn": "false"}'))
    with pytest.raises(web.HTTPException) as error:
        asyncio.run(web.api_account_whoami("zhihu", manual=1))
    assert error.value.status_code == 502
    assert not web._WHOAMI_CACHE


def test_unknown_account_identity_is_not_returned_as_verified_logout(account_state, monkeypatch):
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn":false,"name":"","avatar":"","error":"not ready"}'))
    with pytest.raises(web.HTTPException) as error:
        asyncio.run(web.api_account_whoami("weixin-channels", manual=1, force=True))
    assert error.value.status_code == 502
    assert not web._WHOAMI_CACHE
    assert not (account_state / "weixin-channels.json").exists()


def test_unknown_account_identity_preserves_last_verified_identity(account_state, monkeypatch):
    web._write_login_marker("weixin-channels", "success")
    identity = {"loggedIn": True, "name": "Own channel", "avatar": "https://self.test/channel.png"}
    web._WHOAMI_CACHE["weixin-channels"] = (web.time.time(), identity)
    initial = (account_state / "weixin-channels.json").read_bytes()
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn":false,"error":"not ready"}'))
    with pytest.raises(web.HTTPException) as error:
        asyncio.run(web.api_account_whoami("weixin-channels", manual=1, force=True))
    assert error.value.status_code == 502
    assert web._WHOAMI_CACHE["weixin-channels"][1] == identity
    assert (account_state / "weixin-channels.json").read_bytes() == initial


def test_manual_whoami_bypasses_server_cache(account_state, monkeypatch):
    calls = []
    web._WHOAMI_CACHE["zhihu"] = (web.time.time(), {
        "loggedIn": False, "name": "", "avatar": ""})

    def run(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout='{"loggedIn": true}')

    monkeypatch.setattr(web.subprocess, "run", run)
    assert not asyncio.run(web.api_account_whoami("zhihu", manual=1))["loggedIn"]
    assert not calls
    assert asyncio.run(web.api_account_whoami("zhihu", manual=1, force=True))["loggedIn"]
    assert len(calls) == 1
    assert (account_state / "zhihu.json").exists()


def test_confident_logout_removes_expired_marker(account_state, monkeypatch):
    web._write_login_marker("zhihu", "success")
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn": false}'))
    assert not asyncio.run(web.api_account_whoami("zhihu", manual=1))["loggedIn"]
    assert not (account_state / "zhihu.json").exists()
    assert not web._WHOAMI_CACHE["zhihu"][1]["loggedIn"]


def test_concurrent_account_checks_share_one_browser(account_state, monkeypatch):
    calls = []
    entered = threading.Event()
    release = threading.Event()
    def run(*args, **kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(timeout=2)
        return SimpleNamespace(returncode=0, stdout='{"loggedIn":true,"name":"Me","avatar":""}')

    monkeypatch.setattr(web.subprocess, "run", run)
    async def check():
        first = asyncio.create_task(web.api_account_whoami("zhihu", manual=1))
        assert await asyncio.to_thread(entered.wait, 2)
        second = asyncio.create_task(web.api_account_whoami("zhihu", manual=1, force=True))
        await asyncio.sleep(0)
        release.set()
        return await asyncio.gather(first, second)

    results = asyncio.run(check())
    assert len(calls) == 1
    assert calls[0]["timeout"] == 60
    assert calls[0]["encoding"] == "utf-8"
    assert results[0] == results[1]
    assert not web._WHOAMI_TASKS


def test_incomplete_identity_does_not_stay_cached_for_ten_minutes(account_state, monkeypatch):
    web._write_login_marker("zhihu", "success")
    web._WHOAMI_CACHE["zhihu"] = (web.time.time() - 61, {
        "loggedIn": True, "name": "", "avatar": ""})
    monkeypatch.setattr(web.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout='{"loggedIn":true,"name":"Me","avatar":"https://self.test/avatar"}'))
    result = asyncio.run(web.api_account_whoami("zhihu", manual=1))
    assert result["name"] == "Me"
    assert result["avatar"]
