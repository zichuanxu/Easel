"""海外平台发布的内容模型：Post、平台上限、文案拼接与校验。

纯函数、不碰浏览器：overseas_publisher 在开浏览器之前就用它把不合格的内容挡掉。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTS = frozenset({".mp4", ".mov", ".m4v", ".webm"})
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
KIND_LABEL = {"video": "视频", "image": "图文", "text": "纯文字"}

# X 的加权计数（twitter-text v3）：这些码位区间算 1，其余（中日韩文字、emoji 等）算 2；URL 一律算 23
_X_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
_X_URL_WEIGHT = 23
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
# 行尾是话题 / @：打字时补一个空格把联想框收掉（见 PageDriver.type_text），校验字数时也要算上
TAG_AT_LINE_END = re.compile(r"[#@][^\s#@]+$")


class PostError(ValueError):
    """内容不合格（开浏览器之前就退出）。"""


@dataclass(frozen=True)
class Limits:
    caption: int              # 主文案上限（YouTube 是描述）
    title: int = 0            # 独立标题上限；0 = 平台没有独立标题，标题并进主文案
    hashtags: int = 0         # 话题标签个数上限；0 = 不限
    images: int = 0           # 图文最多几张；0 = 不支持图文
    weighted: bool = False    # True = 按 X 的加权规则计数


@dataclass
class Post:
    media: list[Path] = field(default_factory=list)
    title: str = ""
    desc: str = ""
    tags: str = ""
    visibility: str = ""

    @property
    def kind(self) -> str:
        return infer_kind(self.media)


def infer_kind(media) -> str:
    """无媒体 = 纯文字；1 个视频 = 视频；1～N 张图 = 图文；其它组合报错。"""
    if not media:
        return "text"
    exts = {Path(m).suffix.lower() for m in media}
    if exts <= VIDEO_EXTS:
        if len(media) != 1:
            raise PostError("视频一次只能发 1 个")
        return "video"
    if exts <= IMAGE_EXTS:
        return "image"
    raise PostError("媒体只能是 1 个视频（mp4/mov/m4v/webm），或 1～N 张图片（jpg/png/webp），不能混用")


def parse_tags(raw: str) -> list[str]:
    """逗号 / 空格分隔的话题标签 → 加 # 并去重（不分大小写，保留第一次出现的写法和顺序）。"""
    out: list[str] = []
    seen: set[str] = set()
    for t in re.split(r"[,，\s]+", raw or ""):
        t = t.strip().lstrip("#")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(f"#{t}")
    return out


def caption_text(post: Post, *, with_title: bool = True) -> str:
    """标题 + 正文 + 话题标签，空的部分跳过，段落之间空一行。"""
    parts = [post.title.strip() if with_title else "", post.desc.strip(), " ".join(parse_tags(post.tags))]
    return "\n\n".join(p for p in parts if p)


def typed_extra(text: str) -> int:
    """打字时额外补进去的空格数：每个以话题 / @ 结尾的行一个。"""
    return sum(1 for line in text.split("\n") if TAG_AT_LINE_END.search(line))


def _x_char_weight(ch: str) -> int:
    cp = ord(ch)
    return 1 if any(lo <= cp <= hi for lo, hi in _X_LIGHT_RANGES) else 2


def x_weighted_length(text: str) -> int:
    n, pos = 0, 0
    for m in _URL_RE.finditer(text):
        n += sum(_x_char_weight(c) for c in text[pos:m.start()]) + _X_URL_WEIGHT
        pos = m.end()
    return n + sum(_x_char_weight(c) for c in text[pos:])


def check_media(media) -> None:
    """文件要存在，且按真实路径（解开符号链接）看是图片或视频：x.png 链到 .env 一类文件时拒绝上传。"""
    for m in media:
        p = Path(m).expanduser()
        if not p.is_file():
            raise PostError(f"媒体文件不存在：{m}")
        real = p.resolve()
        if real.suffix.lower() not in VIDEO_EXTS | IMAGE_EXTS:
            raise PostError(f"媒体文件实际指向 {real.name}，不是图片或视频")


def validate(post: Post, *, name: str, kinds, limits: Limits, visibility: tuple[str, ...] = ()) -> None:
    """按平台的形式、上限和可见范围选项校验；不合格抛 PostError，消息直接给用户看。"""
    kind = post.kind
    if kind not in kinds:
        raise PostError(f"{name} 不支持发{KIND_LABEL[kind]}")
    check_media(post.media)
    if kind == "image" and len(post.media) > limits.images:
        raise PostError(f"{name} 图文最多 {limits.images} 张，当前 {len(post.media)} 张")
    if limits.title:
        title = post.title.strip()
        if not title:
            raise PostError(f"{name} 需要标题")
        if len(title) > limits.title:
            raise PostError(f"{name} 标题最多 {limits.title} 个字符，当前 {len(title)}")
        body = caption_text(post, with_title=False)
    else:
        body = caption_text(post)
    if kind == "text" and not body:
        raise PostError("纯文字帖子不能为空")
    n = (x_weighted_length(body) if limits.weighted else len(body)) + typed_extra(body)
    if n > limits.caption:
        unit = "（加权，中日韩文字算 2）" if limits.weighted else ""
        raise PostError(f"{name} 文案最多 {limits.caption} 个字符{unit}，当前 {n}")
    tags = parse_tags(post.tags)
    if limits.hashtags and len(tags) > limits.hashtags:
        raise PostError(f"{name} 话题标签最多 {limits.hashtags} 个，当前 {len(tags)} 个")
    if post.visibility:
        if not visibility:
            raise PostError(f"{name} 没有可见范围选项，不要传 --visibility")
        if post.visibility not in visibility:
            raise PostError(f"{name} 的可见范围只能是：{', '.join(visibility)}")
