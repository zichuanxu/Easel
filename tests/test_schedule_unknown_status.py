"""日历「待确认」状态（海外发布结果未定时 calendar_ops 写入）：网页日历要能存、能改，不能悄悄改成选题。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

import app as web  # noqa: E402
import calendar_ops  # noqa: E402


def test_web_schedule_accepts_every_calendar_ops_status(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "SCHEDULE_FILE", tmp_path / "_schedule.json")
    assert web.SCHEDULE_STATUSES == calendar_ops.CONTENT_STATUSES   # 两边状态集合不能再分叉
    item = asyncio.run(web.api_schedule_create(
        web.ScheduleItem(title="海外发布", date="2026-10-01", status="unknown")))
    assert item["status"] == "unknown"
    upd = asyncio.run(web.api_schedule_update(item["id"], web.ScheduleItem(
        title="海外发布", date="2026-10-01", status="published")))
    assert upd["status"] == "published"
