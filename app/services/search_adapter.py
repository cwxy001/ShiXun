# 搜索适配器 — 百度 + DuckDuckGo 多源搜索

import urllib.request
import urllib.parse
import re
import html
import ssl
import gzip
from io import BytesIO


def web_search_raw(query: str, num: int = 5) -> list:
    """
    多源网络搜索，返回标准化结果列表。
    
    回退策略：百度 → DuckDuckGo → 空
    返回: [{"title": ..., "url": ..., "snippet": ...}, ...]
    """
    results = []

    # 方案1: 百度搜索（中文支持最好）
    try:
        results = _search_baidu(query, num)
        if results:
            return results
    except Exception:
        pass

    # 方案2: DuckDuckGo Lite
    try:
        results = _search_ddg_lite(query, num)
        if results:
            return results
    except Exception:
        pass

    return []


def _fetch_url(url: str, timeout: int = 10) -> str:
    """统一 HTTP 请求，支持 gzip、重定向"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
    )

    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read()
        # 自动解压 gzip
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.GzipFile(fileobj=BytesIO(raw)).read()
        # 尝试从响应头获取编码
        content_type = resp.headers.get("Content-Type", "")
        charset_match = re.search(r'charset=([\w-]+)', content_type)
        encoding = charset_match.group(1) if charset_match else "utf-8"
        return raw.decode(encoding, errors="replace")


def _search_baidu(query: str, num: int) -> list:
    """百度搜索"""
    encoded = urllib.parse.quote(query)
    url = f"https://www.baidu.com/s?wd={encoded}&rn={num * 2}"

    body = _fetch_url(url, timeout=10)

    items = []
    # 百度搜索结果格式：
    # <h3 class="t"><a href="URL" ...>Title</a></h3>
    # <div class="c-abstract">Snippet</div>
    # 或新版格式：
    # <h3 class="c-title"><a href="URL" ...>Title</a></h3>
    # <div class="c-abstract">...</div>

    # 匹配标题块
    h3_pattern = re.compile(
        r'<h3[^>]*class="[^"]*(?:t|c-title)[^"]*"[^>]*>'
        r'.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>'
        r'.*?</h3>',
        re.IGNORECASE | re.DOTALL
    )

    # 匹配摘要
    abstract_pattern = re.compile(
        r'<(?:span|div)[^>]*class="[^"]*(?:c-abstract|content-right_[^"]*|c-span-last)[^"]*"[^>]*>(.*?)</(?:span|div)>',
        re.IGNORECASE | re.DOTALL
    )

    h3_matches = list(h3_pattern.finditer(body))

    for m in h3_matches[:num]:
        url_str = m.group(1)
        title = html.unescape(re.sub(r'<[^>]+>', '', m.group(2)).strip())

        # 跳过非 http 链接和空标题
        if not title or not url_str.startswith("http"):
            continue

        # 在 h3 之后找第一个摘要
        snippet_start = m.end()
        snippet_match = abstract_pattern.search(body, snippet_start)
        snippet = ""
        if snippet_match:
            snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip())

        items.append({"title": title, "url": url_str, "snippet": snippet})

    return items


def _search_ddg_lite(query: str, num: int) -> list:
    """DuckDuckGo Lite 备用搜索"""
    encoded = urllib.parse.quote(query)
    url = f"https://lite.duckduckgo.com/lite/?q={encoded}"

    body = _fetch_url(url, timeout=10)

    items = []

    row_pattern = re.compile(
        r'<a\s+[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>'
        r'.*?<span\s+class=["\']result-snippet["\'][^>]*>(.*?)</span>',
        re.IGNORECASE | re.DOTALL
    )

    for m in row_pattern.finditer(body):
        url_str = m.group(1)
        title = html.unescape(m.group(2).strip())
        snippet = html.unescape(re.sub(r'<[^>]+>', '', m.group(3)).strip())
        if not title or not url_str.startswith("http"):
            continue
        items.append({"title": title, "url": url_str, "snippet": snippet})
        if len(items) >= num:
            break

    return items
