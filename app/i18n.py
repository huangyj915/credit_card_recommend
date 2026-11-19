"""Backend internationalization (i18n) utilities for Traditional Chinese (zh-TW) and English (en)."""

import re
from typing import Dict, List, Optional, Tuple

from app.channels import CHANNELS
from app.models import CardOut, RewardRuleOut

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _norm_key(text: str) -> str:
    return re.sub(r"[\s\-_/（）()・]+", "", (text or "").strip().lower())

DEFAULT_LANG = "zh-TW"
SUPPORTED_LANGS = ("zh-TW", "en")


def normalize_lang(lang: Optional[str]) -> str:
    """Normalize a requested language code to 'zh-TW' or 'en'."""
    if not lang:
        return DEFAULT_LANG
    cleaned = lang.strip().lower().replace("_", "-")
    if cleaned == "en" or cleaned.startswith("en-"):
        return "en"
    return DEFAULT_LANG


CHANNEL_TRANSLATIONS_EN: Dict[str, Dict[str, str]] = {
    "convenience_store": {
        "label": "Convenience Stores",
        "examples": "7-ELEVEN, FamilyMart, Hi-Life, OKmart",
    },
    "dining": {
        "label": "Dining & Cafes",
        "examples": "Restaurants, cafes, fast food",
    },
    "delivery": {
        "label": "Food Delivery",
        "examples": "Uber Eats, foodpanda",
    },
    "ecommerce": {
        "label": "Online Shopping",
        "examples": "momo, PChome, Shopee, Coupang",
    },
    "mobile_pay": {
        "label": "Mobile Payments",
        "examples": "LINE Pay, JKOPay, Apple Pay, PXPay Plus",
    },
    "supermarket": {
        "label": "Supermarkets & Groceries",
        "examples": "PX Mart, Carrefour, Costco, RT-Mart",
    },
    "transport": {
        "label": "Transit & Commute",
        "examples": "THSR, TRA, MRT, Uber, Gas stations",
    },
    "travel": {
        "label": "Travel & Lodging",
        "examples": "Flights, hotels, travel agencies, Klook",
    },
    "overseas": {
        "label": "Overseas Spending",
        "examples": "Foreign in-store, Japan/Korea travel, overseas sites",
    },
    "general": {
        "label": "General Domestic",
        "examples": "Other general domestic card purchases",
    },
}

BANK_NAME_EN: Dict[str, str] = {
    "國泰世華": "Cathay United Bank",
    "台新銀行": "Taishin Bank",
    "玉山銀行": "E.SUN Bank",
    "台北富邦": "Taipei Fubon Bank",
    "中國信託": "CTBC Bank",
    "永豐銀行": "Bank SinoPac",
    "聯邦銀行": "Union Bank of Taiwan",
    "星展銀行": "DBS Bank",
    "匯豐銀行": "HSBC Taiwan",
    "兆豐銀行": "Mega Bank",
    "第一銀行": "First Bank",
    "華南銀行": "Hua Nan Bank",
    "遠東商銀": "Far Eastern International Bank",
    "上海商銀": "Shanghai Commercial & Savings Bank",
    "元大銀行": "Yuanta Bank",
    "樂天信用卡": "Rakuten Card",
    "彰化銀行": "Chang Hwa Bank",
    "合作金庫": "Taiwan Cooperative Bank",
    "凱基銀行": "KGI Bank",
    "土地銀行": "Land Bank of Taiwan",
    "臺灣銀行": "Bank of Taiwan",
    "自訂銀行": "Custom Bank",
}

