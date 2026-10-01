"""海外发布内容模型（overseas/post.py）的离线测试：形式推断、话题标签、文案拼接、字数、媒体校验。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "shared" / "scripts"))

from overseas import post as P  # noqa: E402

LIM = P.Limits(caption=20, images=2, hashtags=2)


def _media(tmp_path, *names):
    out = []
    for n in names:
        f = tmp_path / n
        f.write_bytes(b"x")
        out.append(f)
    return out


def test_infer_kind():
    assert P.infer_kind([]) == "text"
    assert P.infer_kind([Path("a.MP4")]) == "video"
    assert P.infer_kind([Path("a.jpg"), Path("b.webp")]) == "image"


@pytest.mark.parametrize("media", [
    [Path("a.mp4"), Path("b.mp4")],
    [Path("a.mp4"), Path("b.jpg")],
    [Path("a.gif")],
    [Path("a.txt")],
])
def test_infer_kind_rejects_bad_mixes(media):
    with pytest.raises(P.PostError):
        P.infer_kind(media)


def test_parse_tags_prefixes_and_dedupes_case_insensitively():
    assert P.parse_tags("#Easel, easel  AI，shorts #ai") == ["#Easel", "#AI", "#shorts"]
    assert P.parse_tags("") == []


def test_caption_text_joins_nonempty_parts():
    post = P.Post(title="Title", desc="Body", tags="a b")
    assert P.caption_text(post) == "Title\n\nBody\n\n#a #b"
    assert P.caption_text(post, with_title=False) == "Body\n\n#a #b"
    assert P.caption_text(P.Post(title="Only")) == "Only"


@pytest.mark.parametrize("text,expected", [
    ("a" * 280, 280),
    ("中" * 140, 280),
    ("日本語", 6),
    ("see https://example.com/a/very/long/path?x=1 ok", 4 + 23 + 3),
    ("😀", 2),
])
def test_x_weighted_length(text, expected):
    assert P.x_weighted_length(text) == expected


def test_validate_ok(tmp_path):
    P.validate(P.Post(media=_media(tmp_path, "a.jpg"), title="hi", tags="a"),
               name="Demo", kinds={"image"}, limits=LIM)


def test_validate_kind_not_supported(tmp_path):
    with pytest.raises(P.PostError, match="Demo 不支持发视频"):
        P.validate(P.Post(media=_media(tmp_path, "a.mp4"), title="hi"),
                   name="Demo", kinds={"image"}, limits=LIM)


def test_validate_too_many_images(tmp_path):
    with pytest.raises(P.PostError, match="最多 2 张"):
        P.validate(P.Post(media=_media(tmp_path, "a.jpg", "b.jpg", "c.jpg")),
                   name="Demo", kinds={"image"}, limits=LIM)


def test_validate_caption_too_long():
    with pytest.raises(P.PostError, match="最多 20"):
        P.validate(P.Post(title="x" * 21), name="Demo", kinds={"text"}, limits=LIM)


def test_validate_weighted_caption():
    lim = P.Limits(caption=10, weighted=True)
    P.validate(P.Post(title="中" * 5), name="X", kinds={"text"}, limits=lim)
    with pytest.raises(P.PostError, match="加权"):
        P.validate(P.Post(title="中" * 6), name="X", kinds={"text"}, limits=lim)


def test_validate_hashtag_limit():
    with pytest.raises(P.PostError, match="话题标签最多 2 个"):
        P.validate(P.Post(title="t", tags="a b c"), name="Demo", kinds={"text"}, limits=LIM)


def test_validate_title_rules():
    lim = P.Limits(caption=50, title=5)
    with pytest.raises(P.PostError, match="需要标题"):
        P.validate(P.Post(desc="d"), name="YT", kinds={"text"}, limits=lim)
    with pytest.raises(P.PostError, match="标题最多 5"):
        P.validate(P.Post(title="123456"), name="YT", kinds={"text"}, limits=lim)


def test_validate_empty_text_post():
    with pytest.raises(P.PostError, match="不能为空"):
        P.validate(P.Post(), name="X", kinds={"text"}, limits=LIM)


def test_validate_visibility():
    P.validate(P.Post(title="t", visibility="private"), name="YT", kinds={"text"}, limits=LIM,
               visibility=("public", "private"))
    with pytest.raises(P.PostError, match="只能是"):
        P.validate(P.Post(title="t", visibility="secret"), name="YT", kinds={"text"}, limits=LIM,
                   visibility=("public",))
    with pytest.raises(P.PostError, match="没有可见范围"):
        P.validate(P.Post(title="t", visibility="public"), name="IG", kinds={"text"}, limits=LIM)


def test_check_media_missing_file(tmp_path):
    with pytest.raises(P.PostError, match="不存在"):
        P.check_media([tmp_path / "nope.mp4"])


def test_check_media_symlink_to_non_media(tmp_path):
    secret = tmp_path / "secrets.env"
    secret.write_text("TOKEN=abc", encoding="utf-8")
    link = tmp_path / "x.png"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("本机不允许建符号链接（Windows 非开发者模式）")
    with pytest.raises(P.PostError, match="不是图片或视频"):
        P.check_media([link])


def test_typed_extra_counts_lines_ending_in_tag_or_mention():
    assert P.typed_extra("Hello #ai\nworld") == 1
    assert P.typed_extra("Hello\n\n#ai #tech") == 1
    assert P.typed_extra("ping @bob\n#x\nend") == 2
    assert P.typed_extra("no tags here") == 0


def test_validate_counts_space_typed_after_trailing_tag():
    """打字时以话题结尾的行会补一个空格收联想框：X 卡在 280 的文案要提前报超限（Review Focus 2）。"""
    text = "a" * 276 + " #ai"            # 280
    with pytest.raises(P.PostError, match="280"):
        P.validate(P.Post(desc=text), name="X", kinds={"text"}, limits=P.Limits(caption=280, weighted=True))

