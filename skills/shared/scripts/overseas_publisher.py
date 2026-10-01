#!/usr/bin/env python3
"""海外平台（TikTok / YouTube / Instagram / X / Threads）登录、登录态校验与发布。

用法（项目根目录）：
  python skills/shared/scripts/overseas_publisher.py platforms
  python skills/shared/scripts/overseas_publisher.py login --platform youtube [--status-file F] [--timeout 600]
  python skills/shared/scripts/overseas_publisher.py whoami --platform x
  python skills/shared/scripts/overseas_publisher.py publish --platform x --media out.mp4 --desc "..." [--exec]
  python skills/shared/scripts/overseas_publisher.py selftest

login 在本机弹出 Chrome 窗口，由用户亲手登录（含两步验证）；登录态保存在
~/.easel-browser-profiles/<平台>Profile。--status-file 写 login_state JSON，Web 账号页轮询它。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import calendar_ops
import content_guard
import login_state
from overseas import PLATFORMS, REQUIRED_ATTRS, base, get
from overseas.post import KIND_LABEL, Post, PostError, validate, x_weighted_length

DEFAULT_LOGIN_TIMEOUT = 600
LOGIN_POLL_MS = 2000
COOKIE_SETTLE_MS = 3000       # 看到登录态后再等一会儿，让登录 cookie 落盘再关浏览器
LOGIN_LOCK_WAIT_S = 30
WHOAMI_LOCK_WAIT_S = 20
NAV_TIMEOUT_MS = 60000

STARTING_MSG = "正在启动 Chrome…"
WINDOW_MSG = "已弹出 Chrome 窗口，请在窗口里登录 {name}，不要关掉它（可以做两步验证，最长 {minutes} 分钟）"
VERIFYING_MSG = "登录成功，正在确认登录态已保存…"
NOT_SAVED_MSG = "登录看似成功但登录态没能保存，请重试"
VERIFY_FAILED_MSG = ("登录已完成，但确认登录态时浏览器或网络出错：{err}。"
                     "可以稍后在账号页点「校验」；仍显示未登录就再登录一次")
WINDOW_CLOSED_MSG = "登录窗口被关掉了，登录没有完成。请重新点登录"
EXPIRED_MSG = "{minutes} 分钟内没有完成登录，请重新点登录"
BUSY_MSG = "{name} 的登录目录正被占用（可能在校验登录状态），请等 10 秒再点登录"

EXIT_INVALID = 2
EXIT_PLAYWRIGHT = 3
EXIT_UNKNOWN = 5
EXIT_NOT_LOGGED_IN = 6
PUBLISH_LOCK_WAIT_S = 60
VERIFY_WAIT_MS = 300000       # 有头窗口里落到验证页时，等用户亲手过验证的最长时间
UNKNOWN_MSG = "{name}：{detail}。结果待确认，请先到 {name} 上看一眼，不要直接重发"
STEP_FAILED_MSG = "{name} 发布失败：{err}（页面可能改版了，现场截图在 outputs/_login/{key}-publish-fail.png）"


def run_login(mod, status_file, timeout_s, *, launch=base.launch, clock=time.monotonic, profile_root=None) -> int:
    """弹出有头窗口让用户登录 → 关窗口 → 无头重开确认登录态已保存，才写 success。每条路都落终态。"""
    sf = status_file
    login_state.write_status(sf, "starting", STARTING_MSG)
    profile = base.profile_dir(mod, profile_root)
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(LOGIN_LOCK_WAIT_S)
    except TimeoutError:
        return _fail(sf, "error", BUSY_MSG.format(name=mod.NAME))
    try:
        return _login_locked(mod, sf, timeout_s, profile, launch, clock)
    finally:
        lock.release()


def _fail(sf, state: str, msg: str, rc: int = 1) -> int:
    login_state.write_status(sf, state, msg)
    print(f"❌ {msg}", file=sys.stderr)
    return rc


def _login_locked(mod, sf, timeout_s, profile, launch, clock) -> int:
    minutes = max(1, timeout_s // 60)
    try:
        with launch(profile, headed=True) as ctx:
            page = base.first_page(ctx)
            login_state.write_status(sf, "window_login", WINDOW_MSG.format(name=mod.NAME, minutes=minutes))
            page.goto(mod.LOGIN_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            deadline = clock() + timeout_s
            while True:
                base.ensure_window_open(page)
                if mod.is_logged_in(page):
                    page.wait_for_timeout(COOKIE_SETTLE_MS)
                    # 再看一眼：旧 cookie 会让页面短暂显示登录态又跳回登录页，这时关窗口重登就永远失败
                    if mod.is_logged_in(page):
                        break
                    continue
                if clock() >= deadline:
                    return _fail(sf, "expired", EXPIRED_MSG.format(minutes=minutes))
                page.wait_for_timeout(LOGIN_POLL_MS)
    except base.PlaywrightMissing as e:
        return _fail(sf, "error", str(e), rc=3)
    except Exception as e:  # noqa: BLE001 — 任何意外都要落 error 终态，否则账号页弹窗会一直转圈
        msg = WINDOW_CLOSED_MSG if base.is_window_closed_error(e) else f"登录出错：{base.short_err(e)}"
        return _fail(sf, "error", msg)

    login_state.write_status(sf, "verifying", VERIFYING_MSG)
    try:
        ident = _verify_saved(mod, profile, launch)
    except Exception as e:  # noqa: BLE001 — 重开浏览器 / 网络出错说明不了没存上，别吓人重登
        return _fail(sf, "error", VERIFY_FAILED_MSG.format(err=base.short_err(e)))
    if ident is None:
        return _fail(sf, "error", NOT_SAVED_MSG)
    login_state.write_status(sf, "success", ident.get("name") or "已登录")
    print(f"✅ {mod.NAME} 登录成功，已重开浏览器确认登录态已保存")
    return 0


def _verify_saved(mod, profile, launch) -> dict | None:
    with launch(profile, headed=False) as ctx:
        page = base.first_page(ctx)
        page.goto(mod.HOME_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        state = base.settle(page, mod)
        if state is None:
            raise RuntimeError("页面一直没稳定下来，登录态没法确认")
        if not state:
            return None
        return mod.read_identity(page)


def run_whoami(mod, *, launch=base.launch, profile_root=None) -> dict:
    """无头打开首页看登录态。没登录过（没有登录目录）直接返回未登录，不起浏览器；
    校验本身失败（目录被占用、浏览器 / 网络出错）带 error 字段，Web 后端据此不删登录标记。"""
    result = {"loggedIn": False, "name": "", "avatar": ""}
    profile = base.profile_dir(mod, profile_root)
    if not profile.is_dir():
        return result
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(WHOAMI_LOCK_WAIT_S)
    except TimeoutError:
        result["error"] = "登录目录正被占用（登录窗口可能还开着）"
        return result
    try:
        with launch(profile, headed=False) as ctx:
            page = base.first_page(ctx)
            page.goto(mod.HOME_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            state = base.settle(page, mod)
            if state is None:
                result["error"] = "登录态未能确认（页面一直没稳定下来）"
            elif state:
                result["loggedIn"] = True
                result.update(mod.read_identity(page))
    except Exception as e:  # noqa: BLE001 — whoami 永远输出 JSON
        result["error"] = base.short_err(e)
    finally:
        lock.release()
    return result


def build_post(a) -> Post:
    return Post(media=[Path(m).expanduser() for m in a.media or []], title=a.title or "", desc=a.desc or "",
                tags=a.tags or "", visibility=a.visibility or "")


def check_publishable(mod, post: Post) -> None:
    validate(post, name=mod.NAME, kinds=mod.KINDS, limits=mod.LIMITS, visibility=mod.VISIBILITY)
    if post.kind not in mod.READY_KINDS:
        if not mod.READY_KINDS:
            raise PostError(f"{mod.NAME} 发布还没接通（YouTube 需要账号先有频道并完成真机校准）")
        raise PostError(f"{mod.NAME} 的{KIND_LABEL[post.kind]}发布还没接通，目前只能发视频")


def _pub_fail(sf, msg: str, rc: int) -> int:
    login_state.write_status(sf, "error", msg)
    print(f"❌ {msg}", file=sys.stderr)
    return rc


def _record(mod, post: Post, fields: dict, result) -> None:
    title = post.title or (fields.get("caption") or fields.get("description") or "").split("\n")[0][:60]
    calendar_ops.record_publish(mod.KEY, title, url=result.url, ptype=KIND_LABEL[post.kind], tags=post.tags)


def run_publish(mod, post: Post, fields: dict, *, headed: bool = False, status_file=None, launch=base.launch,
                driver_cls=base.PageDriver, profile_root=None, record=None) -> int:
    """真发布：确认登录 → 平台流程 → 按结果落状态。被拦（验证页）且没开窗口时改开有头窗口重试一次。
    结果待确认（unknown）绝不重试、不记日历。record(result) 成功后记日历（测试注入）。"""
    sf = status_file
    if record is None:
        def record(result):
            _record(mod, post, fields, result)
    profile = base.profile_dir(mod, profile_root)
    if not profile.is_dir():
        return _pub_fail(sf, f"{mod.NAME} 未登录：请先在账号页登录", EXIT_NOT_LOGGED_IN)
    lock = base.ProfileLock(profile)
    try:
        lock.acquire(PUBLISH_LOCK_WAIT_S)
    except TimeoutError:
        return _pub_fail(sf, f"{mod.NAME} 的登录目录正被占用（可能在登录或校验），请稍后再发", 1)
    try:
        attempts = [True] if headed else [False, True]
        for i, use_headed in enumerate(attempts):
            try:
                return _publish_once(mod, post, fields, use_headed, sf, launch, driver_cls, profile, record)
            except base.Blocked as e:
                if i + 1 < len(attempts):
                    login_state.write_status(sf, "publishing", f"{mod.NAME} 要人工验证，已弹出浏览器窗口，请在窗口里完成验证")
                    print(f"⚠️ {mod.NAME} 拦了无头浏览器（{e}），改开窗口重试", file=sys.stderr)
                    continue
                return _pub_fail(sf, f"{mod.NAME} 要求人工验证，没能通过：{e}", 1)
        return 1
    except base.PlaywrightMissing as e:
        return _pub_fail(sf, str(e), EXIT_PLAYWRIGHT)
    finally:
        lock.release()


def _publish_once(mod, post, fields, headed, sf, launch, driver_cls, profile, record) -> int:
    with launch(profile, headed=headed) as ctx:
        drv = driver_cls(base.first_page(ctx), block_wait_ms=VERIFY_WAIT_MS if headed else 0)
        opening = (f"已弹出 {mod.NAME} 窗口，别关掉它；要人工验证就在窗口里完成（最长 {VERIFY_WAIT_MS // 60000} 分钟）"
                   if headed else f"正在打开 {mod.NAME}…")
        login_state.write_status(sf, "publishing", opening)
        drv.goto(mod.HOME_URL)
        state = drv.settle(mod)
        if state is None:
            return _pub_fail(sf, f"{mod.NAME} 登录态没法确认（页面一直没稳定），请稍后再试", 1)
        if not state:
            return _pub_fail(sf, f"{mod.NAME} 未登录：请先在账号页登录", EXIT_NOT_LOGGED_IN)
        login_state.write_status(sf, "publishing", f"正在发布到 {mod.NAME}（上传和处理视频可能要几分钟）…")
        try:
            result = mod.publish(drv, fields, post)
        except Exception as e:  # noqa: BLE001 — 点了发布之后出任何错都可能已经发出去了，只能报待确认
            if not drv.committed:
                if isinstance(e, base.StepFailed):
                    base.save_failure(drv.page, mod.KEY)
                    return _pub_fail(sf, STEP_FAILED_MSG.format(name=mod.NAME, err=e, key=mod.KEY), 1)
                raise
            result = base.Result("unknown", message=f"点了发布之后出错（{base.short_err(e)}）")
        if result.status == "success":
            msg = result.message or f"已发布到 {mod.NAME}"
            if result.url:
                msg += f"：{result.url}"
            login_state.write_status(sf, "success", msg)
            print(f"✅ {msg}")
            try:
                record(result)
            except Exception as e:  # noqa: BLE001 — 记日历失败不影响发布结果
                print(f"记日历失败（忽略）：{base.short_err(e)}", file=sys.stderr)
            return 0
        base.save_failure(drv.page, mod.KEY)
        if result.status == "unknown":
            return _pub_fail(sf, UNKNOWN_MSG.format(name=mod.NAME, detail=result.message), EXIT_UNKNOWN)
        return _pub_fail(sf, f"{mod.NAME} 发布失败：{result.message}", 1)


def cmd_publish(a) -> int:
    mod = get(a.platform)
    post = build_post(a)
    sf = a.status_file
    try:
        check_publishable(mod, post)
    except PostError as e:
        return _pub_fail(sf, str(e), EXIT_INVALID)
    fields = mod.compose(post)
    parts = [post.title, post.desc, post.tags, *(m.name for m in post.media)]   # 文件名也会发出去
    label = f"{mod.NAME} 发布内容"
    if not a.exec:
        content_guard.guard_or_die(parts, exec_mode=False, allow_unsafe=a.allow_unsafe, label=label)
        print(json.dumps({"platform": mod.KEY, "kind": post.kind, "media": [str(m) for m in post.media],
                          "fields": fields}, ensure_ascii=False, indent=2))
        print("dry-run：只预览，加 --exec 才会真正发布")
        return 0
    content_guard.guard_or_die(parts, exec_mode=True, allow_unsafe=a.allow_unsafe, label=label)
    login_state.write_status(sf, "starting", f"准备发布到 {mod.NAME}…")
    return run_publish(mod, post, fields, headed=a.headed, status_file=sf)


def _print_platforms() -> int:
    for m in PLATFORMS.values():
        kinds = "、".join(KIND_LABEL[k] for k in ("video", "image", "text") if k in m.KINDS)
        lim = m.LIMITS
        parts = [f"文案≤{lim.caption}{'（加权）' if lim.weighted else ''}"]
        if lim.title:
            parts.append(f"标题≤{lim.title}")
        if lim.images:
            parts.append(f"图片≤{lim.images}张")
        if lim.hashtags:
            parts.append(f"标签≤{lim.hashtags}个")
        if m.VISIBILITY:
            parts.append(f"可见范围：{'/'.join(m.VISIBILITY)}")
        print(f"{m.KEY:<10} {m.NAME:<10} {kinds}  {'，'.join(parts)}")
    return 0


def _selftest() -> int:
    problems: list[str] = []
    for key, m in PLATFORMS.items():
        missing = [a for a in REQUIRED_ATTRS if not hasattr(m, a)]
        if missing:
            problems.append(f"{key} 缺 {', '.join(missing)}")
            continue
        if m.KEY != key:
            problems.append(f"{key} 的 KEY 写成了 {m.KEY}")
        if not m.KINDS or not set(m.KINDS) <= set(KIND_LABEL):
            problems.append(f"{key} 的 KINDS 不合法：{sorted(m.KINDS)}")
        if ("image" in m.KINDS) != (m.LIMITS.images > 0):
            problems.append(f"{key} 的图文能力和图片张数上限对不上")
        if m.VISIBILITY and m.VISIBILITY_DEFAULT not in m.VISIBILITY:
            problems.append(f"{key} 的默认可见范围不在选项里")
        if not any(mk.lower() in m.LOGIN_URL.lower() for mk in m.LOGIN_MARKERS):
            problems.append(f"{key} 的登录页地址没被 LOGIN_MARKERS 识别")
        if not set(m.READY_KINDS) <= set(m.KINDS):
            problems.append(f"{key} 的 READY_KINDS 超出了 KINDS")
    if len({m.PROFILE for m in PLATFORMS.values()}) != len(PLATFORMS):
        problems.append("登录目录名有重复")
    for text, n in (("a" * 280, 280), ("中" * 140, 280), ("https://example.com/x", 23)):
        if x_weighted_length(text) != n:
            problems.append(f"X 加权计数错误：{text[:12]}…")
    if problems:
        for p in problems:
            print(f"❌ {p}")
        return 1
    print(f"✅ selftest 通过（{len(PLATFORMS)} 个平台：{', '.join(PLATFORMS)}）")
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):   # Windows GBK 控制台打印 ✅ / ❌ 会崩
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="海外平台（TikTok / YouTube / Instagram / X / Threads）登录与登录态校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("platforms", help="列出平台、支持的形式和上限")
    p = sub.add_parser("login", help="弹出 Chrome 窗口，亲手登录")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    p.add_argument("--status-file", help="登录状态 JSON（Web 账号页轮询它）")
    p.add_argument("--timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT, help="最长等多少秒（默认 600）")
    p = sub.add_parser("whoami", help="校验登录态，输出单行 JSON")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    p = sub.add_parser("publish", help="发布（默认只预览；--exec 才真发）")
    p.add_argument("--platform", required=True, choices=list(PLATFORMS))
    p.add_argument("--media", action="append", help="视频或图片路径（可重复）；不传即纯文字")
    p.add_argument("--title", help="标题（YouTube 必填，≤100）")
    p.add_argument("--desc", help="正文 / 说明")
    p.add_argument("--tags", help="话题标签，逗号或空格分隔")
    p.add_argument("--visibility", help="可见范围：YouTube public/unlisted/private；TikTok everyone/friends/only_me")
    p.add_argument("--status-file", help="发布状态 JSON（Web 发布中心轮询它）")
    p.add_argument("--headed", action="store_true", help="开窗口发布（平台要人工验证时用）")
    p.add_argument("--allow-unsafe", action="store_true", help="放行内容安全闸门（检出敏感信息也照发，谨慎）")
    p.add_argument("--exec", action="store_true", help="真正发布（默认只预览）")
    sub.add_parser("selftest", help="离线自检")
    a = ap.parse_args(argv)
    if a.cmd == "platforms":
        return _print_platforms()
    if a.cmd == "selftest":
        return _selftest()
    if a.cmd == "publish":
        return cmd_publish(a)
    if a.cmd == "login":
        return run_login(get(a.platform), a.status_file, a.timeout)
    print(json.dumps(run_whoami(get(a.platform)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
