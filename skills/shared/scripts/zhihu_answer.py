#!/usr/bin/env python3
"""zhihu_answer.py — 用已登录的 ZhihuProfile 对知乎问题发布回答。

用法（CWD=项目根）：
  # 预览（dry-run，不真正发布）：
  python skills/shared/scripts/zhihu_answer.py \
      --question https://www.zhihu.com/question/XXXXX \
      --content-file outputs/zhihu_answers/story1.md

  # 真正发布：
  python skills/shared/scripts/zhihu_answer.py \
      --question https://www.zhihu.com/question/XXXXX \
      --content-file outputs/zhihu_answers/story1.md \
      --exec

  # 有头模式（调试/首次校准）：
  python skills/shared/scripts/zhihu_answer.py \
      --question https://www.zhihu.com/question/XXXXX \
      --content-file outputs/zhihu_answers/story1.md \
      --exec --headed

【半自动】默认（未设 EASEL_DOMESTIC_AUTO_PUBLISH=1）：脚本在可见的真实浏览器里把回答填好，停在「发布回答」
按钮前，由用户亲自点；脚本只被动观察结果。真发前过 publish_guard（同一问题已回答过 → exit 8；平台冷却 → exit 9）。
浏览器内核同 web_publisher / xhs_publish：CloakBrowser → 本机 Chrome/Edge（EASEL_ZHIHU_BROWSER=chrome 强制 Chrome，
EASEL_ZHIHU_HEADLESS=1 仅无桌面机器用）。换内核后需要在账号页重新扫码登录一次。

依赖：playwright + chromium（与 web_publisher 共用 ZhihuProfile）
"""

from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content_guard  # noqa: E402  出站内容安全闸门
import human_input  # noqa: E402  真人节奏的鼠标/键盘
import login_state  # noqa: E402
import publish_guard  # noqa: E402  发布闸门：平台冷却 + 重复发布拦截
import real_browser  # noqa: E402  可见真实浏览器启动器（Cloak → 本机 Chrome/Edge）
import semi_auto  # noqa: E402  半自动交接：填完停在发布按钮前，由人亲自点发布

# PROJECT_ROOT：优先 EASEL_ROOT env（gateway/CLI/web 注入），否则按 __file__ 上溯。
# ⚠️ 本脚本会被 sync.sh 拍平复制到 workspace/shared/scripts/，那里 parents[3] 会算错根，
# 相对 content-file 会解析到错误目录——故 env 兜底不可省（与 manifest.py 同款）。
PROJECT_ROOT = Path(os.environ.get("EASEL_ROOT") or Path(__file__).resolve().parents[3])
PROFILE_DIR = Path.home() / ".easel-browser-profiles" / "ZhihuProfile"

# 只收确属 toast/通知的容器（不含 .Modal-content：弹窗里常是须知/规则文字，会把普通提示误判成处罚）
ZHIHU_TOAST_SELECTORS = tuple(semi_auto.DEFAULT_TOAST_SELECTORS) + (
    ".Notification", ".Messages-notification",
)
AI_DECLARE_REMINDER = "若回答含 AI 生成内容，请在窗口里手动勾选平台的 AI 内容声明。"

EDITOR_CHECK = ".public-DraftEditor-content, .DraftEditor-editorContainer [contenteditable=true]"


def die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    semi_auto.note_exit_reason(msg)
    sys.exit(code)


