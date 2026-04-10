"""
陌生開發 — 全方位網路搜尋 TG 群組連結
來源：
  1. DuckDuckGo + Bing（多語言多關鍵字）
  2. Google（透過不同搜尋語法）
  3. TG 目錄站（tgstat, combot 等）
  4. 論壇/社群（PTT, Dcard, Twitter, Reddit）
  5. 部落格/內容農場
"""

import asyncio
import csv
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse
import random
import time
from datetime import datetime

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)
DATA_DIR = os.path.join(TOOLKIT_DIR, "data")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

# 已知的群組（不重複搜尋）
KNOWN_FILE = os.path.join(TOOLKIT_DIR, "scraped_groups.json")
RESULT_FILE = os.path.join(TOOLKIT_DIR, "web_discovery_results.json")


# ============================================================
# 搜尋關鍵字（大幅擴充）
# ============================================================

SEARCH_QUERIES = [
    # === 核心：直接搜 t.me 連結 ===
    "t.me 外送茶", "t.me 喝茶 群", "t.me 茶莊",
    "t.me 約砲 台灣", "t.me 約炮群", "t.me 成人交友",
    "t.me 外約", "t.me 茶友", "t.me 老司機",
    "t.me 步兵", "t.me 騎兵", "t.me 客評",
    "t.me 舒壓 按摩", "t.me 油壓",

    # === 地區 ===
    "t.me 台北 外送茶", "t.me 台中 外送茶", "t.me 高雄 外送茶",
    "t.me 新竹 外送", "t.me 桃園 外送", "t.me 台南 外送",
    "t.me 新北 外約",

    # === 搜尋引擎語法（site: 限定） ===
    "site:t.me 外送茶", "site:t.me 約砲", "site:t.me 茶莊",
    "site:t.me 成人 台灣", "site:t.me 老司機",

    # === 論壇搜尋 ===
    "telegram 外送茶 群組 PTT",
    "telegram 約砲 群 Dcard",
    "telegram 茶莊 連結 分享",
    "telegram 外約 推薦 2026",
    "telegram 成人群組 台灣 加入",
    "telegram 老司機 群組 推薦",
    "telegram 深夜群 推薦",

    # === 部落格/內容農場 ===
    "外送茶 telegram 群組 推薦 連結",
    "約砲 telegram 群 連結 2026",
    "台灣 telegram 成人 群組 整理",
    "telegram 福利群 台灣 連結",
    "telegram 18禁 群組 台灣",

    # === 英文搜尋（找華人圈海外群） ===
    "telegram taiwan adult group",
    "telegram taiwan escort group",
    "telegram taiwan dating 18+",

    # === 品牌/茶莊名稱搜尋 ===
    "telegram 極樂", "telegram 貝兒 外送",
    "telegram 娜娜 步兵", "telegram 大神 茶莊",
    "telegram 含碧樓", "telegram 蘋果 茶莊",
    "telegram 薇閣", "telegram 尋春色",

    # === 特殊語法 ===
    "inurl:t.me 外送茶",
    "inurl:t.me 約砲 台灣",
    "\"t.me\" 外送茶 加入",
    "\"t.me\" 茶莊 群組",
]

# TG 目錄站
TG_DIRECTORIES = [
    "https://tgstat.com/search?q={}&type=channel",
    "https://telegramchannels.me/search?q={}",
    "https://combot.org/telegram/top/groups?q={}",
    "https://tdirectory.me/search?q={}",
    "https://tgramsearch.com/search?q={}",
]

DIR_KEYWORDS = [
    "外送茶", "約砲", "成人交友", "老司機", "茶友",
    "深夜群", "外約", "步兵", "茶莊", "18禁",
    "taiwan adult", "taiwan escort",
]


# ============================================================
# 搜尋引擎
# ============================================================

def fetch_url(url, retries=2):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            if i == retries - 1:
                return ""
    return ""


def extract_tg_links(text):
    patterns = [
        r'(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([a-zA-Z0-9_\-]+)',
        r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)',
    ]
    links = set()
    skip = ["proxy", "socks", "share", "addstickers", "addtheme",
            "setlanguage", "bg", "invoice", "boost", "addlist",
            "privacy", "tos", "faq", "dl", "login", "web"]
    for p in patterns:
        for match in re.finditer(p, text):
            link_id = match.group(1)
            if link_id.lower() in skip or len(link_id) < 3:
                continue
            full = match.group(0)
            if "/+" in full or "/joinchat/" in full:
                links.add(f"+{link_id}")
            else:
                links.add(link_id)
    return links


def duckduckgo_search(query):
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    html = fetch_url(url)
    links = set()
    if html:
        urls = re.findall(r'href="([^"]*)"', html)
        for u in urls:
            if "uddg=" in u:
                real_url = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                links.update(extract_tg_links(real_url))
            elif "t.me" in u:
                links.update(extract_tg_links(u))
        links.update(extract_tg_links(html))
    return links


def bing_search(query):
    links = set()
    for page in range(3):  # 搜 3 頁
        first = page * 10 + 1
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&first={first}"
        html = fetch_url(url)
        if html:
            links.update(extract_tg_links(html))
            for u in re.findall(r'href="([^"]*)"', html):
                if "t.me" in u:
                    links.update(extract_tg_links(u))
    return links


def google_search(query):
    """透過 Google 搜尋（可能被擋）"""
    links = set()
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=20"
    html = fetch_url(url)
    if html:
        links.update(extract_tg_links(html))
    return links


def search_directories():
    """搜尋 TG 目錄站"""
    links = set()
    for kw in DIR_KEYWORDS:
        for tmpl in TG_DIRECTORIES:
            url = tmpl.format(urllib.parse.quote(kw))
            html = fetch_url(url)
            if html:
                links.update(extract_tg_links(html))
        time.sleep(1)
    return links