CARD_NAME_EN: Dict[str, str] = {
    # Cathay
    "CUBE 卡": "CUBE Card",
    "蝦皮購物聯名卡": "Shopee Co-branded Card",
    "長榮航空聯名卡": "EVA Air Co-branded Card",
    "亞洲萬里通聯名卡": "Asia Miles Co-branded Card",
    "世界卡": "World Card",
    # Taishin
    "@GoGo 卡": "@GoGo Card",
    "台新 Richart 卡": "Taishin Richart Card",
    "街口聯名卡": "JKOPay Co-branded Card",
    "遠傳 friDay 聯名卡": "friDay Co-branded Card",
    "Gogoro Rewards 聯名卡": "Gogoro Rewards Card",
    "玫瑰卡": "Rose Card",
    "太陽卡": "Solar Card",
    # E.SUN
    "U Bear 信用卡": "U Bear Credit Card",
    "玉山 Unicard": "E.SUN Unicard",
    "玉山熊本熊卡": "E.SUN Kumamon Card",
    "Pi 拍錢包信用卡": "Pi Wallet Credit Card",
    "星宇航空聯名卡": "STARLUX Co-branded Card",
    "玉山易遊卡": "E.SUN ezTravel Card",
    "玉山數位 e 卡": "E.SUN Digital e-Card",
    "玉山 Only 卡": "E.SUN Only Card",
    # Fubon
    "富邦 J 卡": "Fubon J Card",
    "Costco 聯名卡": "Costco Co-branded Card",
    "momo 卡": "momo Card",
    "Open Possible 聯名卡": "Open Possible Card",
    "富邦尊御世界卡": "Fubon Imperial World Card",
    "福華聯名卡": "Howard Plaza Hotels Co-branded Card",
    # CTBC
    "LINE Pay 信用卡": "LINE Pay Credit Card",
    "ALL ME 卡": "ALL ME Card",
    "英雄聯盟信用卡": "League of Legends Credit Card",
    "中油聯名卡": "CPC Co-branded Card",
    "中華航空聯名卡": "China Airlines Co-branded Card",
    "LaLaport 聯名卡": "LaLaport Co-branded Card",
    "商旅鈦金卡": "Business Travel Titanium Card",
    # SinoPac
    "DAWHO 現金回饋信用卡": "DAWHO Cashback Credit Card",
    "永豐幣倍卡": "SinoPac Dual-Currency Card",
    "永豐 SPORT 卡": "SinoPac SPORT Card",
    "DAWAY 卡": "DAWAY Card",
    "現金回饋 Green 卡": "Cashback Green Card",
    "永豐 55688 聯名卡": "SinoPac 55688 Co-branded Card",
    "MITSUI OUTLET PARK 卡": "MITSUI OUTLET PARK Card",
    # UBOT
    "吉鶴卡": "Jihe Card",
    "聯邦賴點卡": "UBOT LINE Point Card",
    "聯邦綠卡": "UBOT Green Card",
    "聯邦 M 卡": "UBOT M Card",
    "LINE Bank 聯名卡": "LINE Bank Co-branded Card",
    "聯邦 MaiCoin 聯名卡": "UBOT MaiCoin Co-branded Card",
    # DBS
    "星展 eco 永續卡": "DBS eco Sustainability Card",
    "星展饗樂生活卡": "DBS FunLife Card",
    "星展飛行世界商務卡": "DBS Travel World Business Card",
    "星展炫晶商務御璽卡": "DBS LiveFresh Business Signature Card",
    "星展傳說對決聯名卡": "DBS Arena of Valor Card",
    "星展 PChome Prime 聯名卡": "DBS PChome Prime Card",
    "星展everyday鈦金卡": "DBS Everyday Titanium Card",
    "星展 everyday 鈦金卡": "DBS Everyday Titanium Card",
    # HSBC
    "匯豐現金回饋御璽卡": "HSBC Cashback Signature Card",
    "匯豐匯鑽卡": "HSBC Diamond Cashback Card",
    "匯豐 Live+ 現金回饋卡": "HSBC Live+ Cashback Card",
    "匯豐旅人無限卡": "HSBC TravelOne Visa Infinite Card",
    "匯豐旅人御璽卡": "HSBC TravelOne Signature Card",
    "匯豐旅人輕旅卡": "HSBC TravelOne Card",
    "卓越理財信用卡": "HSBC Premier Credit Card",
    # Mega Bank
    "e 秒刷鈦金卡": "e-Instant Titanium Card",
    "宇宙明星 BT21 信用卡": "BT21 Credit Card",
    "利多御璽卡": "Lido Signature Card",
    "Mega One 一卡通聯名卡": "Mega One iPASS Card",
    # First Bank
    "iLEO 信用卡": "iLEO Credit Card",
    "綠活卡": "Green Life Card",
    "御璽商旅卡": "Signature Business Travel Card",
    "桃園市市民卡聯名卡": "Taoyuan Citizen Co-branded Card",
    # Hua Nan
    "SnY 信用卡": "SnY Credit Card",
    "i 網購生活卡": "i-Shopping Life Card",
    "超鑽現金回饋卡": "Super Diamond Cashback Card",
    "Rich+ 富家卡": "Rich+ Family Card",
    # FEIB
    "遠東樂家+卡": "FEIB Happy Home+ Card",
    "Bankee 信用卡": "Bankee Credit Card",
    "遠東快樂信用卡": "FEIB Happy Credit Card",
    "C'est Moi 旅遊卡": "C'est Moi Travel Card",
    # SCSB
    "小小兵回饋卡": "Minions Cashback Card",
    "Teresa 卡": "Teresa Card",
    "簡單卡": "Simple Card",
    "Cloud Bank 雲端卡": "Cloud Bank Card",
    # Yuanta
    "元大鑽金卡": "Yuanta Diamond Cashback Card",
    "鑽金智富卡": "Diamond Wealth Card",
    "分享黑啤卡": "Share Black Bear Card",
    "Hello Kitty 鑽金聯名卡": "Hello Kitty Diamond Card",
    # Rakuten
    "樂天信用卡": "Rakuten Credit Card",
    "樂天 Panda J 卡": "Rakuten Panda J Card",
    "樂天虎航聯名卡": "Rakuten Tigerair Co-branded Card",
    # Chang Hwa
    "My 樂現金回饋卡": "My Fun Cashback Card",
    "My 購卡": "My Shop Card",
    "馬偕認同卡": "Mackay Affinity Card",
    # TCB
    "卡娜赫拉的小動物悠遊聯名卡": "Kanahei EasyCard Co-branded Card",
    "i 享樂生活卡": "i-Enjoy Life Card",
    "活力御璽卡": "Vitality Signature Card",
    # KGI
    "魔 BUY 悠遊卡": "Magic BUY EasyCard",
    "現金回饋卡": "Cashback Card",
    "魔 FUN 悠遊卡": "Magic FUN EasyCard",
    # Land Bank
    "JCB 極緻卡": "JCB Eternity Card",
    "一卡通聯名卡": "iPASS Co-branded Card",
    # Bank of Taiwan
    "導盲犬認同卡": "Guide Dog Affinity Card",
    "一卡通 Titanium 商旅卡": "iPASS Titanium Travel Card",
}

PLAN_NAME_EN: Dict[str, str] = {
    "玩數位": "Digital Fun",
    "樂饗購": "Joy Shopping",
    "趣旅行": "Fun Travel",
    "集精選": "Curated Picks",
    "慶生月": "Birthday Month",
}

ANNUAL_FEE_EN: Dict[str, str] = {
    "首年免年費，電子帳單/任刷12次免年費": "1st year waived; waived with e-statement or 12+ txns/yr",
    "電子帳單免年費": "Waived with e-statement",
    "免年費（達成條件）": "Waived when conditions are met",
    "依銀行官網公告": "Per issuing bank announcement",
}

REWARD_UNIT_EN: Dict[str, str] = {
    "小樹點(信用卡)": "Tree Points (Credit Card)",
    "台新 Point(信用卡)": "Taishin Points (Credit Card)",
    "當期帳單直接折抵": "Direct statement credit",
    "LINE POINTS / 現金回饋": "LINE POINTS / Cashback",
    "現金回饋": "Cashback",
    "現金回饋（匯入大戶帳戶）": "Cashback (deposited to DAWHO account)",
    "現金回饋 / 點數": "Cashback / Points",
}

PAYMENT_METHOD_EN: Dict[str, str] = {
    "實體/線上刷卡": "In-store / Online",
    "實體刷卡": "In-store",
    "線上刷卡": "Online",
    "街口支付": "JKOPay",
    "全盈+PAY": "PXPay Plus",
    "台新Pay": "Taishin Pay",
    "悠遊卡自動加值": "EasyCard Auto-reload",
}