def _click_write_answer_btn(page) -> bool:
    """三策略触发「写回答/编辑回答」编辑器出现，返回是否成功。"""
    # 先检查是否是"编辑回答"状态（已有草稿或已发布）
    already_answered = page.evaluate("""
        () => Array.from(document.querySelectorAll('button'))
                   .some(b => (b.innerText||'').trim() === '编辑回答')
    """)
    if already_answered:
        # 有草稿或已发布的回答，点击"编辑回答"进入编辑器
        clicked = page.evaluate("""
            () => {
                const btn = Array.from(document.querySelectorAll('button'))
                    .find(b => (b.innerText||'').trim() === '编辑回答');
                if (btn) {
                    btn.scrollIntoView({block:'center'});
                    btn.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,view:window}));
                    return true;
                }
                return false;
            }
        """)
        page.wait_for_timeout(3000)
        if page.query_selector(EDITOR_CHECK):
            print("[INFO] 编辑回答 点击 → 编辑器出现", file=sys.stderr)
            return True

    try:
        btn_loc = page.locator(".WriteAnswerButton").first
        btn_loc.wait_for(state="visible", timeout=8000)
    except Exception as e:
        print(f"[WARN] WriteAnswerButton 未出现: {e}", file=sys.stderr)
        return False

    # 策略0: 真人节奏点击（被 header 覆盖层挡住会抛错，再落到策略1）
    try:
        human_input.click(page, btn_loc)
        page.wait_for_timeout(3000)
        if page.query_selector(EDITOR_CHECK):
            print("[INFO] 策略0 真人节奏点击 → 编辑器出现", file=sys.stderr)
            return True
    except Exception:
        pass

    # 策略1: dispatch_event（绕过 header 覆盖层）
    btn_loc.dispatch_event("click")
    page.wait_for_timeout(3000)
    if page.query_selector(EDITOR_CHECK):
        print("[INFO] 策略1 dispatch_event → 编辑器出现", file=sys.stderr)
        return True

    # 策略2: React 完整鼠标事件序列
    page.evaluate("""() => {
        const b = document.querySelector('.WriteAnswerButton');
        if (b) ['mousedown','mouseup','click'].forEach(t =>
            b.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window}))
        );
    }""")
    page.wait_for_timeout(3000)
    if page.query_selector(EDITOR_CHECK):
        print("[INFO] 策略2 React事件序列 → 编辑器出现", file=sys.stderr)
        return True

    # 策略3: focus + Enter 键（最可靠）
    try:
        btn_loc.focus()
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
        if page.query_selector("[contenteditable=true]"):
            print("[INFO] 策略3 focus+Enter → 编辑器出现", file=sys.stderr)
            return True
    except Exception as e:
        print(f"[WARN] 策略3 失败: {e}", file=sys.stderr)

    print("[ERROR] 所有策略均未能打开编辑器", file=sys.stderr)
    return False


def _find_editor(page):
    """找到可见的回答编辑器元素。"""
    selectors = [
        ".DraftEditor-editorContainer [contenteditable=true]",
        "[contenteditable=true][data-contents]",
        ".public-DraftEditor-content",
        ".AnswerForm [contenteditable=true]",
        "[contenteditable=true]",
    ]
    for sel in selectors:
        try:
            page.wait_for_selector(sel, timeout=5000)
            el = page.query_selector(sel)
            if el and el.is_visible():
                print(f"[INFO] 找到编辑器: {sel}", file=sys.stderr)
                return el
        except Exception:
            pass
    return None


def type_into_editor(page, text: str) -> bool:
    """点击「写回答/编辑回答」并写入内容（先清空已有草稿）。"""
    if not _click_write_answer_btn(page):
        print("[WARN] 写回答按钮未能打开编辑器，尝试直接查找", file=sys.stderr)

    editor = _find_editor(page)
    if not editor:
        print("[ERROR] 未找到回答编辑器", file=sys.stderr)
        return False

    # 激活编辑器（真人节奏点击；被挡住点不了再退回 JS click）
    try:
        human_input.click(page, editor)
    except Exception:
        page.evaluate("el => el.click()", editor)
    page.wait_for_timeout(500)

    # 清空已有草稿内容（全选删除）
    page.keyboard.press("ControlOrMeta+A")
    page.wait_for_timeout(300)
    page.keyboard.press("Backspace")
    page.wait_for_timeout(500)
    print("[INFO] 已清空编辑器草稿", file=sys.stderr)

    _human_type(page, text)
    page.wait_for_timeout(1500)
    return True


_HUMAN_TYPE_MAX = 600   # 超过这个长度的长文不逐词组敲（太慢），一行一行整段上屏


def _human_type(page, text: str) -> None:
    """在当前焦点处输入（保留换行）：短文本按真人节奏，长文本按行整段上屏。"""
    if len(text) <= _HUMAN_TYPE_MAX:
        human_input.type_text(page, text)
        return
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            page.keyboard.insert_text(line)
            page.wait_for_timeout(200)
        if i < len(lines) - 1:
            page.keyboard.press("Enter")


