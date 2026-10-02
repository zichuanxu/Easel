#!/usr/bin/env python3
"""human_input.py — 按真人节奏操作页面：鼠标沿曲线移过去再按下松开、按词组输入、滚轮翻页。

小红书把「瞬移到元素中心的点击 / JS 合成的 click() / 固定节奏逐字敲」当作脚本特征。这里只管
输入节奏，用的是浏览器真实的鼠标、键盘事件（isTrusted=true），不改浏览器指纹。

用法（page 是 Playwright 的 Page，target 是 Locator 或 ElementHandle）：
    human_input.click(page, target)        # 移过去 → 停一下 → 按下 → 松开
    human_input.type_text(page, "正文…")   # 中文按 1~4 字一组上屏，英文数字逐键
    human_input.scroll(page, 800)          # 滚轮往下翻 800px 左右
    human_input.pause(page, 800, 2000)     # 看一眼页面再动
"""
from __future__ import annotations

import math
import random

# 随机源单独一个，测试可以换成固定种子
rng = random.Random()

PUNCT_PAUSE = set("，。！？；：、,.!?;:")
# 点击只落在窗口里离上下边缘这么远的一段。吸底发布栏、导航条这些盖在元素上的东西靠下面的
# 命中检查（_HIT_JS）排除，所以这里不必、也不能把底部整段让出来（发布按钮本身就在吸底栏里）。
TOP_MARGIN = 8
BOTTOM_MARGIN = 8

# 点 (x,y) 时浏览器实际命中的是不是这个元素（或它里面的东西）。闭合 Shadow DOM 的宿主
# 会被重定向成宿主本身，所以也算命中。
_HIT_JS = """(el, [x, y]) => {
    const t = document.elementFromPoint(x, y);
    return !!t && (t === el || el.contains(t));
}"""


def pause(page, lo_ms: int, hi_ms: int) -> None:
    page.wait_for_timeout(rng.randint(lo_ms, hi_ms))


def _viewport(page) -> tuple[float, float]:
    try:
        vp = page.viewport_size
    except Exception:
        vp = None
    if vp:
        return float(vp["width"]), float(vp["height"])
    try:  # no_viewport=True（真窗口）时 viewport_size 是 None，读窗口实际大小
        w, h = page.evaluate("() => [window.innerWidth, window.innerHeight]")
        return float(w), float(h)
    except Exception:
        return 1280.0, 800.0


def _pos(page) -> list[float]:
    """这个页面上鼠标当前在哪（Playwright 不提供查询，自己记）。第一次用时先把鼠标放到窗口
    中间一带（Playwright 的指针起点是左上角 (0,0)，不挪的话第一次滚轮会滚到侧栏上）。"""
    st = getattr(page, "_easel_mouse", None)
    if st is None:
        w, h = _viewport(page)
        st = [w * rng.uniform(0.35, 0.65), h * rng.uniform(0.35, 0.65)]
        page.mouse.move(st[0], st[1])
        try:
            setattr(page, "_easel_mouse", st)
        except Exception:
            pass
    return st


