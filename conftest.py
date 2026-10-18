"""全仓测试沙箱：调用时解析的 OpenClaw state 路径一律落进临时目录。

真实事故：web 设置接口的用例 POST /api/settings/models/save，后端顺手把供应商同步进
openclaw.json —— 那条路径当时写死 ~/.openclaw-easel，夹具只换了 .env，于是在装过 Easel
的机器上跑一遍 pytest，就把用户真配置改得 `openclaw config validate` 不过、网关起不来。
CI 机器上没有 ~/.openclaw-easel，所以 CI 永远看不见。

state 目录的唯一真相是 easel/openclaw_workspace.state_dir()，它认 EASEL_OPENCLAW_STATE_DIR。
这里给每个用例都预先指到一个独立临时目录，靠「默认就安全」兜底，不指望每个新用例都记得沙箱。
用例自己再 monkeypatch.setenv 会覆盖这里（autouse 夹具先跑），需要「未设置」语义的用例
自己 delenv 即可。

罩不住的：import 时就算死的路径。easel/gateway_questions.py 在模块加载时算 PROFILE_DIR 等，
早于任何夹具，仍指向真机 state 目录 —— 它只读（sqlite 以 mode=ro 打开、device.json 只读），
不会写坏配置，但新代码别再学它在 import 时定路径。

为什么放仓库根而不是 tests/conftest.py：tests/ 和 skills/builtin/skill-wechat-publisher/tests/
都是带 __init__.py 的 `tests` 包，--import-mode=importlib 下两边的 conftest 都解析成模块名
`tests.conftest`，后导入的那个直接撞名、整个收集报错。根目录这份不在任何包里，模块名不冲突，
而且顺带把 skills/**/tests 也罩住了。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _sandbox_openclaw_state_dir(tmp_path_factory, monkeypatch):
    # 用独立目录而不是 tmp_path 的子目录：不往用例自己的 tmp_path 里掺东西，
    # 断言 tmp_path 内容的用例不会被这里意外创建的文件干扰。
    monkeypatch.setenv("EASEL_OPENCLAW_STATE_DIR", str(tmp_path_factory.mktemp("openclaw-state")))


@pytest.fixture(autouse=True)
def _sandbox_skill_dotenv(tmp_path_factory, monkeypatch):
    # 技能脚本读项目根 .env 的开关（如 semi_auto 的 EASEL_DOMESTIC_AUTO_PUBLISH）一律指到不存在的临时
    # 文件：开发机真 .env 里开了抖音自动点击，用例 delenv 之后也不能悄悄读到它、把半自动用例跑成自动点击。
    monkeypatch.setenv("EASEL_ENV_FILE", str(tmp_path_factory.mktemp("dotenv") / ".env"))


@pytest.fixture(autouse=True)
def isolate_web_outputs(request, tmp_path_factory, monkeypatch):
    if not request.node.path.is_relative_to(Path(__file__).parent / "tests"):
        return
    outputs = tmp_path_factory.mktemp("isolated-web-outputs")
    for name in ("app", "web.app"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "OUTPUTS_DIR"):
            monkeypatch.setattr(module, "OUTPUTS_DIR", outputs)
