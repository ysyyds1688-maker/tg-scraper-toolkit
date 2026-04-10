"""
關聯分析模組
1. 掃描群組訊息，找出「轉發自」特定頻道的訊息
2. 記錄轉發者的 User ID、Username、轉發次數
3. 比對不同群組中的發言頻率，找出核心推廣者
4. 輸出 CSV 報告
"""

import asyncio
import csv
import os
import random
import sys
from datetime import datetime
from collections import defaultdict

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient


async def analyze_groups(scan_limit=500):
    """掃描所有群組，分析轉發關聯"""

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"  ✅ 登入: {me.first_name}\n")

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if getattr(d.entity, "megagroup", False)]

    # 資料結構
    # user_id -> {username, first_name, forward_count, forward_sources: {channel: count}, groups_active: set, total_messages}
    users = defaultdict(lambda: {
        "username": "",
        "first_name": "",
        "last_name": "",
        "forward_count": 0,
        "forward_sources": defaultdict(int),
        "groups_active": set(),
        "total_messages": 0,
    })

    # 頻道被轉發次數
    channel_forwards = defaultdict(int)

    print(f"  掃描 {len(groups)} 個群組...\n")

    for d in groups:
        entity = d.entity
        title = d.title
        print(f"  📥 {title[:40]}", end="", flush=True)

        msg_count = 0
        try:
            async for msg in client.iter_messages(entity, limit=scan_limit):
                msg_count += 1

                if not msg.sender_id:
                    continue

                uid = msg.sender_id
                sender = msg.sender

                # 記錄用戶基本資料
                if sender:
                    if not users[uid]["username"]:
                        users[uid]["username"] = getattr(sender, "username", "") or ""
                    if not users[uid]["first_name"]:
                        users[uid]["first_name"] = getattr(sender, "first_name", "") or ""
                    if not users[uid]["last_name"]:
                        users[uid]["last_name"] = getattr(sender, "last_name", "") or ""

                users[uid]["groups_active"].add(title)
                users[uid]["total_messages"] += 1

                # 檢查是否為轉發訊息
                if msg.forward:
                    fwd = msg.forward
                    source_name = ""

                    if fwd.chat:
                        source_name = getattr(fwd.chat, "title", "") or ""
                    elif fwd.sender:
                        source_name = (
                            (getattr(fwd.sender, "first_name", "") or "")
                            + " " +
                            (getattr(fwd.sender, "last_name", "") or "")
                        ).strip()

                    if source_name:
                        users[uid]["forward_count"] += 1
                        users[uid]["forward_sources"][source_name] += 1
                        channel_forwards[source_name] += 1

                # 隨機延遲模擬真人
                if msg_count % 100 == 0:
                    await asyncio.sleep(random.uniform(0.5, 1.5))

        except Exception as e:
            print(f" ❌ {e}")
            continue

        print(f" ({msg_count} 則)")
        await asyncio.sleep(random.uniform(1.5, 3.5))

    await client.disconnect()

    # === 分析結果 ===

    # 1. 核心推廣者（轉發次數 >= 3）
    promoters = []
    for uid, data in users.items():
        if data["forward_count"] >= 3:
            top_source = max(data["forward_sources"].items(), key=lambda x: x[1]) if data["forward_sources"] else ("", 0)
            promoters.append({
                "user_id": uid,
                "username": data["username"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "forward_count": data["forward_count"],
                "top_forward_source": top_source[0],
                "top_forward_count": top_source[1],
                "groups_active": len(data["groups_active"]),
                "groups_list": "; ".join(list(data["groups_active"])[:5]),
                "total_messages": data["total_messages"],
            })

    promoters.sort(key=lambda x: -x["forward_count"])

    # 2. 跨群活躍用戶（出現在 3 個以上群組）
    cross_group = []
    for uid, data in users.items():
        if len(data["groups_active"]) >= 3:
            cross_group.append({
                "user_id": uid,
                "username": data["username"],
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "groups_active": len(data["groups_active"]),
                "groups_list": "; ".join(list(data["groups_active"])[:5]),
                "total_messages": data["total_messages"],
                "forward_count": data["forward_count"],
            })

    cross_group.sort(key=lambda x: -x["groups_active"])

    # === 輸出 CSV ===
    os.makedirs(os.path.join(TOOLKIT_DIR, "名單輸出"), exist_ok=True)

    # 核心推廣者
    if promoters:
        fp = os.path.join(TOOLKIT_DIR, "名單輸出", "核心推廣者.csv")
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=promoters[0].keys())
            w.writeheader()
            w.writerows(promoters)
        print(f"\n  📊 核心推廣者: {len(promoters)} 位 → 名單輸出/核心推廣者.csv")
    else:
        print(f"\n  📊 核心推廣者: 0 位")

    # 跨群活躍用戶
    if cross_group:
        fp = os.path.join(TOOLKIT_DIR, "名單輸出", "跨群活躍用戶.csv")
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cross_group[0].keys())
            w.writeheader()
            w.writerows(cross_group)
        print(f"  📊 跨群活躍用戶: {len(cross_group)} 位 → 名單輸出/跨群活躍用戶.csv")

    # 被轉發最多的頻道
    if channel_forwards:
        print(f"\n  📢 被轉發最多的頻道/用戶:")
        for name, count in sorted(channel_forwards.items(), key=lambda x: -x[1])[:20]:
            print(f"    {count:>4} 次 | {name[:45]}")

    # 總結
    print(f"\n  📊 總結:")
    print(f"     掃描群組: {len(groups)} 個")
    print(f"     用戶總數: {len(users)} 位")
    print(f"     核心推廣者: {len(promoters)} 位（轉發 ≥ 3 次）")
    print(f"     跨群活躍: {len(cross_group)} 位（≥ 3 個群組）")


async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       關聯分析                                ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print("  分析群組中的轉發關聯，找出核心推廣者和跨群活躍用戶")
    print("  純被動讀取，不發送任何訊息\n")

    limit_input = input("  每群掃描幾則訊息？(預設 500, 0=全部): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else 500
    if limit == 0:
        limit = None

    await analyze_groups(scan_limit=limit)

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
