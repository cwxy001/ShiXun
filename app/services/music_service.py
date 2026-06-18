# 音乐查询服务 — iTunes Search API (免费，无需 Key)

import json
import urllib.request
import urllib.parse


def search_music(query: str, limit: int = 8) -> dict:
    """
    通过 iTunes API 搜索音乐。
    返回: {"results": [...], "query": ..., "result_count": ...}
    """
    try:
        term = urllib.parse.quote(query)
        url = f"https://itunes.apple.com/search?term={term}&media=music&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "IOIQ/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        items = []
        for r in data.get("results", []):
            items.append({
                "track_name": r.get("trackName", ""),
                "artist_name": r.get("artistName", ""),
                "collection_name": r.get("collectionName", ""),
                "track_view_url": r.get("trackViewUrl", ""),
                "artwork_url": r.get("artworkUrl100", "").replace("100x100", "300x300"),
                "preview_url": r.get("previewUrl", ""),
                "primary_genre": r.get("primaryGenreName", ""),
                "release_date": r.get("releaseDate", ""),
                "track_price": r.get("trackPrice"),
                "currency": r.get("currency", ""),
                "track_time_ms": r.get("trackTimeMillis", 0),
            })
        return {
            "results": items,
            "query": query,
            "result_count": len(items),
            "source": "iTunes",
        }
    except urllib.error.URLError as e:
        return {"error": f"音乐服务请求失败：{str(e.reason)}", "query": query, "results": []}
    except Exception as e:
        return {"error": f"音乐数据解析失败：{str(e)}", "query": query, "results": []}


def search_artist(query: str) -> dict:
    """搜索歌手信息"""
    try:
        term = urllib.parse.quote(query)
        url = f"https://itunes.apple.com/search?term={term}&entity=musicArtist&limit=5"
        req = urllib.request.Request(url, headers={"User-Agent": "IOIQ/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        items = []
        for r in data.get("results", []):
            items.append({
                "artist_name": r.get("artistName", ""),
                "artist_link": r.get("artistLinkUrl", ""),
                "primary_genre": r.get("primaryGenreName", ""),
            })
        return {"results": items, "query": query, "result_count": len(items)}
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}