CARD_NOTES_EN: Dict[str, str] = {
    "權益切換型神卡，每日可透過 App 切換方案（例：玩數位、樂饗購、趣旅行、集精選），本系統會自動幫你試算最適合你消費結構的方案。": (
        "Flexible switchable-plan card allowing daily plan changes in-app "
        "(e.g. Digital Fun, Joy Shopping, Fun Travel, Curated Picks). The system automatically selects the best plan for your spending."
    ),
    "網購、外送與行動支付主力卡，通常需綁定數位帳單與Richart帳戶自動扣繳以享加碼回饋（有每月上限）。": (
        "Popular card for online shopping, food delivery, and mobile pay. Usually requires e-statement and Richart auto-debit for bonus cashback (monthly cap applies)."
    ),
    "網購直接折抵當期帳單，一般消費亦有 1% 無上限，適合小資網購與影音訂閱族群。": (
        "Online shopping rewards automatically offset the current statement, plus unlimited 1% base cashback. Great for online shoppers and streaming subscriptions."
    ),
    "日韓旅遊神卡，日本/韓國實體消費享高額加碼，國內亦有 1% 無上限與指定交通/超商回饋。": (
        "Top card for Japan & Korea travel with boosted in-store rewards, plus unlimited 1% domestic base rate and bonus transit/convenience store perks."
    ),
    "國內無腦 1%～2%（綁定帳戶自動扣繳），日幣消費及指定國內日系餐飲美食享加碼。": (
        "Easy 1%–2% domestic rate (with bank account auto-debit), plus bonus rewards on JPY spending and designated Japanese restaurants in Taiwan."
    ),
    "須成為「大戶」等級（往來資產達標）可解鎖國內 2% / 海外 3% 與七大通路加碼至 7%。": (
        "Requires DAWHO tier status (asset threshold met) to unlock 2% domestic / 3% overseas base rates and up to 7% across 7 designated categories."
    ),
    "日韓泰旅遊神卡，日韓泰消費最高 6%、日本三大交通卡最高 10%，國內一般消費 1% 無上限。": (
        "Top card for Japan, Korea & Thailand travel: up to 6% overseas, up to 10% on major Japan IC transit cards, plus unlimited 1% domestic base rate."
    ),
    "國內一般消費 1% 無上限，日幣消費及指定國內日系名店享加碼 4% 回饋。": (
        "Unlimited 1% domestic base rate, plus up to 4% on JPY spending and designated Japanese merchants in Taiwan."
    ),
    "須成為「大戶Plus」或「大戶」等級並完成指定任務，享國內最高 5% / 國外最高 6% 現金回饋。": (
        "Requires DAWHO Plus / DAWHO tier and completed missions for up to 5% domestic and 6% overseas cashback."
    ),
    "透過 Playwright 爬取國泰世華 CUBE 卡頁面並自動解析方案規則。": (
        "Scraped from Cathay United CUBE Card page via Playwright and parsed into plan rules."
    ),
    "透過 Playwright 爬取玉山 U Bear 卡頁面並自動解析回饋與上限。": (
        "Scraped from E.SUN U Bear Card page via Playwright and parsed for rates and caps."
    ),
    "透過 Playwright 爬取台新 @GoGo 卡頁面並自動解析回饋與上限。": (
        "Scraped from Taishin @GoGo Card page via Playwright and parsed for rates and caps."
    ),
}

