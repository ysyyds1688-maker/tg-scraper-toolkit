"""
大量搜尋 Telegram 上同類型可抓取的群組（megagroup）
用大量關鍵字組合搜尋，找到後自動檢測是否可抓取成員
"""

import asyncio
import csv
import os
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, get_scraped_group_ids
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch, Channel
from telethon.errors import ChatAdminRequiredError, FloodWaitError


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 大量關鍵字 - 各種可能的搜尋詞
KEYWORDS = [
    # === 外送茶核心 ===
    "外送茶", "外送茶討論", "外送茶群", "外送茶推薦",
    "喝茶", "喝茶群", "喝茶討論", "喝茶推薦",
    "品茶", "品茶群", "品茶討論",
    "茶友", "茶友討論", "茶友群", "茶客", "茶客群",
    "茶訊", "魚訊", "茶莊", "茶行",
    "叫茶", "點茶", "約茶", "找茶",
    "叫小姐", "找小姐", "約小姐",
    "個工", "個人工作室", "個工推薦",
    # === 約砲核心 ===
    "約砲", "約炮", "約砲群", "約炮群",
    "約砲討論", "約炮討論", "砲友", "炮友",
    "約愛", "約愛群", "一夜情", "一夜情群",
    "ONS", "FWB", "炮群", "砲群",
    "打砲", "打炮", "開房", "開房群",
    # === 外約/外送 ===
    "外約", "外約群", "外約討論", "外約推薦",
    "外送", "外送妹", "外送群",
    "出差", "出差群", "出差約",
    # === 地區 + 外送茶 ===
    "台北外送茶", "台中外送茶", "高雄外送茶",
    "新竹外送茶", "桃園外送茶", "台南外送茶",
    "新北外送茶", "彰化外送茶",
    # === 地區 + 約 ===
    "台北約", "台中約", "高雄約", "新竹約",
    "桃園約", "台南約", "新北約",
    "台北約砲", "台中約砲", "高雄約砲",
    "台北外約", "台中外約", "高雄外約",
    # === 地區 + 茶 ===
    "台北茶", "台中茶", "高雄茶", "新竹茶",
    "桃園茶", "台南茶", "新北茶",
    "台北喝茶", "台中喝茶", "高雄喝茶",
    # === 術語/暗語 ===
    "步兵", "騎兵", "無碼", "素人",
    "本土", "本土妹", "台妹", "台灣妹",
    "紅牌", "班表", "選妹", "看照選妹",
    "試車", "開箱", "評價", "心得",
    "體驗", "客評", "分享",
    # === 群組風格名稱 ===
    "俱樂部",
    "深夜", "深夜群", "深夜討論", "深夜旅遊",
    "老司機", "老司機群", "司機群",
    "紳士", "紳士群", "紳士俱樂部",
    "夜生活", "夜生活群", "夜店",
    "成人", "成人群", "成人討論", "成人交友",
    "福利", "福利群", "福利社",
    "車友", "開車", "開車群",
    "兼職", "兼差", "兼職妹", "兼職群",
    "限制級", "18禁", "色群", "黃群",
    # === 交友/社交 ===
    "交友", "交友群", "台灣交友", "寂寞交友",
    "約會", "約會群", "單身", "單身群",
    "聊天", "聊天群", "台灣聊天",
    "寂寞", "無聊", "深夜聊天",
    # === 按摩/舒壓 ===
    "按摩", "按摩群", "舒壓", "舒壓群",
    "SPA", "油壓", "半套", "全套",
    "指油壓", "養生館", "個人按摩",
    # === 英文 ===
    "Taiwan adult", "Taiwan dating", "Taiwan chat",
    "escort Taiwan", "massage Taiwan", "Taiwan escort",
    "Taipei group", "Taichung group", "Kaohsiung group",
    "Taiwan hookup", "Taiwan ONS", "Taiwan FWB",
    "Taipei dating", "Taichung dating",
    # === 台灣通用群組（大量台灣用戶）===
    "台灣", "台灣群", "台灣群組", "台灣人",
    "台北", "台中", "高雄", "新竹", "桃園", "台南",
    "新北", "彰化", "嘉義", "屏東", "花蓮", "基隆",
    "淡水", "板橋", "三重", "中壢",
    # === 生活/興趣 ===
    "美食", "美食群", "台灣美食",
    "旅遊", "旅遊群", "台灣旅遊", "背包客",
    "投資", "投資群", "股票", "股票群", "加密貨幣",
    "比特幣", "虛擬貨幣", "幣圈", "NFT",
    "打工", "打工群", "兼職", "求職", "找工作",
    "租屋", "租房", "房屋", "買房",
    "二手", "二手交易", "買賣", "拍賣",
    "代購", "團購", "團購群",
    # === 娛樂 ===
    "電影", "電影群", "追劇", "美劇", "韓劇", "日劇",
    "動漫", "動漫群", "漫畫", "番", "ACG",
    "遊戲", "遊戲群", "手遊", "電競",
    "原神", "LOL", "PUBG", "寶可夢",
    "音樂", "音樂群", "K-pop", "JPOP",
    "貼圖", "桌布", "迷因",
    # === 社群/討論 ===
    "PTT", "Dcard", "靠北", "八卦",
    "政治", "時事", "新聞",
    "命理", "星座", "塔羅", "占卜",
    "讀書", "書友", "閱讀",
    "狼人殺", "桌遊",
    "寵物", "貓", "狗",
    "健身", "運動", "跑步", "籃球",
    # === 技術/工作 ===
    "工程師", "程式", "coding", "Python",
    "設計", "UI", "前端", "後端",
    "行銷", "SEO", "電商",
    "自媒體", "YouTube", "直播",
]


