"""publish_guard：重复拦截 / 冷却 / 处罚文本识别。全部在 tmp_path 里，不碰真实 outputs/。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "shared" / "scripts"))

import json
from datetime import timedelta

import pytest

import publish_guard as pg


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(pg, "LEDGER_PATH", tmp_path / "_publish" / "ledger.jsonl")
    monkeypatch.setattr(pg, "COOLDOWN_PATH", tmp_path / "_publish" / "cooldown.json")
    monkeypatch.setattr(pg, "PUBLISH_LOG_PATH", tmp_path / "_analytics" / "publish-log.json")
    return tmp_path


def _video(tmp_path, name="a.mp4", data=b"video-bytes"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ---- 指纹 / 标题 ----
def test_media_fingerprint(tmp_path):
    a, b = _video(tmp_path, "a.mp4", b"x"), _video(tmp_path, "b.mp4", b"x")
    c = _video(tmp_path, "c.mp4", b"y")
    assert pg.media_fingerprint([]) == ""
    assert pg.media_fingerprint([a]) == pg.media_fingerprint([b]) != pg.media_fingerprint([c])
    assert len(pg.media_fingerprint([a])) == 64


def test_normalize_title_equivalences():
    a = pg.normalize_title("跟着动画学JLPT N2 ｜ 第二期")
    b = pg.normalize_title("跟着动画学JLPT N2｜第2期")
    assert a == b and a == "跟着动画学jlptn2第2期"
    assert pg.normalize_title("第十二集") == "第12集"
    assert pg.normalize_title("第一百零三话") == "第103话"
    assert pg.normalize_title("第二十篇") == "第20篇"
    assert pg.normalize_title("Hello, World!") == "helloworld"
    assert pg.normalize_title("") == ""


def test_canonical_platform_aliases():
    assert pg.canonical_platform("抖音") == "douyin"
    assert pg.canonical_platform("视频号") == "weixin-channels"
    assert pg.canonical_platform("微信视频号") == "weixin-channels"
    assert pg.canonical_platform("B站") == "bilibili"
    assert pg.canonical_platform("TikTok") == "tiktok"
    assert pg.canonical_platform("小红书") == "xiaohongshu"
    assert pg.canonical_platform("unknown-x") == "unknown-x"


# ---- 重复 ----
def test_duplicate_by_media_and_platform_scoped(tmp_path):
    v = _video(tmp_path)
    pg.record_publish("douyin", [v], "标题一", url="https://x/1")
    hit = pg.find_duplicate("douyin", [v], "完全不同的标题")
    assert hit and hit["reason"] == "media" and hit["source"] == "ledger" and hit["url"] == "https://x/1"
    assert pg.find_duplicate("bilibili", [v], "完全不同的标题") is None   # 跨平台不拦
    assert pg.find_duplicate("douyin", [_video(tmp_path, "o.mp4", b"other")], "另一个") is None


def test_duplicate_by_normalized_title(tmp_path):
    pg.record_publish("douyin", [_video(tmp_path)], "跟着动画学JLPT N2 ｜ 第二期")
    hit = pg.find_duplicate("抖音", [_video(tmp_path, "n.mp4", b"new")], "跟着动画学JLPT N2｜第2期")
    assert hit and hit["reason"] == "title"


def test_duplicate_window(tmp_path):
    v = _video(tmp_path)
    pg.record_publish("douyin", [v], "t")
    rows = pg._read_ledger()
    rows[0]["published_at"] = (pg._now() - timedelta(days=40)).isoformat()
    pg.ledger_path().write_text(json.dumps(rows[0], ensure_ascii=False) + "\n", encoding="utf-8")
    assert pg.find_duplicate("douyin", [v], "t") is None
    assert pg.find_duplicate("douyin", [v], "t", window_days=60) is not None


def test_duplicate_from_publish_log(tmp_path):
    log = pg.publish_log_path()
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"version": "1.0", "entries": [
        {"id": 1, "platform": "视频号", "title": "同一个标题！", "url": "u",
         "published_at": pg._now().isoformat()},
        {"id": 2, "platform": "抖音", "title": "别的", "published_at": "2020-01-01T00:00:00+08:00"},
    ]}, ensure_ascii=False), encoding="utf-8")
    hit = pg.find_duplicate("weixin-channels", [], "同一个标题")
    assert hit and hit["source"] == "publish-log" and hit["reason"] == "title"
    assert pg.find_duplicate("douyin", [], "同一个标题") is None
    assert pg.find_duplicate("douyin", [], "别的") is None   # 太旧


def test_empty_title_never_matches(tmp_path):
    pg.record_publish("douyin", [], "")
    assert pg.find_duplicate("douyin", [], "") is None


def test_corrupt_ledger_line_warns_but_does_not_crash(tmp_path, capsys):
    pg.ledger_path().parent.mkdir(parents=True)
    pg.ledger_path().write_text("not json\n", encoding="utf-8")
    assert pg.find_duplicate("douyin", [], "t") is None
    assert "损坏" in capsys.readouterr().err


def _corrupt_cooldown():
    pg.cooldown_path().parent.mkdir(parents=True, exist_ok=True)
    pg.cooldown_path().write_text("{broken", encoding="utf-8")


def test_corrupt_cooldown_fails_closed_for_every_platform(capsys):
    _corrupt_cooldown()
    for plat in ("douyin", "xiaohongshu", "zhihu", "bilibili"):
        cd = pg.active_cooldown(plat)
        assert cd and cd["corrupt"] is True
        assert "检查" in cd["reason"] and "cooldown.json" in cd["reason"]
    with pytest.raises(SystemExit) as e:
        pg.guard_before_publish("douyin", [], "t")
    assert e.value.code == pg.EXIT_COOLDOWN
    assert "损坏" in capsys.readouterr().err


def test_set_cooldown_on_corrupt_file_quarantines_first(capsys):
    _corrupt_cooldown()
    pg.set_cooldown("douyin", "被封")
    asides = list(pg.cooldown_path().parent.glob("cooldown.json.corrupt-*"))
    assert len(asides) == 1 and asides[0].read_text(encoding="utf-8") == "{broken"
    assert "已移到" in capsys.readouterr().err
    assert pg.active_cooldown("douyin")["reason"] == "被封"
    assert pg.active_cooldown("zhihu") is None   # 文件已修复，别的平台恢复正常判定


def test_clear_cooldown_on_corrupt_file_quarantines_first(capsys):
    _corrupt_cooldown()
    assert pg.clear_cooldown("douyin") is False
    assert len(list(pg.cooldown_path().parent.glob("cooldown.json.corrupt-*"))) == 1
    assert "已移到" in capsys.readouterr().err


def test_cooldown_status_cli_reports_corrupt(capsys):
    _corrupt_cooldown()
    assert pg.main(["status"]) == 0
    assert "损坏" in capsys.readouterr().out


def test_ledger_is_append_only(tmp_path):
    v = _video(tmp_path)
    pg.record_publish("douyin", [v], "a")
    before = pg.ledger_path().read_bytes()
    pg.record_publish("douyin", [v], "b")
    after = pg.ledger_path().read_bytes()
    assert after.startswith(before) and after.count(b"\n") == 2   # 只追加，不重写已有内容


def test_ledger_append_preserves_corrupt_line_and_fsyncs(tmp_path, monkeypatch):
    pg.ledger_path().parent.mkdir(parents=True)
    pg.ledger_path().write_text("garbage-line\n", encoding="utf-8")
    synced = []
    real = pg.os.fsync
    monkeypatch.setattr(pg.os, "fsync", lambda fd: (synced.append(fd), real(fd))[1])
    pg.record_publish("douyin", [], "t")
    assert synced
    text = pg.ledger_path().read_text(encoding="utf-8")
    assert text.startswith("garbage-line\n")   # 坏行不被抹掉
    assert pg.find_duplicate("douyin", [], "t")


def test_record_publish_unconfirmed_flag_blocks_second_post(tmp_path):
    v = _video(tmp_path)
    rec = pg.record_publish("douyin", [v], "t", url="", unconfirmed=True)
    assert rec["unconfirmed"] is True and rec["url"] == ""
    assert pg.find_duplicate("douyin", [v], "other title")["reason"] == "media"


# ---- 冷却 ----
def test_cooldown_lifecycle():
    assert pg.active_cooldown("douyin") is None
    pg.set_cooldown("douyin", "被限制", evidence="原文")
    cd = pg.active_cooldown("抖音")
    assert cd and cd["reason"] == "被限制" and cd["until"] is None
    assert pg.active_cooldown("bilibili") is None
    assert pg.clear_cooldown("douyin") is True
    assert pg.active_cooldown("douyin") is None
    assert pg.clear_cooldown("douyin") is False


def test_cooldown_expiry():
    pg.set_cooldown("douyin", "r", until=pg._now() - timedelta(hours=1))
    assert pg.active_cooldown("douyin") is None
    pg.set_cooldown("douyin", "r", until=pg._now() + timedelta(hours=1))
    assert pg.active_cooldown("douyin") is not None
    with pytest.raises(ValueError):
        pg.set_cooldown("douyin", "r", until="garbage")


# ---- classify ----
@pytest.mark.parametrize("text", [
    "视频投稿功能已封禁，详情见【消息-系统通知】",
    "您的发布功能被限制",
    "发文功能已被冻结",
    "投稿权限已被封禁",
    "操作过于频繁，请稍后再试",
    "账号存在风险，已限制发布",
    "您的账号已被封禁",
    "你已被禁言",
    "您的账号已被限制发布",
    "你已被禁止发布笔记",
    "笔记发布受限",
    "账号被限流",
    "您的账号涉嫌违规，发布权限已受限",
    "你的账号存在违规行为，投稿功能暂不可用",
    "发布功能已被冻结",
])
def test_classify_positive(text):
    assert pg.classify_block_text(text)


@pytest.mark.parametrize("text", [
    "请勿发布违规内容",
    "违规内容将被处理",
    "请勿发布违规内容，否则账号将被封禁",
    "账号异常登录提醒",
    "检测到账号异常登录，请确认是否本人操作",
    "账号异常，请联系客服",      # 单独的「账号异常/存在风险」不算处罚，必须带限制类词
    "当前账号存在风险",
    "如果违规，发布功能将被限制",
    "发布违规内容可能会被限流",
    "违规内容会被平台处理",
    "发布成功",
    "发布前请阅读社区规范，遵守相关法律法规",
    "上传中，请勿关闭页面",
    "投稿须知：视频时长不得超过15分钟",
    "封面设置",
    "",
    None,
])
def test_classify_negative(text):
    assert pg.classify_block_text(text) is None


def test_on_block_detected_sets_cooldown(capsys):
    rec = pg.on_block_detected("douyin", "视频投稿功能已封禁，详情见【消息-系统通知】")
    assert pg.active_cooldown("douyin")["evidence"].startswith("视频投稿功能已封禁")
    assert rec["until"] is None
    assert "冷却" in capsys.readouterr().err


# ---- guard ----
def test_guard_cooldown_first(tmp_path, capsys):
    v = _video(tmp_path)
    pg.record_publish("douyin", [v], "t")
    pg.set_cooldown("douyin", "被封")
    with pytest.raises(SystemExit) as e:
        pg.guard_before_publish("douyin", [v], "t", allow_repost=True)   # allow_repost 也绕不过冷却
    assert e.value.code == pg.EXIT_COOLDOWN == 9
    assert "用户" in capsys.readouterr().err


def test_guard_duplicate_and_allow_repost(tmp_path, capsys):
    v = _video(tmp_path)
    pg.guard_before_publish("douyin", [v], "t")        # 无记录：放行
    pg.record_publish("douyin", [v], "t")
    with pytest.raises(SystemExit) as e:
        pg.guard_before_publish("douyin", [v], "t")
    assert e.value.code == pg.EXIT_DUPLICATE == 8
    assert "--allow-repost" in capsys.readouterr().err
    pg.guard_before_publish("douyin", [v], "t", allow_repost=True)
    pg.guard_before_publish("bilibili", [v], "t")      # 别的平台放行


def test_exit_codes_do_not_clash():
    import content_guard
    assert {pg.EXIT_DUPLICATE, pg.EXIT_COOLDOWN}.isdisjoint({content_guard.EXIT_LEAK, 1, 2, 3, 5, 6})


# ---- CLI ----
def test_cli(tmp_path, capsys):
    v = _video(tmp_path)
    assert pg.main(["check", "--platform", "douyin", "--title", "t", "--media", v]) == 0
    pg.record_publish("douyin", [v], "t")
    assert pg.main(["check", "--platform", "douyin", "--title", "t", "--media", v]) == 8
    assert pg.main(["check", "--platform", "douyin", "--title", "t", "--media", v, "--allow-repost"]) == 0
    assert pg.main(["cooldown", "set", "--platform", "douyin", "--reason", "手动"]) == 0
    assert pg.main(["check", "--platform", "douyin", "--title", "x"]) == 9
    assert pg.main(["status", "--platform", "douyin"]) == 0
    assert "冷却中" in capsys.readouterr().out
    assert pg.main(["cooldown", "clear", "--platform", "douyin"]) == 0
    assert pg.active_cooldown("douyin") is None


@pytest.mark.parametrize("text", [
    "账号违规，已被限制发布若干天",       # 「若干」不是假设语气的「若」
    "账号存在异常，暂时无法发布",
    "账号异常，无法发布",
])
def test_block_text_review_followups_detected(text):
    assert pg.classify_block_text(text)


@pytest.mark.parametrize("text", [
    "若账号异常将被限制发布",              # 真正的假设句仍不命中
    "账号异常登录提醒",
])
def test_block_text_review_followups_ignored(text):
    assert pg.classify_block_text(text) is None


def test_ledger_append_after_partial_line_keeps_new_record(tmp_path):
    """上次写到一半崩溃留下没换行的半行：新记录要单独成行，仍能被查重认出来。"""
    pg.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    pg.LEDGER_PATH.write_text('{"platform": "douyin", "title": "半行', encoding="utf-8")
    v = _video(tmp_path)
    pg.record_publish("douyin", [v], "完整的一条")
    lines = pg.LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["title"] == "完整的一条"
    assert pg.find_duplicate("douyin", [v], "完整的一条")