RULE_CONDITIONS_EN: Dict[str, str] = {
    "需切換至「玩數位」方案（含蝦皮、momo、PChome、酷澎等）": (
        "Requires switching to 'Digital Fun' plan (Shopee, momo, PChome, Coupang, etc.)"
    ),
    "需切換至「玩數位」方案並綁定指定數位/網購通路": (
        "Requires 'Digital Fun' plan with designated digital/online channels"
    ),
    "需切換至「樂饗購」方案（國內餐飲、百貨、藥妝）": (
        "Requires 'Joy Shopping' plan (domestic dining, department stores, pharmacies)"
    ),
    "需切換至「樂饗購」方案（Uber Eats、foodpanda）": (
        "Requires 'Joy Shopping' plan (Uber Eats, foodpanda)"
    ),
    "需切換至「趣旅行」方案（海外實體消費、機票、訂房）": (
        "Requires 'Fun Travel' plan (overseas in-store, flights, hotels)"
    ),
    "需切換至「趣旅行」方案（航空公司、全球飯店、Klook 等）": (
        "Requires 'Fun Travel' plan (airlines, global hotels, Klook, etc.)"
    ),
    "需切換至「趣旅行」方案（高鐵、Uber、台灣大車隊等）": (
        "Requires 'Fun Travel' plan (THSR, Uber, Taiwan Taxi, etc.)"
    ),
    "需切換至「集精選」方案（7-11、全家）": (
        "Requires 'Curated Picks' plan (7-ELEVEN, FamilyMart)"
    ),
    "需切換至「集精選」方案（全聯、家樂福）": (
        "Requires 'Curated Picks' plan (PX Mart, Carrefour)"
    ),
    "指定網購（蝦皮、momo、酷澎、PChome 等），加碼享每月上限": (
        "Designated online merchants (Shopee, momo, Coupang, PChome, etc.); monthly cap applies"
    ),
    "綁定指定行動支付（含超商/餐飲適用店點）": (
        "Designated mobile payments (includes eligible convenience stores & dining)"
    ),
    "Uber Eats、foodpanda 適用": "Valid on Uber Eats and foodpanda",
    "指定網路消費與行動支付（部分通路加碼每月上限約 200 元）": (
        "Designated online & mobile pay spending (bonus capped at ~NT$200/mo)"
    ),
    "透過網路消費認定之行動支付綁定（不含超商實體代收）": (
        "Mobile payments classified as online spending (excludes convenience store bill pay)"
    ),
    "Uber Eats、foodpanda 列為網路消費": "Uber Eats and foodpanda qualify as online spending",
    "日韓當地實體消費含基本+加碼（加碼需登錄，每月上限依活動規範）": (
        "In-store spending in Japan & Korea incl. bonus (registration required; monthly cap applies)"
    ),
    "指定航空、旅行社與訂房活動期間加碼": (
        "Seasonal bonus for designated airlines, travel agencies, and hotel bookings"
    ),
    "指定超商/咖啡通路搭配行動支付": (
        "Designated convenience stores & cafes via mobile payment"
    ),
    "日本消費綁定 Apple Pay QUICPay 含加碼": (
        "Japan spending via Apple Pay QUICPay includes bonus rate"
    ),
    "國內指定日系名店與餐飲通路加碼": (
        "Bonus at designated Japanese-brand stores and dining merchants in Taiwan"
    ),
    "綁定聯邦 NewNewBank 數位帳戶自扣享無上限回饋": (
        "Unlimited cashback with UBOT NewNewBank auto-debit"
    ),
    "大戶等級（樂/食/行/玩/學/家/寵七大指定通路加碼）": (
        "DAWHO tier bonus across 7 designated lifestyle categories"
    ),
    "Uber Eats、foodpanda 列為七大通路，加碼每月上限 300 元": (
        "Uber Eats & foodpanda included in 7 categories; bonus capped at NT$300/mo"
    ),
    "航空、飯店、旅行社列為七大通路": (
        "Airlines, hotels, and travel agencies included in 7 categories"
    ),
    "高鐵、台鐵、Uber 等指定交通通路": (
        "THSR, TRA, Uber, and designated transit merchants"
    ),
    "大戶等級享海外消費 3% 無上限": (
        "DAWHO tier earns unlimited 3% on overseas spending"
    ),
    "日韓泰旅遊最高 6% 回饋（含基本+加碼，加碼需登錄）": (
        "Up to 6% for Japan, Korea & Thailand travel (incl. bonus; registration required)"
    ),
    "日本三大交通卡（Suica / PASMO / ICOCA）最高 10% 回饋": (
        "Up to 10% on major Japan IC transit cards (Suica / PASMO / ICOCA)"
    ),
    "國內一般消費 1% 回饋無上限": "Unlimited 1% on general domestic spending",
    "日幣消費 2.5% 無上限 + 行動支付加碼最高 4%": (
        "2.5% unlimited on JPY spending + mobile pay bonus up to 4%"
    ),
    "國內嚴選日系名店加碼 4% 回饋（每月上限 500 元）": (
        "4% bonus at select Japanese-brand merchants in Taiwan (cap NT$500/mo)"
    ),
    "大戶Plus等級國內一般消費最高 5%（基本 1%+任務加碼 4%，每月上限 1,000 元）": (
        "DAWHO Plus tier: up to 5% domestic (1% base + 4% mission bonus, cap NT$1,000/mo)"
    ),
    "大戶Plus等級國內餐飲一般消費最高 5%（含任務加碼，每月上限 1,000 元）": (
        "DAWHO Plus tier: up to 5% on domestic dining (incl. mission bonus, cap NT$1,000/mo)"
    ),
    "大戶Plus等級外送平台一般消費最高 5%（含任務加碼，每月上限 1,000 元）": (
        "DAWHO Plus tier: up to 5% on food delivery (incl. mission bonus, cap NT$1,000/mo)"
    ),
    "大戶Plus等級旅遊住宿一般消費最高 5%（含任務加碼，每月上限 1,000 元）": (
        "DAWHO Plus tier: up to 5% on travel & lodging (incl. mission bonus, cap NT$1,000/mo)"
    ),
    "大戶Plus等級悠遊卡自動加值／交通最高 5%（每月上限 500 元）": (
        "DAWHO Plus tier: up to 5% on EasyCard auto-reload & transit (cap NT$500/mo)"
    ),
    "大戶Plus等級國外消費最高 6%（基本 2%+任務加碼 4%，每月上限 1,000 元）": (
        "DAWHO Plus tier: up to 6% overseas (2% base + 4% mission bonus, cap NT$1,000/mo)"
    ),
    "精選網購（蝦皮、momo、酷澎、PChome）最高 3.8% 回饋，每月上限 1,500 元 行動支付綁定 LINE Pay、全盈+PAY、台新Pay 最高 3.8% 回饋，每月上限 1,500 元 外送平台 Uber Eats、foo": (
        "Up to 3.8% on select online shopping (Shopee, momo, Coupang, PChome), mobile pay (LINE Pay, PXPay Plus, Taishin Pay), and delivery (Uber Eats, foodpanda); cap NT$1,500/mo"
    ),
    # Scraped demo_html conditions (Cathay CUBE, Taishin @GoGo, E.SUN U Bear)
    "玩數位 蝦皮、momo、PChome、酷澎網購電商享 3% 小樹點無上限": (
        "Digital Fun: Unlimited 3% Tree Points on Shopee, momo, PChome, and Coupang"
    ),
    "玩數位 LINE Pay、Apple Pay 指定數位網購平台享 3% 回饋": (
        "Digital Fun: 3% reward on designated online platforms via LINE Pay / Apple Pay"
    ),
    "樂饗購 國內餐飲美食、百貨與藥妝享 3% 小樹點無上限": (
        "Joy Shopping: Unlimited 3% Tree Points on domestic dining, department stores, and pharmacies"
    ),
    "樂饗購 Uber Eats、foodpanda 外送平台享 3% 回饋": (
        "Joy Shopping: 3% reward on Uber Eats and foodpanda"
    ),
    "趣旅行 海外實體消費、機票航空、全球飯店訂房享 3% 小樹點無上限": (
        "Fun Travel: Unlimited 3% Tree Points on overseas in-store, flights, and global hotels"
    ),
    "趣旅行 台灣高鐵、Uber 等交通通勤享 3% 回饋": (
        "Fun Travel: 3% reward on THSR, Uber, and transit"
    ),
    "集精選 7-11、全家超商消費享 2% 小樹點回饋": (
        "Curated Picks: 2% Tree Points at 7-ELEVEN and FamilyMart"
    ),
    "集精選 全聯福利中心、家樂福超市量販享 2% 回饋": (
        "Curated Picks: 2% reward at PX Mart and Carrefour"
    ),
    "精選網購（蝦皮、momo、酷澎、PChome）最高 3% 回饋，每月上限 1,500 元 行動支付綁定 LINE Pay、全盈+PAY、台新Pay 最高 3% 回饋，每月上限 1,500 元 外送平台 Uber Eats、foodpanda": (
        "Up to 3% on select online shopping (Shopee, momo, Coupang, PChome), mobile pay (LINE Pay, PXPay Plus, Taishin Pay), and delivery (Uber Eats, foodpanda); cap NT$1,500/mo"
    ),
    "網購電商（momo、蝦皮、PChome）網路消費享 3% 現金回饋，每月加碼上限 200 元 行動支付綁定 LINE Pay、街口支付消費享 3% 現金回饋，上限 200 元 Uber Eats、foodpanda 外送平台享 3% 回饋，": (
        "3% cashback on online shopping (momo, Shopee, PChome), LINE Pay/JKOPay, and Uber Eats/foodpanda; bonus cap NT$200/mo"
    ),
}

_CARD_NAME_NORM_EN: Dict[str, str] = {_norm_key(k): v for k, v in CARD_NAME_EN.items()}