def curve(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    """从 (x0,y0) 到 (x1,y1) 的一条弯曲轨迹：三次贝塞尔，两个控制点往同一侧偏，两头慢中间快。
    纯函数（除随机数），终点必为 (x1,y1)。"""
    dist = math.hypot(x1 - x0, y1 - y0)
    if dist < 1:
        return [(x1, y1)]
    steps = max(8, min(45, int(dist / 14)))
    nx, ny = -(y1 - y0) / dist, (x1 - x0) / dist          # 法向
    bend = dist * rng.uniform(0.08, 0.25) * rng.choice((-1, 1))
    c1 = (x0 + (x1 - x0) * rng.uniform(0.2, 0.4) + nx * bend,
          y0 + (y1 - y0) * rng.uniform(0.2, 0.4) + ny * bend)
    k = rng.uniform(0.3, 0.9)
    c2 = (x0 + (x1 - x0) * rng.uniform(0.6, 0.8) + nx * bend * k,
          y0 + (y1 - y0) * rng.uniform(0.6, 0.8) + ny * bend * k)
    pts = []
    for i in range(1, steps + 1):
        t = 0.5 - 0.5 * math.cos(math.pi * i / steps)       # 两头慢中间快
        u = 1 - t
        x = u**3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x1
        y = u**3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y1
        pts.append((x + rng.uniform(-0.8, 0.8), y + rng.uniform(-0.8, 0.8)))
    pts[-1] = (x1, y1)
    return pts


def move_to(page, x: float, y: float) -> None:
    st = _pos(page)
    for px, py in curve(st[0], st[1], x, y):
        page.mouse.move(px, py)
        page.wait_for_timeout(rng.randint(6, 16))
    st[0], st[1] = x, y


def scroll(page, dy: float) -> None:
    """用滚轮翻页：每格 80~160px，格间停一下，正数往下。"""
    _pos(page)                            # 滚轮作用在鼠标所在处，先确保鼠标在窗口里
    left = abs(dy)
    sign = 1 if dy >= 0 else -1
    while left > 0:
        step = min(left, rng.randint(80, 160))
        page.mouse.wheel(0, sign * step)
        left -= step
        page.wait_for_timeout(rng.randint(30, 110))
    page.wait_for_timeout(rng.randint(150, 400))


def _box(target):
    try:
        box = target.bounding_box()
    except Exception:
        return None
    if not box or box["width"] < 1 or box["height"] < 1:
        return None                       # 不存在 / 隐藏 / 零尺寸都当看不见
    return box


def _visible_band(box: dict, h: float) -> tuple[float, float] | None:
    """元素在可点区域 [TOP_MARGIN, h-BOTTOM_MARGIN] 里露出来的那段纵向范围；露得太少返回 None。"""
    lo = max(box["y"], TOP_MARGIN)
    hi = min(box["y"] + box["height"], h - BOTTOM_MARGIN)
    if hi - lo < min(box["height"], 12):
        return None
    return lo, hi


def _bring_into_view(page, target):
    """元素不在可点区域就用滚轮把它滚进来；比可点区域还高的元素，露出够大的一截就行。
    滚轮滚不动它（在内层滚动区）再退回 scroll_into_view。"""
    _w, h = _viewport(page)
    for _ in range(25):
        box = _box(target)
        if box is None:
            break
        if _visible_band(box, h):
            return box
        top = box["y"]
        scroll(page, top - h * rng.uniform(0.25, 0.4))
        after = _box(target)
        if after is None or abs(after["y"] - top) < 1:
            break
    try:
        target.scroll_into_view_if_needed()
    except Exception:
        pass
    return _box(target)


def _aim(page, target, x_frac: float | None) -> tuple[float, float]:
    """在元素露出来的可点区域里挑一个点，并确认浏览器在那个点上命中的就是这个元素
    （没被弹层、吸底栏盖住）。挑 6 次都不中就报错——宁可不点，也不能点到别的按钮上。"""
    box = _bring_into_view(page, target)
    if not box:
        raise RuntimeError("元素不可见，没法点")
    _w, h = _viewport(page)
    band = _visible_band(box, h)
    if not band:
        raise RuntimeError("元素不在可点区域里，没法点")
    lo, hi = band
    for _ in range(6):
        fx = (x_frac + rng.uniform(-0.015, 0.015)) if x_frac is not None else rng.uniform(0.3, 0.7)
        x = box["x"] + box["width"] * fx
        y = lo + (hi - lo) * rng.uniform(0.3, 0.7)
        try:
            hit = target.evaluate(_HIT_JS, [x, y])
        except Exception:
            hit = True                    # 查不了（元素句柄已失效等）就不拦，交给后面的步骤报错
        if hit:
            return x, y
    raise RuntimeError("要点的元素被别的东西挡住了，没有点")


def hover(page, target) -> None:
    x, y = _aim(page, target, None)
    move_to(page, x, y)


def click(page, target, x_frac: float | None = None) -> None:
    """移到元素上（默认中间一带随机一点；x_frac 指定横向比例，如宽横条右侧的按钮）→ 停顿 → 按下 → 松开。
    点之前确认那个点上命中的就是这个元素，挡住了就报错不点。"""
    x, y = _aim(page, target, x_frac)
    move_to(page, x, y)
    page.wait_for_timeout(rng.randint(60, 220))
    page.mouse.down()
    page.wait_for_timeout(rng.randint(50, 140))
    page.mouse.up()


def chunks(text: str) -> list[str]:
    """把文字切成真人输入的节奏：换行单独一段；ASCII 逐字符；中文等 1~4 字一组（输入法一次上屏一个词）。
    拼回去等于原文。"""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n" or ord(ch) < 128:
            out.append(ch)
            i += 1
            continue
        n = rng.randint(1, 4)
        j = i
        while j < len(text) and j - i < n and text[j] != "\n" and ord(text[j]) >= 128:
            j += 1
        out.append(text[i:j])
        i = j
    return out


def type_text(page, text: str) -> None:
    """在当前焦点处输入。换行按回车；英文数字逐键；中文按词组上屏；标点后、偶尔停下想一想。"""
    for piece in chunks(text):
        if piece == "\n":
            page.keyboard.press("Enter")
            page.wait_for_timeout(rng.randint(150, 500))
            continue
        if ord(piece[0]) < 128:
            page.keyboard.type(piece)
            page.wait_for_timeout(rng.randint(45, 160))
        else:
            page.keyboard.insert_text(piece)
            page.wait_for_timeout(rng.randint(140, 420))
        if piece[-1] in PUNCT_PAUSE:
            page.wait_for_timeout(rng.randint(200, 650))
        elif rng.random() < 0.04:
            page.wait_for_timeout(rng.randint(700, 1800))