def _click_publish_btn(page) -> bool:
    """点击「发布回答/提交修改」按钮 — JS遍历全部button，不依赖视口内可见。"""
    # 候选按钮文本（发布回答 和 提交修改 均可）
    PUBLISH_TEXTS = ['发布回答', '提交修改']

    # 策略0: 真人节奏点击（human_input）；点不了（被挡/没找到）才落到下面的 JS 点击。每次发布只会点中一次。
    for btn_text in PUBLISH_TEXTS:
        try:
            loc = page.locator(f"button:has-text('{btn_text}')").first
            loc.wait_for(state="visible", timeout=3000)
            human_input.click(page, loc)
            page.wait_for_timeout(4000)
            print(f"[INFO] 发布按钮 [{btn_text}] 真人节奏点击 OK", file=sys.stderr)
            return True
        except Exception:
            continue

    # 策略1: JS遍历所有button，找含候选文本的，scrollIntoView再click
    clicked = page.evaluate("""
        () => {
            const texts = ['发布回答', '提交修改'];
            const btns = Array.from(document.querySelectorAll('button'));
            const pub = btns.find(b => texts.some(t => (b.innerText || '').trim().includes(t)));
            if (pub) {
                pub.scrollIntoView({behavior:'instant', block:'center'});
                pub.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,view:window}));
                return pub.innerText.trim();
            }
            return '';
        }
    """)
    if clicked:
        page.wait_for_timeout(4000)
        print(f"[INFO] 发布按钮 [{clicked}] JS遍历点击 OK", file=sys.stderr)
        return True

    print("[WARN] JS遍历未找到发布按钮，尝试 locator attached", file=sys.stderr)

    # 策略2: locator state=attached（不要求在视口内），两种文本都试
    for btn_text in PUBLISH_TEXTS:
        try:
            pub_loc = page.locator(f"button:has-text('{btn_text}')").first
            pub_loc.wait_for(state="attached", timeout=5000)
            pub_loc.scroll_into_view_if_needed()
            pub_loc.dispatch_event("click")
            page.wait_for_timeout(4000)
            print(f"[INFO] 发布按钮 [{btn_text}] locator+attached OK", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[WARN] 发布按钮 [{btn_text}] locator 失败: {e}", file=sys.stderr)

    return False


def question_key(question_url: str) -> str:
    """闸门用的「标题」键：同一个问题只回答一次（按问题 id 归一，不看回答正文）。"""
    import re
    m = re.search(r"/question/(\d+)", question_url or "")
    return f"知乎回答问题{m.group(1)}" if m else f"知乎回答{question_url}"


def _answer_published(page, baseline_url: str) -> bool:
    """回答已发布的被动判定（选择器/路径未在真机校准，宁可漏判也不误判）：
    URL 变成 .../answer/<id> 且和交接时不同；或出现含「发布成功」的 toast。"""
    try:
        url = page.url or ""
    except Exception:
        return False
    if "/answer/" in url and url != baseline_url:
        return True
    try:
        for t in semi_auto._toast_texts(page, ZHIHU_TOAST_SELECTORS):
            if "发布成功" in t or "回答成功" in t:
                return True
    except Exception as e:
        if semi_auto._looks_closed(e):
            raise
    return False


def _scan_block_toasts(page) -> None:
    """扫 toast/通知文本：命中平台处罚/限制提示 → 设冷却并 exit 9，不重试。"""
    try:
        texts = semi_auto._toast_texts(page, ZHIHU_TOAST_SELECTORS)
    except Exception:
        return
    for text in texts:
        if publish_guard.classify_block_text(text):
            publish_guard.on_block_detected("zhihu", text)
            sys.exit(publish_guard.EXIT_COOLDOWN)


def _launch(p, headed: bool = True):
    """real_browser.launch：与 web_publisher 的知乎登录共用 ZhihuProfile + 同一套引擎/指纹。"""
    return real_browser.launch(
        p, profile_dir=PROFILE_DIR, headed=headed, proxy=None, platform_label="知乎",
        headless_env="EASEL_ZHIHU_HEADLESS", browser_env="EASEL_ZHIHU_BROWSER",
        chrome_hint="在账号页重新扫码登录知乎")


def _guard_status_lines(media, question_url: str) -> list[str]:
    """闸门状态（只读，不退出、不开浏览器）：冷却 / 重复，供 dry-run 展示。"""
    lines = []
    try:
        cd = publish_guard.active_cooldown("zhihu")
        if cd:
            lines.append(f"⛔ 闸门：知乎处于冷却期（{cd.get('reason') or '未记录'}），真发会以退出码 9 拒绝；只有用户能解除")
        dup = publish_guard.find_duplicate("zhihu", media, question_key(question_url))
        if dup:
            lines.append(f"⛔ 闸门：检测到重复回答（{dup.get('published_at')} 已回答过同一问题），"
                         "真发会以退出码 8 拒绝（用户明确要求重发才可加 --allow-repost）")
        if not lines:
            lines.append("✅ 闸门：无冷却、无重复，可发布")
    except Exception as e:  # noqa: BLE001
        lines.append(f"⚠️ 闸门状态读取失败：{type(e).__name__}")
    return lines


def publish_answer(question_url: str, content: str, headed: bool = True, dry_run: bool = True, *,
                   semi: bool | None = None, status_file: str | None = None,
                   handoff_timeout: float = 3600, ai_declare: bool = True,
                   content_path: Path | None = None) -> dict:
    result = {"success": False, "url": "", "error": ""}
    if semi is None:
        semi = not semi_auto.auto_click_allowed("zhihu")

    if dry_run:
        # dry-run 只打印计划：不启动浏览器、不访问知乎（避免一次无谓的自动化访问）
        print(f"[DRY-RUN] 将回答问题：{question_url}", file=sys.stderr)
        print(f"[DRY-RUN] 回答字数：{len(content)} 字", file=sys.stderr)
        print(f"[DRY-RUN] 内容预览（前100字）：{content[:100]}...", file=sys.stderr)
        print(f"[DRY-RUN] 模式：{'半自动（窗口里填好，由你亲自点发布）' if semi else '自动点击（EASEL_DOMESTIC_AUTO_PUBLISH=1）'}",
              file=sys.stderr)
        for ln in _guard_status_lines([str(content_path)] if content_path else [], question_url):
            print(f"[DRY-RUN] {ln}", file=sys.stderr)
        result["success"] = True
        result["url"] = question_url
        result["dry_run"] = True
        return result

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _launch(p, headed=True)   # 发布一律开可见窗口
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            # 1. 打开问题页
            print(f"[INFO] 访问问题页: {question_url}", file=sys.stderr)
            page.goto(question_url, wait_until="networkidle", timeout=40000)
            page.wait_for_timeout(2000)

            # 检查登录态
            if page.query_selector(".SignContainer, .Login-content"):
                result["error"] = "未登录知乎，请先在「账号」页扫码登录"
                return result

            # 获取问题标题
            title = ""
            for sel in ["h1.QuestionHeader-title", "h1"]:
                el = page.query_selector(sel)
                if el:
                    title = el.inner_text().strip()[:60]
                    break
            print(f"[INFO] 问题标题: {title}", file=sys.stderr)

            # 2. 写入回答内容
            ok = type_into_editor(page, content)
            if not ok:
                result["error"] = "无法写入编辑器"
                return result

            page.wait_for_timeout(1500)
            baseline_url = page.url or ""
            media = [str(content_path)] if content_path else []

            # 3. 半自动：停在「发布回答」前，由用户亲自点；脚本只被动观察
            if semi:
                note = AI_DECLARE_REMINDER if ai_declare else ""

                def _cb(state: str, message: str) -> None:
                    if state == "awaiting_user_click" and note:
                        print(f"⚠️ {note}", flush=True)
                        try:
                            login_state.write_status(status_file, state, f"{message} {note}")
                        except OSError:
                            pass

                outcome = semi_auto.await_human_publish(
                    page, platform="zhihu", is_published=lambda pg: _answer_published(pg, baseline_url),
                    toast_selectors=ZHIHU_TOAST_SELECTORS, status_file=status_file,
                    timeout_s=handoff_timeout, on_status=_cb)
                if outcome == "blocked":
                    sys.exit(publish_guard.EXIT_COOLDOWN)
                if outcome != "published":
                    why = "窗口已被关闭" if outcome == "closed" else "等待你点击发布超时"
                    result["error"] = (f"知乎回答未发布：{why}，没有确认发布成功。"
                                       "请先到知乎核对，不要自动重试。")
                    return result
                # _answer_published 本身就是严格判定（URL 变成 /answer/<id> 或「发布成功」toast）：核对通过才写 success
                result["success"] = True
                result["url"] = page.url
                publish_guard.record_publish("zhihu", media, question_key(question_url), url=page.url or "")
                semi_auto.report_final(status_file, "success", "发布成功（已检测到回答页/发布成功提示）。")
                return result

            # 3'. 自动点击逃生口（EASEL_DOMESTIC_AUTO_PUBLISH=1，仅用户自己设）：只点一次，不重试
            published = _click_publish_btn(page)
            if not published:
                result["error"] = "未找到或无法点击发布回答按钮"
                return result
            _scan_block_toasts(page)   # 处罚/限制提示 → 设冷却 + exit 9
            current_url = page.url
            print(f"[INFO] 当前页面 URL: {current_url}", file=sys.stderr)
            if _answer_published(page, baseline_url):
                result["success"] = True
                result["url"] = current_url
                publish_guard.record_publish("zhihu", media, question_key(question_url), url=current_url or "")
            else:
                result["url"] = current_url
                result["error"] = "已点击发布但未确认成功（URL 未变成回答页、无成功提示）。不要重试，请到知乎核对。"
                # 发布按钮已点过但结果未确认：记 unconfirmed 账，防止误二发
                try:
                    publish_guard.record_publish("zhihu", media, question_key(question_url), url="", unconfirmed=True)
                except Exception as e:  # noqa: BLE001
                    print(f"[WARN] 未确认发布的记账失败：{e}", file=sys.stderr)
            return result
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def _selftest() -> int:
    """轻量自测（不启浏览器）：校验选择器常量、内容读取与相对路径解析逻辑。"""
    import tempfile
    assert EDITOR_CHECK and "contenteditable" in EDITOR_CHECK, "编辑器选择器不应为空"
    assert callable(real_browser.launch), "应走 real_browser 启动器"
    assert question_key("https://www.zhihu.com/question/123456/answer/9") == question_key(
        "https://www.zhihu.com/question/123456"), "同一问题应得同一闸门键"
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "a.md"
        f.write_text("回答正文\n\n第二段", encoding="utf-8")
        assert f.read_text(encoding="utf-8").strip() == "回答正文\n\n第二段"
    # 相对 content-file 应挂到 PROJECT_ROOT 下
    rel = Path("outputs/x/answer.md")
    assert (PROJECT_ROOT / rel).is_absolute()
    try:
        import playwright  # noqa: F401
        pw = "yes"
    except Exception:
        pw = "MISSING（需 pip install playwright && playwright install chromium）"
    print(f"zhihu_answer.py selftest: OK (playwright={pw})")
    return 0


def main():
    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest())
    parser = argparse.ArgumentParser(description="知乎问题回答发布工具")
    parser.add_argument("--selftest", action="store_true", help="离线自检")
    parser.add_argument("--question", required=True, help="知乎问题 URL")
    parser.add_argument("--content-file", required=True, help="回答内容文件路径")
    parser.add_argument("--exec", action="store_true", dest="execute", help="真正发布（默认 dry-run）")
    parser.add_argument("--allow-unsafe", action="store_true",
                        help="放行内容安全闸门（检出内部设置泄露也照发，谨慎）")
    parser.add_argument("--headed", action="store_true", help="（兼容保留）发布一律开可见窗口")
    parser.add_argument("--allow-repost", action="store_true",
                        help="放行重复发布拦截（仅当用户明确要求重复回答同一问题/重发同一内容）")
    parser.add_argument("--handoff-timeout", type=float, default=3600,
                        help="半自动：等用户亲自点「发布回答」的最长秒数（默认 3600）")
    parser.add_argument("--status-file", help="半自动状态 JSON 输出路径（awaiting_user_click / success / error）")
    parser.add_argument("--ai-declare", action=argparse.BooleanOptionalAction, default=True,
                        help="回答含 AI 内容时，交接提示里提醒在窗口里手动勾 AI 声明（默认开；仅影响提醒文案）")
    args = parser.parse_args()

    content_path = Path(args.content_file)
    if not content_path.is_absolute():
        content_path = PROJECT_ROOT / content_path
    if not content_path.exists():
        die(f"内容文件不存在：{content_path}")

    content = content_path.read_text(encoding="utf-8").strip()
    if not content:
        die("内容文件为空")

    dry_run = not args.execute
    # 出站内容安全闸门：真发前扫描回答正文，检出内部设置泄露即阻止发布（dry-run 只告警）。
    content_guard.guard_or_die([content], exec_mode=not dry_run,
                               allow_unsafe=args.allow_unsafe, label="知乎回答内容")
    if not dry_run:
        # 发布闸门：平台冷却（exit 9）+ 同一问题重复回答（exit 8）。放在起浏览器之前。
        publish_guard.guard_before_publish("zhihu", [str(content_path)], question_key(args.question),
                                           allow_repost=args.allow_repost)
    mode_label = "DRY-RUN" if dry_run else "EXEC"
    print(f"[{mode_label}] 知乎问题回答发布", file=sys.stderr)
    print(f"  问题: {args.question}", file=sys.stderr)
    print(f"  内容: {content_path} ({len(content)} 字)", file=sys.stderr)

    result = publish_answer(
        question_url=args.question,
        content=content,
        headed=True,
        dry_run=dry_run,
        status_file=args.status_file,
        handoff_timeout=args.handoff_timeout,
        ai_declare=args.ai_declare,
        content_path=content_path,
    )

    if not result.get("success") and not dry_run:
        # 任何失败/未确认出口：状态文件写成终态 error（不留 verifying / awaiting_user_click）
        semi_auto.report_final(args.status_file, "error", result.get("error") or "发布未确认成功")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