_CARD_TOKEN_GLOSSARY: List[Tuple[str, str]] = [
    ("國泰世華", "Cathay United "),
    ("台北富邦", "Taipei Fubon "),
    ("台新銀行", "Taishin "),
    ("玉山銀行", "E.SUN "),
    ("永豐銀行", "SinoPac "),
    ("聯邦銀行", "UBOT "),
    ("星展銀行", "DBS "),
    ("匯豐銀行", "HSBC "),
    ("滙豐銀行", "HSBC "),
    ("兆豐銀行", "Mega "),
    ("第一銀行", "First Bank "),
    ("華南銀行", "Hua Nan "),
    ("遠東商銀", "FEIB "),
    ("上海商銀", "SCSB "),
    ("元大銀行", "Yuanta "),
    ("樂天信用卡", "Rakuten "),
    ("彰化銀行", "Chang Hwa "),
    ("合作金庫", "TCB "),
    ("凱基銀行", "KGI "),
    ("土地銀行", "Land Bank "),
    ("臺灣銀行", "Bank of Taiwan "),
    ("富邦", "Fubon "),
    ("台新", "Taishin "),
    ("玉山", "E.SUN "),
    ("永豐", "SinoPac "),
    ("聯邦", "UBOT "),
    ("星展", "DBS "),
    ("匯豐", "HSBC "),
    ("滙豐", "HSBC "),
    ("樂天", "Rakuten "),
    ("遠東", "FEIB "),
    ("元大", "Yuanta "),
    ("悠遊聯名卡", " EasyCard Co-branded Card"),
    ("一卡通聯名卡", " iPASS Co-branded Card"),
    ("現金回饋信用卡", " Cashback Credit Card"),
    ("現金回饋卡", " Cashback Card"),
    ("商務御璽卡", " Business Signature Card"),
    ("商旅鈦金卡", " Business Travel Titanium Card"),
    ("認同卡", " Affinity Card"),
    ("聯名卡", " Co-branded Card"),
    ("商務卡", " Business Card"),
    ("鈦金卡", " Titanium Card"),
    ("御璽卡", " Signature Card"),
    ("無限卡", " Visa Infinite Card"),
    ("世界卡", " World Card"),
    ("極緻卡", " Eternity Card"),
    ("晶緻卡", " Precious Card"),
    ("白金卡", " Platinum Card"),
    ("簽帳金融卡", " Debit Card"),
    ("推薦卡片", "Recommended Card"),
    ("信用卡", " Credit Card"),
    ("卡片", " Card"),
    ("熊本熊", "Kumamon"),
    ("熊本", "Kumamon"),
    ("卡", " Card"),
]

_SCRAPED_HIGHLIGHT_KEYWORDS: List[Tuple[str, str]] = [
    ("7-11", "7-ELEVEN"),
    ("全家", "FamilyMart"),
    ("萊爾富", "Hi-Life"),
    ("全聯", "PX Mart"),
    ("大全聯", "RT-Mart"),
    ("大潤發", "RT-Mart"),
    ("家樂福", "Carrefour"),
    ("好市多", "Costco"),
    ("新光三越", "Shin Kong Mitsukoshi"),
    ("康是美", "Cosmed"),
    ("ikea", "IKEA"),
    ("高鐵", "THSR"),
    ("台鐵", "TRA"),
    ("uber eats", "Uber Eats"),
    ("foodpanda", "foodpanda"),
    ("ubereats", "Uber Eats"),
    ("momo", "momo"),
    ("pchome", "PChome"),
    ("蝦皮", "Shopee"),
    ("酷澎", "Coupang"),
    ("klook", "Klook"),
    ("kkday", "KKday"),
    ("line pay", "LINE Pay"),
    ("apple pay", "Apple Pay"),
    ("台新pay", "Taishin Pay"),
    ("街口", "JKOPay"),
    ("全盈", "PXPay Plus"),
    ("myfone", "myfone"),
    ("tesla", "Tesla"),
    ("gogoro", "Gogoro"),
    ("日本", "Japan"),
    ("韓國", "Korea"),
    ("日韓", "Japan & Korea"),
    ("海外", "Overseas"),
    ("國外", "Overseas"),
    ("飯店", "Hotels"),
    ("住宿", "Hotels"),
    ("餐廳", "Dining"),
    ("餐飲", "Dining"),
    ("機場貴賓室", "Airport lounge"),
    ("機場接送", "Airport transfer"),
    ("新戶", "New cardholders"),
    ("登錄", "Registration required"),
    ("無上限", "Unlimited"),
    ("自扣", "Auto-debit"),
    ("電子帳單", "e-Statement"),
]

# Reverse lookup maps (case-insensitive) so English names submitted back to custom scrape still match.
_BANK_EN_TO_ZH: Dict[str, str] = {v.lower(): k for k, v in BANK_NAME_EN.items()}
_CARD_EN_TO_ZH: Dict[str, str] = {v.lower(): k for k, v in CARD_NAME_EN.items()}


def get_localized_channels(lang: Optional[str] = None) -> List[Dict[str, str]]:
    """Return standardized spending channels localized to the requested language."""
    resolved = normalize_lang(lang)
    if resolved == "zh-TW":
        return CHANNELS
    localized: List[Dict[str, str]] = []
    for ch in CHANNELS:
        en = CHANNEL_TRANSLATIONS_EN.get(ch["code"], {})
        localized.append(
            {
                "code": ch["code"],
                "label": en.get("label", ch["label"]),
                "examples": en.get("examples", ch["examples"]),
                "icon": ch["icon"],
            }
        )
    return localized


def get_channel_label(channel_code: str, lang: Optional[str] = None, fallback: Optional[str] = None) -> str:
    """Return localized label for a standardized channel code."""
    resolved = normalize_lang(lang)
    if resolved == "en":
        en = CHANNEL_TRANSLATIONS_EN.get(channel_code)
        if en:
            return en["label"]
    for ch in CHANNELS:
        if ch["code"] == channel_code:
            return ch["label"]
    return fallback or channel_code


def translate_bank_name(name: str, lang: Optional[str] = None) -> str:
    """Translate known Taiwan bank names when lang is 'en'."""
    if normalize_lang(lang) != "en":
        return name
    return BANK_NAME_EN.get(name, name)


def translate_card_name(name: str, lang: Optional[str] = None) -> str:
    """Translate known credit card names when lang is 'en', with glossary fallback for custom cards."""
    if normalize_lang(lang) != "en" or not name:
        return name
    if name in CARD_NAME_EN:
        return CARD_NAME_EN[name]
    normed = _CARD_NAME_NORM_EN.get(_norm_key(name))
    if normed:
        return normed
    if not _contains_cjk(name):
        return name

    translated = name
    for zh_tok, en_tok in _CARD_TOKEN_GLOSSARY:
        translated = translated.replace(zh_tok, en_tok)
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def translate_plan_name(name: Optional[str], lang: Optional[str] = None) -> Optional[str]:
    """Translate switchable plan names when lang is 'en'."""
    if name is None or normalize_lang(lang) != "en":
        return name
    return PLAN_NAME_EN.get(name, name)


def translate_annual_fee(text: str, lang: Optional[str] = None) -> str:
    if normalize_lang(lang) != "en":
        return text
    return ANNUAL_FEE_EN.get(text, text)


def translate_reward_unit(text: str, lang: Optional[str] = None) -> str:
    if normalize_lang(lang) != "en":
        return text
    return REWARD_UNIT_EN.get(text, text)


