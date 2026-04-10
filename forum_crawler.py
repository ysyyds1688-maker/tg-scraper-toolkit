"""
論壇/社群爬蟲 — 從成人論壇和社群媒體找 TG 群組連結
不需要 TG API，被限速也能跑

來源：
  1. JKForum（台灣最大成人論壇）
  2. Google 進階搜尋語法（site: 限定論壇）
  3. TG 群組聚合網站
  4. Twitter/X
  5. Reddit
"""

import json
import os
import re
import ssl
import sys
import time
import random
import urllib.request
import urllib.parse

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(TOOLKIT_DIR, "forum_discovered_links.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def fetch_url(url, retries=2):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            if i == retries - 1:
                return ""
    return ""


def extract_tg_links(text):
    patterns = [
        r'(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([a-zA-Z0-9_\-]+)',
        r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{3,})',
    ]
    links = set()
    skip = ["proxy", "socks", "share", "addstickers", "addtheme",
            "setlanguage", "bg", "invoice", "boost", "addlist",
            "privacy", "tos", "faq", "dl", "login", "web", "s",
            "dns", "telegram", "features", "apps", "blog"]
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


def duckduckgo(query):
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    html = fetch_url(url)
    links = set()
    if html:
        for u in re.findall(r'href="([^"]*)"', html):
            if "uddg=" in u:
                real = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                links.update(extract_tg_links(real))
            elif "t.me" in u:
                links.update(extract_tg_links(u))
        links.update(extract_tg_links(html))
    return links


def bing(query, pages=3):
    links = set()
    for page in range(pages):
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&first={page*10+1}"
        html = fetch_url(url)
        if html:
            links.update(extract_tg_links(html))
            for u in re.findall(r'href="([^"]*)"', html):
                if "t.me" in u:
                    links.update(extract_tg_links(u))
    return links


def google(query):
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=30"
    html = fetch_url(url)
    links = set()
    if html:
        links.update(extract_tg_links(html))
    return links


def search_all(query):
    links = set()
    links.update(duckduckgo(query))
    links.update(bing(query))
    links.update(google(query))
    return links


# ============================================================
# 搜尋來源
# ============================================================

def source_1_forums():
    """從論壇搜尋 TG 連結"""
    print("\n  📋 來源 1: 論壇搜尋")
    queries = [
        # JKForum
        "site:jkforum.net t.me",
        "site:jkforum.net telegram 群",
        "site:jkforum.net 外送茶 telegram",
        "site:jkforum.net 約砲 t.me",
        "site:jkforum.net 茶莊 telegram",
        "jkforum telegram 外送茶 t.me",
        "jkf 外送茶 telegram 群組",
        # 卡提諾
        "site:ck101.com t.me",
        "site:ck101.com telegram 外送",
        # PTT
        "site:ptt.cc t.me 外送茶",
        "site:ptt.cc telegram 約砲",
        "site:ptt.cc telegram 成人",
        "ptt sex telegram t.me",
        # Dcard
        "site:dcard.tw t.me 外送",
        "site:dcard.tw telegram 約砲",
        "dcard 西斯 telegram t.me",
    ]

    all_links = set()
    for i, q in enumerate(queries, 1):
        print(f"    [{i:2d}/{len(queries)}] {q[:50]}", end="", flush=True)
        links = search_all(q)
        new = links - all_links
        all_links.update(links)
        print(f" → +{len(new)}") if new else print(" → 0")
        time.sleep(random.uniform(3, 6))

    print(f"    小計: {len(all_links)} 個")
    return all_links


def source_2_google_dorks():
    """Google 進階搜尋語法"""
    print("\n  📋 來源 2: Google 進階搜尋")
    queries = [
        # 精準搜尋
        '"t.me" "外送茶" "群組"',
        '"t.me" "約砲" "台灣"',
        '"t.me" "茶莊" "加入"',
        '"telegram" "外送茶" "連結"',
        '"telegram群" "外送茶" site:*.tw',
        # 特定網站
        "site:medium.com telegram 外送茶 t.me",
        "site:pixnet.net telegram 外送 t.me",
        "site:matters.news telegram 成人 t.me",
        # 年份限定（找最新的）
        '"t.me" 外送茶 群 2025 OR 2026',
        '"t.me" 約砲群 台灣 2025 OR 2026',
        # 列表型文章
        "telegram 群組 推薦 列表 外送茶",
        "telegram 成人 群組 整理 台灣",
        "telegram 18禁 群組 連結 整理",
        "telegram group link taiwan adult",
    ]

    all_links = set()
    for i, q in enumerate(queries, 1):
        print(f"    [{i:2d}/{len(queries)}] {q[:50]}", end="", flush=True)
        links = search_all(q)
        new = links - all_links
        all_links.update(links)
        print(f" → +{len(new)}") if new else print(" → 0")
        time.sleep(random.uniform(3, 6))

    print(f"    小計: {len(all_links)} 個")
    return all_links