# ============================================================
# 主程式
# ============================================================

async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       陌生開發 — 全方位搜尋 TG 群組             ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print(f"  搜尋關鍵字: {len(SEARCH_QUERIES)} 組")
    print(f"  目錄站: {len(TG_DIRECTORIES)} 個")
    print(f"  目錄關鍵字: {len(DIR_KEYWORDS)} 組")
    print()

    all_links = set()

    # Phase 1: 搜尋引擎
    print("  === Phase 1: 搜尋引擎 ===\n")
    for i, q in enumerate(SEARCH_QUERIES, 1):
        print(f"  [{i:2d}/{len(SEARCH_QUERIES)}] {q[:45]}", end="", flush=True)

        links = set()
        links.update(duckduckgo_search(q))
        links.update(bing_search(q))
        links.update(google_search(q))

        new = links - all_links
        all_links.update(links)

        if new:
            print(f" → +{len(new)} 個")
        else:
            print(f" → 0")

        time.sleep(random.uniform(2, 4))

    # Phase 2: TG 目錄站
    print(f"\n  === Phase 2: TG 目錄站 ===\n")
    print(f"  搜尋中...", end="", flush=True)
    dir_links = search_directories()
    new = dir_links - all_links
    all_links.update(dir_links)
    print(f" → +{len(new)} 個\n")

    print(f"  共找到 {len(all_links)} 個不重複連結\n")

    if not all_links:
        print("  沒有找到連結")
        return

    # Phase 3: 用 TG API 檢查
    print("  === Phase 3: 檢查連結 ===\n")

    from config import API_ID, API_HASH, SESSION_NAME
    from telethon import TelegramClient
    from telethon.tl.types import Channel
    from telethon.tl.functions.channels import GetFullChannelRequest
    from telethon.errors import FloodWaitError, ChannelPrivateError

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    # 已知的群組
    dialogs = await client.get_dialogs()
    known_ids = set()
    for d in dialogs:
        if d.is_group or d.is_channel:
            known_ids.add(d.entity.id)

    results = {"groups": [], "channels": [], "errors": []}
    checked = 0

    for link_id in sorted(all_links):
        if link_id.startswith("+"):
            continue  # 私密連結先跳過

        try:
            entity = await client.get_entity(link_id)
            if not isinstance(entity, Channel):
                continue

            is_mega = getattr(entity, "megagroup", False)
            count = getattr(entity, "participants_count", 0) or 0
            already = entity.id in known_ids
            kind = "👥" if is_mega else "📢"
            status = "已加入" if already else "新的"

            info = {
                "title": entity.title,
                "username": getattr(entity, "username", "") or "",
                "link": link_id,
                "megagroup": is_mega,
                "count": count,
                "already_joined": already,
            }

            if is_mega:
                results["groups"].append(info)
            else:
                results["channels"].append(info)

            if not already:
                print(f"  🆕 {kind} {entity.title[:35]} ({count}人)")

            checked += 1
            await asyncio.sleep(1)

        except FloodWaitError as e:
            print(f"  ⚠️ 限速 {e.seconds}s，等待...")
            await asyncio.sleep(e.seconds + 5)
        except (ChannelPrivateError, Exception):
            pass

    await client.disconnect()

    # 統計
    new_groups = [g for g in results["groups"] if not g["already_joined"]]
    new_channels = [c for c in results["channels"] if not c["already_joined"]]

    print(f"\n  === 結果 ===")
    print(f"  檢查了 {checked} 個連結")
    print(f"  新群組: {len(new_groups)} 個")
    print(f"  新頻道: {len(new_channels)} 個")

    if new_groups:
        print(f"\n  新群組（可撈名單）:")
        for g in sorted(new_groups, key=lambda x: -x["count"]):
            link = f"t.me/{g['username']}" if g["username"] else "(私密)"
            print(f"    👥 {g['title'][:35]} ({g['count']}人) {link}")

    if new_channels:
        print(f"\n  新頻道（可轉發內容）:")
        for c in sorted(new_channels, key=lambda x: -x["count"])[:20]:
            link = f"t.me/{c['username']}" if c["username"] else "(私密)"
            print(f"    📢 {c['title'][:35]} ({c['count']}人) {link}")

    # 儲存結果
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  結果已儲存: {RESULT_FILE}")

    # 詢問是否加入新群組
    if new_groups:
        print(f"\n  要自動加入 {len(new_groups)} 個新群組嗎？")
        try:
            confirm = input("  (y/n): ").strip().lower()
        except EOFError:
            confirm = "y"

        if confirm == "y":
            from telethon.tl.functions.channels import JoinChannelRequest
            from telethon.errors import UserAlreadyParticipantError

            client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
            await client.start()

            joined = 0
            for g in new_groups:
                try:
                    entity = await client.get_entity(g["username"] or g["link"])
                    await client(JoinChannelRequest(entity))
                    print(f"    ✅ 加入: {g['title']}")
                    joined += 1
                except UserAlreadyParticipantError:
                    print(f"    ⏭ 已加入: {g['title']}")
                except FloodWaitError as e:
                    print(f"    ⚠️ 限速 {e.seconds}s")
                    if e.seconds > 120:
                        print(f"    停止加入")
                        break
                    await asyncio.sleep(e.seconds + 5)
                except Exception as e:
                    print(f"    ❌ {g['title']}: {e}")
                await asyncio.sleep(random.uniform(15, 30))

            print(f"\n    共加入 {joined} 個新群組")
            await client.disconnect()

    input("\n按 Enter 返回...")


if __name__ == "__main__":
    asyncio.run(main())
