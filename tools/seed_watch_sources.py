"""添加更多瞭望采集数据源"""
import sys; sys.path.insert(0, '.')
from app.models.db import get_connection

sources = [
    ("百度新闻搜索", "https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&rsv_dl=ns_pc&word={关键词}&pn={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
    ("百度网页搜索", "https://www.baidu.com/s?wd={关键词}&pn={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
    ("搜狗搜索", "https://www.sogou.com/web?query={关键词}&page={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
    ("360搜索", "https://www.so.com/s?q={关键词}&pn={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
    ("Bing搜索", "https://www.bing.com/search?q={关键词}&first={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
    ("搜狗微信搜索", "https://weixin.sogou.com/weixin?type=2&query={关键词}&page={pn}",
     "GET", '{"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}', 1),
]

c = get_connection()
added = 0
for name, url_tpl, method, headers, pagination in sources:
    existing = c.execute("SELECT id FROM watch_sources WHERE url_template = ?", (url_tpl,)).fetchone()
    if not existing:
        c.execute(
            "INSERT INTO watch_sources (name, url_template, method, headers, enable_pagination) VALUES (?,?,?,?,?)",
            (name, url_tpl, method, headers, pagination)
        )
        added += 1

c.commit()

total = c.execute("SELECT COUNT(*) FROM watch_sources").fetchone()[0]
print(f"新增 {added} 个数据源，当前共 {total} 个")
rows = c.execute("SELECT id, name FROM watch_sources").fetchall()
for r in rows:
    print(f"  [{r['id']}] {r['name']}")
