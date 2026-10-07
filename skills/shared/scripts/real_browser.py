#!/usr/bin/env python3
"""real_browser.py — 可复用的「可见真实浏览器」启动器（从 xhs_publish.py 抽出）。

国内平台（小红书/抖音/视频号/快手/知乎）一律走半自动：开一个人能看见、能操作的真实窗口，
脚本填好表单后停在发布按钮前，由用户亲自点击（见 semi_auto.py）。本模块只负责「开浏览器」：

  内核优先级：CloakBrowser（每个账号一套固定指纹）→ 本机正式版 Chrome / Edge → Playwright 自带 Chromium（告警）。
  默认一律开窗口；只有 headless_env 指定的环境变量为真时才允许无头。

用法（每个平台各自一套登录目录 + 指纹文件，互不串）::

    import real_browser
    ctx = real_browser.launch(
        p, profile_dir=Path("~/.easel-browser-profiles/DouyinProfile").expanduser(),
        headed=True, proxy=None, platform_label="抖音",
        headless_env="EASEL_DOUYIN_HEADLESS", browser_env="EASEL_DOUYIN_BROWSER",
    )

约定（xhs 已依赖，不得改）：
  - 指纹文件 `<profile_dir>/.easel-fingerprint.json`，seed 只生成一次、永不重新生成（除非平台身份与本机不符）；
  - Cloak 数据目录 `<profile_dir>/cloak-browser/`，与 Chrome 数据分开。

纯 stdlib（playwright 由调用方传入 p）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 启动参数尽量少：--no-sandbox / --disable-gpu 这类是无头脚本的标配，正式版 Chrome 带上还会弹
# 「不受支持的命令行标记」提示条。--enable-automation 是 Playwright 默认加的，会亮「Chrome 正受到
# 自动测试软件的控制」并打开自动化模式，单独去掉（IGNORE_DEFAULT_ARGS）。
LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run", "--no-default-browser-check",
]
IGNORE_DEFAULT_ARGS = ["--enable-automation"]
# Cloak 另外要去掉 --enable-unsafe-swiftshader（软件渲染 WebGL，显卡串是真机不会有的）。同 cloakbrowser 包装库。
CLOAK_IGNORE_DEFAULT_ARGS = IGNORE_DEFAULT_ARGS + ["--enable-unsafe-swiftshader"]
# Cloak 的浏览器数据放在登录目录下单独一个子目录：Cloak 内核版本（如 145）比 Chrome 旧，旧内核打不开
# 新版本写过的数据目录；两种内核的指纹也不同，混用同一份登录态像同一个号在两台设备间来回切。
CLOAK_DATA_DIR = "cloak-browser"
FINGERPRINT_FILE = ".easel-fingerprint.json"


def env_true(name: str | None) -> bool:
    """环境变量是否为真（1/true/yes/on）。name 为空恒为 False。"""
    return bool(name) and (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def allow_headless(headless_env: str | None) -> bool:
    """允许无头吗：仅当 headless_env 指定的环境变量为真（只给没有桌面的机器用，很容易被识别成脚本）。"""
    return env_true(headless_env)


def cloak_executable() -> Path | None:
    """本机已装的 CloakBrowser 内核（`pip install cloakbrowser && python -m cloakbrowser install`
    装到 ~/.cloakbrowser，CLOAKBROWSER_CACHE_DIR 可改）。有多个版本取最新装的。
    EASEL_CLOAK_BROWSER 直接指定可执行文件。"""
    override = (os.environ.get("EASEL_CLOAK_BROWSER") or "").strip()
    if override:
        p = Path(override).expanduser()
        return p if p.is_file() else None
    root = Path(os.environ.get("CLOAKBROWSER_CACHE_DIR") or (Path.home() / ".cloakbrowser")).expanduser()
    if not root.is_dir():
        return None
    if sys.platform == "darwin":
        pattern = "chromium-*/Chromium.app/Contents/MacOS/Chromium"
    elif os.name == "nt":
        pattern = "chromium-*/chrome.exe"
    else:
        pattern = "chromium-*/chrome"
    choices = sorted((c for c in root.glob(pattern) if c.is_file()),
                     key=lambda c: c.stat().st_mtime, reverse=True)
    return choices[0] if choices else None


def browser_channel() -> str | None:
    """本机装的正式版浏览器：Chrome 优先，其次 Edge；都没有返回 None。"""
    if sys.platform == "darwin":
        for app, channel in (("Google Chrome.app", "chrome"), ("Microsoft Edge.app", "msedge")):
            if any((d / app).is_dir() for d in (Path("/Applications"), Path.home() / "Applications")):
                return channel
        return None
    if os.name != "nt":
        import shutil
        if shutil.which("google-chrome") or shutil.which("google-chrome-stable"):
            return "chrome"
        if shutil.which("microsoft-edge") or shutil.which("microsoft-edge-stable"):
            return "msedge"
        return None
    pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    chrome = (
        pf / "Google" / "Chrome" / "Application" / "chrome.exe",
        pf86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
    )
    if any(p.is_file() for p in chrome):
        return "chrome"
    edge = (
        pf / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        pf86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    )
    if any(p.is_file() for p in edge):
        return "msedge"
    return None


def host_fingerprint_platform() -> str:
    """Cloak 指纹的平台身份：Mac 上就是 macOS（和真机字体、显卡一致）；其它系统用 Cloak 默认的 Windows。"""
    return "macos" if sys.platform == "darwin" else "windows"


def read_fingerprint(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(d, dict) and isinstance(d.get("seed"), int) and 10000 <= d["seed"] <= 99999
            and d.get("platform") in ("macos", "windows")):
        return d
    return None


def account_fingerprint(profile_dir: Path, *, fingerprint_file: str = FINGERPRINT_FILE,
                        platform_label: str = "", host_fn=None) -> dict:
    """这个账号固定用的 Cloak 指纹（seed + 平台），存在登录目录里；第一次用时生成。
    指纹固定 = 每次打开都像同一台设备；Cloak 默认每次启动随机换一套，对同一个号反而可疑。
    平台和本机对不上（登录目录从别的系统拷过来）就重新生成——Mac 上顶着 Windows 指纹，字体/显卡会露馅。
    并发安全：新文件用硬链接原子落盘，两个进程同时第一次打开时只有一个的 seed 生效，另一个读它的。
    host_fn：返回本机平台身份的函数（默认 host_fingerprint_platform，xhs 用它注入自己的可 patch 版本）。"""
    import secrets
    path = Path(profile_dir) / fingerprint_file
    path.parent.mkdir(parents=True, exist_ok=True)
    host = (host_fn or host_fingerprint_platform)()
    for _ in range(5):
        cur = read_fingerprint(path)
        if cur and cur["platform"] == host:
            return cur
        if cur:
            print(f"⚠️ 登录目录里的指纹是 {cur['platform']} 身份，和本机不符，重新生成一套 {host} 指纹",
                  file=sys.stderr)
        d = {"seed": 10000 + secrets.randbelow(90000), "platform": host,
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        tmp = path.with_name(f"{fingerprint_file}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
        tmp.write_text(json.dumps(d), encoding="utf-8")
        try:
            if path.exists():
                os.replace(tmp, path)          # 坏文件 / 平台不符：直接覆盖
            else:
                try:
                    os.link(tmp, path)         # 不存在：原子创建，别人抢先了就读别人的
                except FileExistsError:
                    time.sleep(0.2)
                    continue
                except OSError:
                    os.replace(tmp, path)      # 不支持硬链接的文件系统
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        print(f"已为这个{platform_label or ''}账号生成固定指纹（{host} 身份），之后每次都用它：{path}",
              file=sys.stderr)
        return d
    raise RuntimeError(f"读写指纹文件失败：{path}")


def resolve_engine(browser_env: str | None = None, *, cloak_fn=None, channel_fn=None) -> tuple[str, str]:
    """实际会用哪个浏览器：("cloak", 可执行文件) / ("chrome"|"msedge", "") / ("bundled", "")。
    browser_env 指定的环境变量 =chrome 时跳过 Cloak 直接用本机 Chrome；默认 auto（Cloak 优先）。
    cloak_fn / channel_fn 可注入（xhs 用以保留模块级可 patch 的入口）。"""
    choice = ((os.environ.get(browser_env) if browser_env else "") or "auto").strip().lower()
    if choice != "chrome":
        cloak = (cloak_fn or cloak_executable)()
        if cloak:
            return "cloak", str(cloak)
    channel = (channel_fn or browser_channel)()
    return (channel, "") if channel else ("bundled", "")


def clear_stale_chrome_locks(profile: Path) -> None:
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        try:
            (profile / name).unlink()
        except OSError:
            pass


def launch(p, *, profile_dir: Path, headed: bool, proxy: str | None = None,
           fingerprint_file: str = FINGERPRINT_FILE, platform_label: str = "",
           headless_env: str | None = None, browser_env: str | None = None,
           engine: tuple[str, str] | None = None, fingerprint_fn=None,
           chrome_hint: str = "") -> object:
    """开平台用的浏览器（persistent context）。默认一律开窗口（headed 参数只在允许无头时才有意义）；
    内核优先 CloakBrowser（账号固定指纹、数据在登录目录的 cloak-browser/ 子目录），
    其次本机正式版 Chrome / Edge，最后才是 Playwright 自带的 Chromium。

    profile_dir：该平台账号的登录目录（如 .../XiaohongshuProfile）；指纹文件、Cloak 数据目录都在它下面。
    engine：预先算好的 resolve_engine() 结果（不传则现算）。
    fingerprint_fn：无参函数，返回账号指纹 dict（不传则用 account_fingerprint(profile_dir, ...)）。
    """
    account = Path(profile_dir)
    account.mkdir(parents=True, exist_ok=True)
    headless = not headed and allow_headless(headless_env)
    engine_name, cloak = engine or resolve_engine(browser_env)
    label = platform_label or "该平台"
    if engine_name == "cloak":
        fp = (fingerprint_fn or (lambda: account_fingerprint(
            account, fingerprint_file=fingerprint_file, platform_label=platform_label)))()
        profile = account / CLOAK_DATA_DIR
        if not profile.exists() and (account / "Default").is_dir():
            print(f"ℹ️ 第一次用 CloakBrowser 打开这个账号：之前的登录在 Chrome 的数据里，"
                  f"Cloak 里要重新扫码登录一次（{chrome_hint or '对应平台的登录命令'}）", file=sys.stderr)
        profile.mkdir(parents=True, exist_ok=True)
        # 同 cloakbrowser 包装库：指纹、语言都用内核开关，不用 Playwright 的 locale 模拟（那是 CDP 注入）
        args = ["--no-first-run", "--no-default-browser-check",
                f"--fingerprint={fp['seed']}", f"--fingerprint-platform={fp['platform']}",
                "--lang=zh-CN", "--fingerprint-locale=zh-CN"]
        if not headless:
            args.append("--ignore-gpu-blocklist")
        if sys.platform.startswith("linux"):
            args.append("--no-sandbox")    # 同包装库：容器 / 关了 user namespace 的发行版上沙箱起不来
        kwargs = dict(headless=headless, args=args, executable_path=cloak,
                      ignore_default_args=list(CLOAK_IGNORE_DEFAULT_ARGS))
    else:
        profile = account
        args = list(LAUNCH_ARGS)
        kwargs = dict(headless=headless,
                      locale="zh-CN",
                      args=args,
                      ignore_default_args=list(IGNORE_DEFAULT_ARGS))
    if not headless:
        kwargs["no_viewport"] = True   # 用真实窗口大小，不让页面尺寸和窗口对不上
    if (sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0
            and "--no-sandbox" not in args):
        args.append("--no-sandbox")    # root 下 Chromium 不开沙箱起不来
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    else:
        # 显式直连：Chromium 级屏蔽系统/环境代理（开 VPN 也能用）
        args.append("--no-proxy-server")
    if engine_name in ("chrome", "msedge"):
        kwargs["channel"] = engine_name
    elif engine_name == "bundled":
        print(f"⚠️ 没找到 CloakBrowser 和本机 Chrome / Edge，改用 Playwright 自带的 Chromium，"
              f"更容易被{label}识别成脚本。建议安装 CloakBrowser 或 Google Chrome。", file=sys.stderr)
    last: Exception | None = None
    for attempt in range(2):
        try:
            return p.chromium.launch_persistent_context(str(profile), **kwargs)
        except Exception as e:
            last = e
            if attempt == 0 and "TargetClosed" in type(e).__name__:
                time.sleep(1.2)
                clear_stale_chrome_locks(profile)
                continue
            raise
    raise last  # pragma: no cover


# --------------------------------------------------------------------------- #
# 国内平台注册表：登录目录名 / 指纹文件 / 环境变量名 / 中文名。
# 发布脚本（xhs_publish / douyin_publish / web_publisher）与读数据脚本（account_stats /
# zhihu_comments_fetch）必须用同一套引擎 + 同一份登录目录，否则读数据时看不到发布时的登录态。
# 值必须与各发布脚本里的 PROFILE_NAME / PLATFORMS[...]["profile"] / 环境变量名逐一一致
# （tests/test_real_browser.py 有一致性断言）。
# --------------------------------------------------------------------------- #
PLATFORMS: dict[str, dict] = {
    "xiaohongshu": {"profile": "XiaohongshuProfile", "label": "小红书",
                    "headless_env": "EASEL_XHS_HEADLESS", "browser_env": "EASEL_XHS_BROWSER",
                    "fingerprint_file": FINGERPRINT_FILE},
    "douyin": {"profile": "DouyinProfile", "label": "抖音",
               "headless_env": "EASEL_DOUYIN_HEADLESS", "browser_env": "EASEL_DOUYIN_BROWSER",
               "fingerprint_file": FINGERPRINT_FILE},
    "kuaishou": {"profile": "KuaishouProfile", "label": "快手",
                 "headless_env": "EASEL_KUAISHOU_HEADLESS", "browser_env": "EASEL_KUAISHOU_BROWSER",
                 "fingerprint_file": FINGERPRINT_FILE},
    "weixin-channels": {"profile": "ChannelsProfile", "label": "微信视频号",
                        "headless_env": "EASEL_CHANNELS_HEADLESS", "browser_env": "EASEL_CHANNELS_BROWSER",
                        "fingerprint_file": FINGERPRINT_FILE},
    "zhihu": {"profile": "ZhihuProfile", "label": "知乎",
              "headless_env": "EASEL_ZHIHU_HEADLESS", "browser_env": "EASEL_ZHIHU_BROWSER",
              "fingerprint_file": FINGERPRINT_FILE},
}


def platform_profile_dir(platform: str, base: str | None = None) -> Path:
    """该平台账号的登录目录（~/.easel-browser-profiles/<XxxProfile>，base 可覆盖根目录）。"""
    root = Path(base).expanduser() if base else Path.home() / ".easel-browser-profiles"
    return root / PLATFORMS[platform]["profile"]


def launch_platform(p, platform: str, *, headed: bool = True, proxy: str | None = None,
                    base: str | None = None, headless_env: str | None = None, **kw) -> object:
    """按注册表开某国内平台的浏览器：与该平台发布脚本同引擎、同登录目录、同指纹、同环境变量。
    headed=False 只有该平台的 *_HEADLESS 环境变量为真时才真无头，否则一律开窗口。"""
    cfg = PLATFORMS[platform]
    return launch(
        p, profile_dir=platform_profile_dir(platform, base), headed=headed, proxy=proxy,
        fingerprint_file=cfg["fingerprint_file"], platform_label=cfg["label"],
        headless_env=headless_env or cfg["headless_env"], browser_env=cfg["browser_env"],
        chrome_hint=kw.pop("chrome_hint", f"对应平台的登录命令（{cfg['label']}）"), **kw)