async def search_and_collect(client):
    """用所有關鍵字搜尋，收集不重複的群組"""
    all_found = {}  # id -> (entity, found_by_keyword)

    for i, kw in enumerate(KEYWORDS):
        print(f"  [{i+1}/{len(KEYWORDS)}] 搜尋: '{kw}'", end="", flush=True)
        try:
            result = await client(SearchRequest(q=kw, limit=100))
            new = 0
            for chat in result.chats:
                if isinstance(chat, Channel) and chat.id not in all_found:
                    all_found[chat.id] = (chat, kw)
                    new += 1
            found = len([c for c in result.chats if isinstance(c, Channel)])
            if found > 0:
                print(f" → {found} 個結果，新增 {new} 個")
            else:
                print(f" → 0")
        except FloodWaitError as e:
            print(f" → 限速! 等待 {e.seconds} 秒...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f" → 錯誤: {type(e).__name__}")

        await asyncio.sleep(1.2)  # 避免限速

    return all_found


async def check_scrapable(client, entity):
    """檢查是否為可抓取的 megagroup"""
    if not getattr(entity, "megagroup", False):
        return False, "頻道", 0, 0

    try:
        full = await client(GetFullChannelRequest(entity))
        can_view = getattr(full.full_chat, "can_view_participants", False)
        count = getattr(full.full_chat, "participants_count", 0)

        if not can_view:
            return False, f"禁止查看({count}人)", count, 0

        test = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=0,
            limit=10,
            hash=0,
        ))

        ratio = test.count / count if count > 0 else 0
        if test.count >= 50:
            return True, f"可抓取({test.count}/{count}人, {ratio:.0%})", count, test.count
        else:
            return False, f"太少({test.count}/{count}人)", count, test.count

    except ChatAdminRequiredError:
        return False, "需管理員", 0, 0
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False, "限速", 0, 0
    except Exception as e:
        return False, f"{type(e).__name__}", 0, 0


