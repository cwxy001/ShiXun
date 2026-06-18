# 天气查询服务 — Open-Meteo (免费，无需 API Key)

import json
import urllib.request
import urllib.parse
from datetime import datetime

# 中文地名到经纬度的简易映射
_CITY_COORDS = {
    "北京": (39.9042, 116.4074),
    "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644),
    "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551),
    "成都": (30.5728, 104.0668),
    "重庆": (29.4316, 106.9123),
    "武汉": (30.5928, 114.3055),
    "南京": (32.0603, 118.7969),
    "西安": (34.3416, 108.9398),
    "天津": (39.3434, 117.3616),
    "苏州": (31.2990, 120.5853),
    "长沙": (28.2282, 112.9388),
    "郑州": (34.7466, 113.6253),
    "济南": (36.6512, 116.9972),
    "青岛": (36.0671, 120.3826),
    "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894),
    "福州": (26.0745, 119.2965),
    "合肥": (31.8206, 117.2272),
    "昆明": (25.0389, 102.7183),
    "贵阳": (26.6470, 106.6302),
    "南宁": (22.8170, 108.3665),
    "海口": (20.0440, 110.3500),
    "哈尔滨": (45.8038, 126.5350),
    "长春": (43.8171, 125.3235),
    "沈阳": (41.8057, 123.4315),
    "石家庄": (38.0428, 114.5149),
    "太原": (37.8706, 112.5489),
    "兰州": (36.0611, 103.8343),
    "乌鲁木齐": (43.8256, 87.6168),
}

_WEATHER_CODE_ZH = {
    0: "晴天", 1: "大部晴朗", 2: "多云", 3: "阴天",
    45: "雾", 48: "冰雾", 51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "小冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "阵雪",
    95: "雷暴", 96: "冰雹雷暴", 99: "大冰雹雷暴",
}


def _geocode(city_name: str) -> tuple:
    """城市名→经纬度"""
    name = city_name.strip().rstrip("市省区县")
    # 精确匹配
    for key, coords in _CITY_COORDS.items():
        if key == name or key.startswith(name) or name.startswith(key):
            return coords
    # 模糊搜索
    lower = name.lower()
    for key, coords in _CITY_COORDS.items():
        if lower in key.lower() or key.lower() in lower:
            return coords
    return None


def _weather_desc(code: int) -> str:
    return _WEATHER_CODE_ZH.get(code, f"未知({code})")


def _wind_direction(deg: float) -> str:
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    idx = round(deg / 45) % 8
    return dirs[idx]


def get_weather(city: str) -> dict:
    """
    获取城市实时天气。
    API: Open-Meteo (https://open-meteo.com/)，免费无 Key。
    返回: {"city": ..., "temperature": ..., "humidity": ..., "wind_speed": ...}
    """
    coords = _geocode(city)
    if not coords:
        return {"error": f"暂不支持「{city}」的天气查询，请尝试北京、上海、广州等主要城市", "city": city}

    lat, lon = coords

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            f"weather_code,wind_speed_10m,wind_direction_10m,pressure_msl"
            f"&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"
            f"&timezone=Asia%2FShanghai&forecast_days=4"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "IOIQ/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        current = data.get("current", {})
        daily = data.get("daily", {})

        forecast = []
        if daily:
            times = daily.get("time", [])
            codes = daily.get("weather_code", [])
            highs = daily.get("temperature_2m_max", [])
            lows = daily.get("temperature_2m_min", [])
            pops = daily.get("precipitation_probability_max", [])
            for i in range(min(len(times), 4)):
                forecast.append({
                    "date": times[i],
                    "weather": _weather_desc(codes[i]) if i < len(codes) else "",
                    "high": highs[i] if i < len(highs) else None,
                    "low": lows[i] if i < len(lows) else None,
                    "precip_pct": pops[i] if i < len(pops) else None,
                })

        return {
            "city": city,
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "weather": _weather_desc(current.get("weather_code", 0)),
            "wind_speed": current.get("wind_speed_10m"),
            "wind_direction": _wind_direction(current.get("wind_direction_10m", 0)),
            "pressure": current.get("pressure_msl"),
            "forecast": forecast,
            "source": "Open-Meteo",
        }
    except urllib.error.URLError as e:
        return {"error": f"天气服务请求失败：{str(e.reason)}", "city": city}
    except Exception as e:
        return {"error": f"天气数据解析失败：{str(e)}", "city": city}