def source_3_tg_directories():
    """TG 群組聚合網站"""
    print("\n  📋 來源 3: TG 群組聚合網站")

    directories = {
        "tgstat.com": [
            "https://tgstat.com/search?q={}&type=channel",
            "https://tgstat.com/search?q={}&type=chat",
        ],
        "telegramchannels.me": [
            "https://telegramchannels.me/search?q={}",
        ],
        "combot.org": [
            "https://combot.org/telegram/top/groups?q={}",
        ],
        "tdirectory.me": [
            "https://tdirectory.me/search?q={}",
        ],
        "tgramsearch.com": [
            "https://tgramsearch.com/search?q={}",
        ],
        "hottg.com": [
            "https://hottg.com/search?q={}",
        ],
    }

    keywords = [
        "外送茶", "約砲", "台灣成人", "老司機", "茶友",
        "茶莊", "外約", "步兵", "18禁", "deep night",
        "taiwan escort", "taiwan adult", "taiwan dating",
        "massage taiwan", "台灣 massage",
    ]

    all_links = set()
    for site_name, templates in directories.items():
        site_links = set()
        for kw in keywords:
            for tmpl in templates:
                url = tmpl.format(urllib.parse.quote(kw))
                html = fetch_url(url)
                if html:
                    links = extract_tg_links(html)
                    site_links.update(links)
            time.sleep(1)
        new = site_links - all_links
        all_links.update(site_links)
        print(f"    {site_name}: +{len(new)} 個")

    print(f"    小計: {len(all_links)} 個")
    return all_links


def source_4_social_media():
    """社群媒體搜尋"""
    print("\n  📋 來源 4: 社群媒體")
    queries = [
        # Twitter/X
        "site:twitter.com t.me 外送茶",
        "site:twitter.com t.me 約砲 台灣",
        "site:twitter.com telegram 茶莊",
        "site:x.com t.me 外送茶",
        "site:x.com t.me 台灣 成人",
        # Reddit
        "site:reddit.com t.me taiwan adult",
        "site:reddit.com telegram taiwan escort",
        "site:reddit.com t.me 約砲",
        # YouTube（影片描述裡的連結）
        "site:youtube.com telegram 外送茶 t.me",
        "site:youtube.com telegram 約砲 台灣",
    ]

    all_links = set()
    for i, q in enumerate(queries, 1):
        print(f"    [{i:2d}/{len(queries)}] {q[:50]}", end="", flush=True)
        links = search_all(q)
        new = links - all_links
        all_links.update(links)
        print(f" → +{len(new)}") if new else print(" → 0")
        time.sleep(random.uniform(3, 6))

    print(f"    小計: {len(all_links)} 個")
    return all_links


def source_5_aggregator_sites():
    """群組連結整理網站"""
    print("\n  📋 來源 5: 連結整理網站")
    queries = [
        "telegram 群組 連結 整理 台灣 成人",
        "telegram group links collection taiwan",
        "telegram 外送茶 群組 列表",
        "telegram 約砲 群組 大全",
        "telegram 18+ group taiwan list",
        "telegram 成人 頻道 推薦 2026",
    ]

    all_links = set()
    for i, q in enumerate(queries, 1):
        print(f"    [{i:2d}/{len(queries)}] {q[:50]}", end="", flush=True)
        links = search_all(q)
        new = links - all_links
        all_links.update(links)
        print(f" → +{len(new)}") if new else print(" → 0")
        time.sleep(random.uniform(3, 6))

    # 也直接爬幾個已知的整理頁面
    known_pages = [
        "https://telegramchannels.me/groups/taiwan",
        "https://telegramchannels.me/channels/taiwan",
    ]
    for url in known_pages:
        html = fetch_url(url)
        if html:
            links = extract_tg_links(html)
            new = links - all_links
            all_links.update(links)
            if new:
                print(f"    {url[:40]}: +{len(new)} 個")

    print(f"    小計: {len(all_links)} 個")
    return all_links


# ============================================================
# 主程式
# ============================================================

def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       論壇/社群爬蟲（不需要 TG API）            ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print("  從論壇、搜尋引擎、聚合網站找 TG 群組連結")
    print("  帳號被限速也能跑\n")

    # 載入之前已找到的連結
    existing = set()
    for f in ["discovered_links.json", "forum_discovered_links.json"]:
        fp = os.path.join(TOOLKIT_DIR, f)
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as fh:
                existing.update(json.load(fh))
    print(f"  之前已找到: {len(existing)} 個連結\n")

    all_links = set()

    # 跑 5 個來源
    all_links.update(source_1_forums())
    all_links.update(source_2_google_dorks())
    all_links.update(source_3_tg_directories())
    all_links.update(source_4_social_media())
    all_links.update(source_5_aggregator_sites())

    # 去除已知的
    new_links = all_links - existing
    total = all_links | existing

    print(f"\n  {'='*50}")
    print(f"  總共找到: {len(all_links)} 個連結")
    print(f"  新連結:   {len(new_links)} 個")
    print(f"  累計:     {len(total)} 個")

    # 儲存
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(total), f, ensure_ascii=False, indent=2)
    print(f"\n  已儲存: {RESULT_FILE}")

    if new_links:
        print(f"\n  新找到的連結:")
        for link in sorted(new_links)[:30]:
            prefix = "t.me/+" if link.startswith("+") else "t.me/"
            print(f"    {prefix}{link}")
        if len(new_links) > 30:
            print(f"    ...還有 {len(new_links)-30} 個")

    print(f"\n  下一步: 等限速解除後跑 web_discovery.py Phase 3 檢查這些連結")

    input("\n按 Enter 返回...")


if __name__ == "__main__":
    main()
