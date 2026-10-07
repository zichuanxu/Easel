"""ask_user 问答题桥接：gateway RPC 错误分类 + /api/chat/question/answer 对失效题的处理。不连真 gateway。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import app as web  # noqa: E402
from easel import gateway_questions as gq  # noqa: E402


@pytest.mark.parametrize("err", [
    # 超时被取消后再提交（截图里的场景，网关日志原文）
    {"code": "INVALID_REQUEST", "message": "question 'toolu_01Rd:0' is already cancelled",
     "details": {"reason": "QUESTION_ALREADY_TERMINAL"}},
    # 15s 宽限后记录被清理
    {"code": "INVALID_REQUEST", "message": "question 'toolu_01Rd:0' was not found",
     "details": {"reason": "QUESTION_NOT_FOUND"}},
    # 没带 details 时按 message 兜底
    {"code": "INVALID_REQUEST", "message": "question 'toolu_01Rd:0' is already expired"},
])
def test_dead_question_is_gone_not_unsupported(err):
    e = gq._classify_rpc_error("question.resolve", err)
    assert isinstance(e, gq.GatewayQuestionGoneError)
    assert not isinstance(e, gq.GatewayUnsupportedError)


def test_unknown_method_still_unsupported():
    """旧版 gateway 没有 question RPC：仍要熔断桥接。"""
    e = gq._classify_rpc_error("question.list", {"code": "INVALID_REQUEST", "message": "unknown method: question.list"})
    assert isinstance(e, gq.GatewayUnsupportedError)


def test_invalid_answer_is_plain_failure():
    e = gq._classify_rpc_error("question.resolve", {
        "code": "INVALID_REQUEST", "message": "question 'q1' requires an answer",
        "details": {"reason": "QUESTION_INVALID_ANSWER"}})
    assert type(e) is gq.GatewayQuestionError
    assert str(e).startswith("question.resolve failed:")


class _FakeClient:
    error: Exception | None = None

    def connect(self):
        pass

    def resolve(self, *_a, **_k):
        if self.error:
            raise self.error
        return {"status": "answered"}

    def close(self):
        pass


def _answer(monkeypatch, error):
    _FakeClient.error = error
    monkeypatch.setattr(web, "GatewayClient", _FakeClient)
    req = web.QuestionAnswerRequest(questionId="toolu_01Rd:0", answers={"q1": ["只重发第2期"]})
    return asyncio.run(web.api_question_answer(req))


def test_answer_dead_question_reports_gone(monkeypatch):
    out = _answer(monkeypatch, gq.GatewayQuestionGoneError("question.resolve failed: ..."))
    assert out == {"ok": False, "gone": True, "error": web.QUESTION_GONE_HINT}
    assert "not supported" not in out["error"]


def test_answer_other_error_passthrough(monkeypatch):
    out = _answer(monkeypatch, gq.GatewayQuestionError("question.resolve failed: bad"))
    assert out == {"ok": False, "error": "question.resolve failed: bad"}


def test_answer_ok(monkeypatch):
    assert _answer(monkeypatch, None) == {"ok": True, "result": {"status": "answered"}}