async def scrape_members(client, entity):
    """抓取成員"""
    members = []
    seen = set()
    offset = 0

    while True:
        try:
            participants = await client(GetParticipantsRequest(
                channel=entity,
                filter=ChannelParticipantsSearch(""),
                offset=offset,
                limit=200,
                hash=0,
            ))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            continue
        except Exception:
            break

        if not participants.users:
            break

        for user in participants.users:
            if user.id not in seen:
                seen.add(user.id)
                members.append({
                    "user_id": user.id,
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "phone": user.phone or "",
                    "is_bot": user.bot or False,
                    "source_group": entity.title,
                    "source_group_id": entity.id,
                })

        offset += len(participants.users)
        if offset >= participants.count:
            break

    return members


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Phase 1: 大量搜尋
    print(f"Phase 1: 用 {len(KEYWORDS)} 個關鍵字搜尋\n")
    all_found = await search_and_collect(client)
    print(f"\n共找到 {len(all_found)} 個不重複群組/頻道\n")

    # Phase 2: 篩選可抓取的
    print("Phase 2: 逐一檢查是否可抓取\n")
    scrapable = []
    report = []

    for i, (gid, (entity, keyword)) in enumerate(all_found.items()):
        is_mega = "群組" if getattr(entity, "megagroup", False) else "頻道"
        count = getattr(entity, "participants_count", 0) or 0
        print(f"  [{i+1}/{len(all_found)}] {entity.title[:40]:<40s}", end=" ", flush=True)

        ok, status, total, scrapable_count = await check_scrapable(client, entity)

        if ok:
            print(f"✓ {status}")
            scrapable.append(entity)
        else:
            print(f"✗ {status}")

        # 組連結
        username = getattr(entity, "username", None)
        if username:
            link = f"https://t.me/{username}"
        else:
            link = f"https://t.me/c/{gid}"

        report.append({
            "group_id": gid,
            "title": entity.title,
            "link": link,
            "type": is_mega,
            "total_members": total,
            "scrapable_members": scrapable_count,
            "status": status,
            "found_by": keyword,
        })

        await asyncio.sleep(0.5)

    # 儲存報告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"search_report_{timestamp}.csv")
    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)
    print(f"\n搜尋報告已儲存: {report_path}")

    print(f"\n{'='*60}")
    print(f"結果: 找到 {len(scrapable)} 個可抓取的群組 (共搜尋 {len(all_found)} 個)\n")

    if not scrapable:
        print("沒有找到可抓取的群組")
        await client.disconnect()
        return

    for e in scrapable:
        count = getattr(e, "participants_count", "?")
        print(f"  ✓ {e.title} ({count} 人)")

    confirm = input(f"\n開始爬取這 {len(scrapable)} 個群組？(y/n): ").strip().lower()
    if confirm != "y":
        await client.disconnect()
        return

    # Phase 3: 批次爬取
    scraped_ids = get_scraped_group_ids()
    print(f"\n已爬過的群組: {len(scraped_ids)} 個")
    print(f"\nPhase 3: 開始爬取\n")
    all_members = []

    for entity in scrapable:
        if str(entity.id) in scraped_ids:
            print(f"  ⏭ 已爬過，跳過: {entity.title}")
            continue
        print(f"  📥 {entity.title}...", end="", flush=True)
        try:
            members = await scrape_members(client, entity)
            all_members.extend(members)
            print(f" {len(members)} 位")
        except Exception as e:
            print(f" 失敗: {e}")
        await asyncio.sleep(1)

    if all_members:
        seen = set()
        unique = []
        for m in all_members:
            if m["user_id"] not in seen:
                seen.add(m["user_id"])
                unique.append(m)

        filepath = os.path.join(OUTPUT_DIR, f"mass_search_members_{timestamp}.csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_members[0].keys())
            writer.writeheader()
            writer.writerows(unique)

        print(f"\n{'='*60}")
        print(f"完成! 共 {len(unique)} 位不重複成員")
        print(f"儲存至: {filepath}")

        # 自動合併去重
        print("\n自動合併去重中...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])
    else:
        print("\n沒有抓到任何成員")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