def translate_card_notes(text: str, lang: Optional[str] = None) -> str:
    """Translate card notes to English, including dynamically scraped note templates."""
    if normalize_lang(lang) != "en" or not text:
        return text
    if text in CARD_NOTES_EN:
        return CARD_NOTES_EN[text]

    custom_match = re.match(r"^透過 Playwright 依使用者指定卡名爬取解析（來源：(.+?)）。$", text.strip())
    if custom_match:
        return f"Scraped and parsed via Playwright by card name (Source: {custom_match.group(1)})."

    if _contains_cjk(text):
        url_match = re.search(r"https?://\S+?(?=[）)。\s]|$)", text)
        if url_match:
            return f"Scraped and parsed from official bank page via Playwright (Source: {url_match.group(0)})."
        return "Scraped and parsed from the issuing bank's official page via Playwright."
    return text


def _summarize_scraped_condition_en(
    raw_text: str,
    channel_code: Optional[str] = None,
    rate: Optional[float] = None,
    monthly_cap_ntd: Optional[float] = None,
    min_spend_ntd: Optional[float] = None,
    payment_methods: Optional[List[str]] = None,
) -> str:
    """Convert a live-scraped Chinese rule snippet into an English summary without raw CJK."""
    lowered = raw_text.lower()
    channel_label = get_channel_label(channel_code, "en") if channel_code else "eligible spending"
    rate_str = f"{rate:g}%" if rate is not None else "promo rate"

    # Detect non-reward financial disclosure snippets (e.g. revolving APR / cash advance fee)
    if any(tok in raw_text for tok in ("循環信用", "循環利率", "預借現金", "年利率")):
        return (
            f"Scraped page notice ({rate_str} listed): APR or cash advance fee disclosure "
            f"detected on bank page; verify actual {channel_label} reward rate on official site."
        )

    details: List[str] = []
    if payment_methods:
        en_methods = translate_payment_methods(payment_methods, "en")
        specific = [m for m in en_methods if m not in ("In-store / Online", "In-store", "Online")]
        if specific:
            details.append(f"via {', '.join(specific)}")

    if monthly_cap_ntd is not None:
        details.append(f"cap NT${int(monthly_cap_ntd):,}/mo")
    if min_spend_ntd is not None and min_spend_ntd > 0:
        details.append(f"min. spend NT${int(min_spend_ntd):,}")

    found_kws: List[str] = []
    for zh_kw, en_kw in _SCRAPED_HIGHLIGHT_KEYWORDS:
        if zh_kw in lowered and en_kw not in found_kws:
            found_kws.append(en_kw)
        if len(found_kws) >= 5:
            break

    if found_kws:
        details.append(f"highlights: {', '.join(found_kws)}")
    elif any(tok in raw_text for tok in ("折", "優惠", "現折")):
        details.append("discount / promo terms scraped from bank page")
    else:
        details.append("terms scraped from bank page")

    return f"{rate_str} on {channel_label} ({'; '.join(details)})"


def translate_rule_conditions(
    text: str,
    lang: Optional[str] = None,
    channel_code: Optional[str] = None,
    rate: Optional[float] = None,
    monthly_cap_ntd: Optional[float] = None,
    min_spend_ntd: Optional[float] = None,
    payment_methods: Optional[List[str]] = None,
) -> str:
    """Translate rule conditions to English, summarizing live-scraped Chinese snippets."""
    if normalize_lang(lang) != "en" or not text:
        return text
    if text in RULE_CONDITIONS_EN:
        return RULE_CONDITIONS_EN[text]
    if not _contains_cjk(text):
        return text
    return _summarize_scraped_condition_en(
        text,
        channel_code=channel_code,
        rate=rate,
        monthly_cap_ntd=monthly_cap_ntd,
        min_spend_ntd=min_spend_ntd,
        payment_methods=payment_methods,
    )


def translate_payment_methods(methods: List[str], lang: Optional[str] = None) -> List[str]:
    if normalize_lang(lang) != "en":
        return methods
    return [PAYMENT_METHOD_EN.get(m, m) for m in methods]


def translate_card_out(card: CardOut, lang: Optional[str] = None) -> CardOut:
    """Return a localized CardOut copy if lang is 'en', otherwise return card unchanged."""
    resolved = normalize_lang(lang)
    if resolved == "zh-TW":
        return card
    localized_rules = [
        RewardRuleOut(
            id=r.id,
            card_id=r.card_id,
            channel_code=r.channel_code,
            channel_label=get_channel_label(r.channel_code, resolved, r.channel_label),
            plan_name=translate_plan_name(r.plan_name, resolved),
            rate=r.rate,
            monthly_cap_ntd=r.monthly_cap_ntd,
            cap_group=r.cap_group,
            cap_applies_to=r.cap_applies_to,
            min_spend_ntd=r.min_spend_ntd,
            payment_methods=translate_payment_methods(r.payment_methods, resolved),
            conditions=translate_rule_conditions(
                r.conditions,
                resolved,
                channel_code=r.channel_code,
                rate=r.rate,
                monthly_cap_ntd=r.monthly_cap_ntd,
                min_spend_ntd=r.min_spend_ntd,
                payment_methods=r.payment_methods,
            ),
        )
        for r in card.rules
    ]
    return CardOut(
        id=card.id,
        bank_name=translate_bank_name(card.bank_name, resolved),
        card_name=translate_card_name(card.card_name, resolved),
        card_slug=card.card_slug,
        official_url=card.official_url,
        annual_fee=translate_annual_fee(card.annual_fee, resolved),
        base_rate_domestic=card.base_rate_domestic,
        base_rate_foreign=card.base_rate_foreign,
        reward_unit=translate_reward_unit(card.reward_unit, resolved),
        notes=translate_card_notes(card.notes, resolved),
        source_type=card.source_type,
        last_updated=card.last_updated,
        rules=localized_rules,
    )


def canonicalize_bank_name(name: Optional[str]) -> Optional[str]:
    """Map an English bank name back to its canonical Chinese bank name if known."""
    if not name:
        return name
    cleaned = name.strip()
    return _BANK_EN_TO_ZH.get(cleaned.lower(), cleaned)


def canonicalize_card_name(name: str) -> str:
    """Map an English card name back to its canonical Chinese card name if known."""
    cleaned = name.strip()
    return _CARD_EN_TO_ZH.get(cleaned.lower(), cleaned)


