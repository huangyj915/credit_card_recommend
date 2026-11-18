"""Standardized Taiwan credit card spending channels."""

from typing import Dict, List


CHANNELS: List[Dict[str, str]] = [
    {
        "code": "convenience_store",
        "label": "超商消費",
        "examples": "7-11、全家、萊爾富、OK",
        "icon": "🏪",
    },
    {
        "code": "dining",
        "label": "餐飲美食",
        "examples": "餐廳、咖啡廳、速食店",
        "icon": "🍽️",
    },
    {
        "code": "delivery",
        "label": "外送平台",
        "examples": "Uber Eats、foodpanda",
        "icon": "🛵",
    },
    {
        "code": "ecommerce",
        "label": "網購電商",
        "examples": "momo、PChome、蝦皮、酷澎",
        "icon": "🛒",
    },
    {
        "code": "mobile_pay",
        "label": "行動支付",
        "examples": "LINE Pay、街口支付、Apple Pay、全盈+PAY",
        "icon": "📱",
    },
    {
        "code": "supermarket",
        "label": "超市量販",
        "examples": "全聯、家樂福、好市多、大潤發",
        "icon": "🧺",
    },
    {
        "code": "transport",
        "label": "交通通勤",
        "examples": "高鐵、台鐵、捷運、Uber、加油",
        "icon": "🚆",
    },
    {
        "code": "travel",
        "label": "旅遊住宿",
        "examples": "機票、訂房網、旅行社、Klook",
        "icon": "🏨",
    },
    {
        "code": "overseas",
        "label": "海外消費",
        "examples": "外幣實體消費、日韓旅遊、海外網站",
        "icon": "✈️",
    },
    {
        "code": "general",
        "label": "一般國內消費",
        "examples": "其他無指定通路之一般刷卡",
        "icon": "💳",
    },
]

CHANNEL_MAP: Dict[str, Dict[str, str]] = {item["code"]: item for item in CHANNELS}
