"""创作数据抓取的等待逻辑：轮询提取结果本身、拿到就走，不再白等选择器超时。不启动真实浏览器。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "shared" / "scripts"))

import account_stats as A  # noqa: E402
import weixin_mp_stats as W  # noqa: E402


class FakePage:
    """按序列返回 evaluate 结果（用完停在最后一个），记录累计等待毫秒。"""

    def __init__(self, seq=None, urls=None):
        self.seq = list(seq or [[]])
        self.urls = list(urls or [""])
        self.waited = 0

    def evaluate(self, _js):
        item = self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def url(self):
        return self.urls.pop(0) if len(self.urls) > 1 else self.urls[0]

    def wait_for_timeout(self, ms):
        self.waited += ms


def test_poll_extract_returns_as_soon_as_list_is_stable():
    one = [{"title": "a"}]
    page = FakePage([[], [], one, one, one + [{"title": "b"}]])
    assert A._poll_extract(page, "js", max_ms=8000, step=300) == one
    assert page.waited == 900   # 空、空、有、同 → 第 4 次读到相同即返回，只等了 3 步


def test_poll_extract_gives_up_at_max_and_returns_last_result():
    page = FakePage([[]])
    assert A._poll_extract(page, "js", max_ms=1000, step=300) == []
    assert page.waited <= 1200


def test_poll_extract_treats_evaluate_errors_as_empty():
    one = [{"title": "a"}]
    page = FakePage([RuntimeError("navigating"), one, one])
    assert A._poll_extract(page, "js", max_ms=3000, step=300) == one


def test_wait_token_returns_once_redirect_lands():
    page = FakePage(urls=["https://mp.weixin.qq.com/", "https://mp.weixin.qq.com/",
                          "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&token=12345&lang=zh_CN"])
    assert W._wait_token(page, max_ms=4000, step=200) == "12345"
    assert page.waited == 400


def test_wait_token_times_out_to_empty_when_not_logged_in():
    page = FakePage(urls=["https://mp.weixin.qq.com/"])
    assert W._wait_token(page, max_ms=1000, step=200) == ""
    assert page.waited <= 1200