_MESSAGES: Dict[str, Dict[str, str]] = {
    "zh-TW": {
        "base_rate_note": "適用基本消費回饋",
        "min_spend_note": "未達低消門檻 NT${min_spend}，改計基本回饋 {base_rate}%",
        "cap_reached_note": "已達月回饋上限 NT${cap}（超過部分以基本回饋 {base_rate}% 計）",
        "shared_cap_reached_note": "已達共用月回饋上限 NT${cap}（超過部分以基本回饋 {base_rate}% 計）",
        "bonus_cap_reached_note": "已達月加碼上限 NT${cap}（基本回饋 {base_rate}% 另計無上限）",
        "shared_bonus_cap_reached_note": "已達共用月加碼上限 NT${cap}（基本回饋 {base_rate}% 另計無上限）",
        "overseas_fee_note": "已扣 1.5% 國外交易手續費 (-NT${fee})",
        "scraper_busy": "目前已有爬蟲任務執行中，請稍候再試。",
        "rate_limit_exceeded": "請求過於頻繁，請稍後再試。",
        "csrf_required": "偵測到跨站或未驗證來源請求，已拒絕操作。",
        "highlight_item": "{channel_label} {rate}%（省 NT${reward}）",
        "admin_token_required": "需要正確的管理員密碼（X-Admin-Token）才能執行寫入或爬蟲操作。",
        "public_readonly": "目前為公開唯讀展示模式，已停用卡片寫入與 Playwright 爬蟲。",
        "discover_success": "已透過 Playwright 從{bank_name}官網載入並合併 {count} 張信用卡。",
        "discover_empty": "未能從{bank_name}官網自動擷取到新的卡名（可能因官網防爬或動態載入），目前顯示內建與資料庫清單共 {count} 張。",
        "discover_error": "無法連線至{bank_name}官網列表頁（{err}），目前顯示內建清單共 {count} 張。",
        "unknown_bank_code": "未知的銀行爬蟲代碼: {code}",
        "scraper_discontinued": "偵測到「{bank_name} {card_name}」疑似已停發或停止申辦（{reason}），已略過不更新。",
        "scraper_no_rules": "頁面已開啟但未解析出結構化回饋規則（可能因官網改版、JS 動態載入或 WAF 阻擋），已保留既有資料。",
        "scraper_success": "成功透過 Playwright ({mode}) 解析並更新 {count} 條通路規則",
        "scraper_error": "爬取失敗：{exc_type}: {err}",
        "custom_discontinued_query": "「{card_name}」標示為停發／停止申辦卡片，已依設定略過不抓取。",
        "custom_url_invalid": "網址驗證失敗：{err}",
        "custom_demo_unsupported": "「{card_name}」屬於自訂新卡片，沒有內建離線示範 HTML；請改用即時爬取（live），或直接提供該卡官網網址進行測試。",
        "custom_url_not_found": "無法自動定位「{card_name}」的官網頁面（{reason}），請於下方補填該卡的「官方介紹頁網址」再試一次。",
        "custom_discontinued_page": "偵測到「{card_name}」已停發或停止申辦（{reason}），已略過不寫入資料庫。",
        "custom_no_rules": "已開啟頁面但未解析出「{card_name}」的結構化回饋規則（可能因官網改版、JS 動態載入或防爬阻擋），未更動既有資料。",
        "custom_success": "成功透過 Playwright 解析並更新「{bank_name} {card_name}」共 {count} 條通路規則",
        "custom_error": "爬取「{card_name}」失敗：{exc_type}: {err}",
    },
    "en": {
        "base_rate_note": "Base reward rate applied",
        "min_spend_note": "Below min. spend NT${min_spend}; base rate {base_rate}% applied",
        "cap_reached_note": "Monthly cap NT${cap} reached (excess earns base rate {base_rate}%)",
        "shared_cap_reached_note": "Shared monthly cap NT${cap} reached (excess earns base rate {base_rate}%)",
        "bonus_cap_reached_note": "Monthly bonus cap NT${cap} reached (base rate {base_rate}% still applies)",
        "shared_bonus_cap_reached_note": "Shared monthly bonus cap NT${cap} reached (base rate {base_rate}% still applies)",
        "overseas_fee_note": "Incl. -1.5% FX fee (-NT${fee})",
        "scraper_busy": "Another Playwright scraper task is currently running; please try again shortly.",
        "rate_limit_exceeded": "Too many requests; please try again shortly.",
        "csrf_required": "Cross-site or unverified origin request rejected.",
        "highlight_item": "{channel_label} {rate}% (Save NT${reward})",
        "admin_token_required": "Valid admin password (X-Admin-Token) is required for write or scraper operations.",
        "public_readonly": "Public read-only demo mode is active; card writes and Playwright scrapers are disabled.",
        "discover_success": "Loaded and merged {count} credit cards from {bank_name} official site via Playwright.",
        "discover_empty": "Could not auto-extract new card names from {bank_name} website (anti-bot or dynamic rendering); showing {count} curated & saved cards.",
        "discover_error": "Failed to connect to {bank_name} card list page ({err}); showing {count} curated cards.",
        "unknown_bank_code": "Unknown bank scraper code: {code}",
        "scraper_discontinued": "Detected that '{bank_name} {card_name}' appears discontinued ({reason}); skipped update.",
        "scraper_no_rules": "Page loaded but no structured reward rules were parsed (site layout change, JS rendering, or WAF block); existing data preserved.",
        "scraper_success": "Parsed and updated {count} channel rules via Playwright ({mode})",
        "scraper_error": "Scrape failed: {exc_type}: {err}",
        "custom_discontinued_query": "'{card_name}' is marked as discontinued; skipped scraping.",
        "custom_url_invalid": "URL validation failed: {err}",
        "custom_demo_unsupported": "'{card_name}' is a custom card without built-in demo HTML; please switch to 'live' mode or provide the official card URL.",
        "custom_url_not_found": "Could not auto-locate the official page for '{card_name}' ({reason}); please fill in the 'Official Card Page URL' below and try again.",
        "custom_discontinued_page": "Detected that '{card_name}' is discontinued ({reason}); skipped saving to database.",
        "custom_no_rules": "Page loaded but no structured reward rules were parsed for '{card_name}' (site change, JS rendering, or anti-bot block); existing data unchanged.",
        "custom_success": "Parsed and updated {count} channel rules for '{bank_name} {card_name}' via Playwright",
        "custom_error": "Failed to scrape '{card_name}': {exc_type}: {err}",
    },
}


def _translate_bank_and_card_phrase(phrase: str, lang: str) -> str:
    """Translate a '{bank_name} {card_name}' or '{card_name}' phrase cleanly."""
    cleaned = (phrase or "").strip()
    if not cleaned:
        return cleaned
    if lang == "en":
        for zh_bank, en_bank in sorted(BANK_NAME_EN.items(), key=lambda x: len(x[0]), reverse=True):
            if cleaned.startswith(zh_bank + " "):
                rest = cleaned[len(zh_bank) + 1 :].strip()
                return f"{en_bank} {translate_card_name(rest, 'en')}"
        return translate_card_name(cleaned, "en")

    # zh-TW direction
    for en_bank, zh_bank in sorted(_BANK_EN_TO_ZH.items(), key=lambda x: len(x[0]), reverse=True):
        if cleaned.lower().startswith(en_bank + " "):
            rest = cleaned[len(en_bank) + 1 :].strip()
            return f"{zh_bank} {canonicalize_card_name(rest)}"
    return canonicalize_card_name(cleaned)


_REASON_ZH_TO_EN: Dict[str, str] = {
    "搜尋結果中找不到合適的銀行官網介紹頁": "No matching official bank card page found in search results",
    "未取得有效網址": "No valid URL found",
    "網址標示停發": "URL marked as discontinued",
}
_REASON_EN_TO_ZH: Dict[str, str] = {v.lower(): k for k, v in _REASON_ZH_TO_EN.items()}


def _translate_scrape_reason(reason: str, lang: str) -> str:
    cleaned = (reason or "").strip()
    if lang == "en":
        if cleaned in _REASON_ZH_TO_EN:
            return _REASON_ZH_TO_EN[cleaned]
        if _contains_cjk(cleaned):
            return "official card page could not be matched automatically"
        return cleaned
    return _REASON_EN_TO_ZH.get(cleaned.lower(), cleaned)


def translate_scrape_log_message(message: str, lang: Optional[str] = None, card_slug: str = "", status: str = "") -> str:
    """Translate historical scrape log messages between zh-TW and en."""
    resolved = normalize_lang(lang)
    text = (message or "").strip()
    if not text:
        return text

    if resolved == "en":
        # Pattern 1: 成功透過 Playwright 解析並更新「{bank_card}」共 {count} 條通路規則
        m = re.match(r"^成功透過 Playwright 解析並更新「(.+?)」共 (\d+) 條通路規則$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            return t_backend("custom_success", "en", bank_name="", card_name=label, count=m.group(2)).replace("' ", "'")

        # Pattern 2: 成功透過 Playwright ({mode}) 解析並更新 {count} 條通路規則
        m = re.match(r"^成功透過 Playwright \((.+?)\) 解析並更新 (\d+) 條通路規則$", text)
        if m:
            return t_backend("scraper_success", "en", mode=m.group(1), count=m.group(2))

        # Pattern 3: 已開啟頁面但未解析出「{card_name}」的結構化回饋規則...
        m = re.match(r"^已開啟頁面但未解析出「(.+?)」的結構化回饋規則.*$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            return t_backend("custom_no_rules", "en", card_name=label)

        # Pattern 4: 頁面已開啟但未解析出結構化回饋規則...
        if text.startswith("頁面已開啟但未解析出結構化回饋規則"):
            return t_backend("scraper_no_rules", "en")

        # Pattern 5: 無法自動定位「{card_name}」的官網頁面（{reason}）...
        m = re.match(r"^無法自動定位「(.+?)」的官網頁面（(.+?)），請於下方補填.*$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            reason = _translate_scrape_reason(m.group(2), "en")
            return t_backend("custom_url_not_found", "en", card_name=label, reason=reason)

        # Pattern 6: 偵測到「{card_name}」已停發或停止申辦（{reason}）...
        m = re.match(r"^偵測到「(.+?)」已停發或停止申辦（(.+?)）.*$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            reason = _translate_scrape_reason(m.group(2), "en")
            return t_backend("custom_discontinued_page", "en", card_name=label, reason=reason)

        # Pattern 7: 偵測到「{bank_card}」疑似已停發或停止申辦（{reason}）...
        m = re.match(r"^偵測到「(.+?)」疑似已停發或停止申辦（(.+?)）.*$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            reason = _translate_scrape_reason(m.group(2), "en")
            return f"Detected that '{label}' appears discontinued ({reason}); skipped update."

        # Pattern 8: 「{card_name}」屬於自訂新卡片...
        m = re.match(r"^「(.+?)」屬於自訂新卡片.*$", text)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            return t_backend("custom_demo_unsupported", "en", card_name=label)

        # Pattern 9: 爬取「{card_name}」失敗：{exc_type}: {err}
        m = re.match(r"^爬取「(.+?)」失敗：([^:]+):\s*(.*)$", text, re.DOTALL)
        if m:
            label = _translate_bank_and_card_phrase(m.group(1), "en")
            err = re.sub(r"\s+", " ", m.group(3)).strip()[:180]
            return t_backend("custom_error", "en", card_name=label, exc_type=m.group(2).strip(), err=err)

        # Pattern 10: 爬取失敗：{exc_type}: {err}
        m = re.match(r"^爬取失敗：([^:]+):\s*(.*)$", text, re.DOTALL)
        if m:
            err = re.sub(r"\s+", " ", m.group(2)).strip()[:180]
            return t_backend("scraper_error", "en", exc_type=m.group(1).strip(), err=err)

        if _contains_cjk(text):
            target = card_slug or "card"
            return f"Playwright scrape log for {target} ({status or 'info'})."
        return text

    # zh-TW direction (translate English-stored logs back to zh-TW)
    m = re.match(r"^Parsed and updated (\d+) channel rules for '(.+?)' via Playwright$", text)
    if m:
        label = _translate_bank_and_card_phrase(m.group(2), "zh-TW")
        return f"成功透過 Playwright 解析並更新「{label}」共 {m.group(1)} 條通路規則"

    m = re.match(r"^Parsed and updated (\d+) channel rules via Playwright \((.+?)\)$", text)
    if m:
        return t_backend("scraper_success", "zh-TW", mode=m.group(2), count=m.group(1))

    m = re.match(r"^Page loaded but no structured reward rules were parsed for '(.+?)' .*$", text)
    if m:
        label = _translate_bank_and_card_phrase(m.group(1), "zh-TW")
        return t_backend("custom_no_rules", "zh-TW", card_name=label)

    if text.startswith("Page loaded but no structured reward rules were parsed ("):
        return t_backend("scraper_no_rules", "zh-TW")

    return text


def translate_scrape_log(log: dict, lang: Optional[str] = None) -> dict:
    """Return a scrape log dict with a localized message field."""
    resolved = normalize_lang(lang)
    translated = dict(log)
    translated["message"] = translate_scrape_log_message(
        log.get("message", ""),
        lang=resolved,
        card_slug=log.get("card_slug", ""),
        status=log.get("status", ""),
    )
    return translated


def t_backend(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """Format a localized backend message string."""
    resolved = normalize_lang(lang)
    template = _MESSAGES.get(resolved, _MESSAGES[DEFAULT_LANG]).get(
        key, _MESSAGES[DEFAULT_LANG].get(key, key)
    )
    return template.format(**kwargs) if kwargs else template
