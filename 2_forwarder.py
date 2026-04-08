"""
Telegram 訊息轉發工具
功能：
  1. 即時監聽 - 來源群組有新訊息就自動轉發到目標頻道
  2. 歷史批量轉發 - 一次性把群組的歷史訊息轉發到頻道
"""

import asyncio
import os
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, TARGET_CHANNEL
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError


# ============================================================
# 工具函式
# ============================================================

async def list_groups(client):
    """列出所有群組/頻道供選擇"""
    dialogs = await client.get_dialogs()
    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)

    print(f"\n{'':>4} {'名稱':<45} {'類型':<10} {'成員':>8}")
    print("-" * 75)

    for i, d in enumerate(groups):
        entity = d.entity
        is_broadcast = getattr(entity, "broadcast", False)
        is_mega = getattr(entity, "megagroup", False)
        count = getattr(entity, "participants_count", 0) or 0
        icon = "📢" if is_broadcast else "👥" if is_mega else "💬"
        type_str = "頻道" if is_broadcast else "超級群組" if is_mega else "群組"
        print(f"  [{i+1:3d}] {icon} {d.title[:42]:<42s} {type_str:<10} {count:>6d} 人")

    return groups


async def select_groups(groups, prompt="選擇群組編號（逗號分隔，如 1,3,5）: "):
    """讓用戶選擇多個群組"""
    nums = input(prompt).strip()
    indices = [int(n.strip()) - 1 for n in nums.split(",")]
    selected = [groups[i] for i in indices if 0 <= i < len(groups)]
    return selected


async def get_target(client, target_channel):
    """取得目標頻道實體"""
    if not target_channel:
        target_channel = input("\n輸入目標頻道（username 或 ID 或連結）: ").strip()

    if target_channel.lstrip("-").isdigit():
        target_channel = int(target_channel)

    entity = await client.get_entity(target_channel)
    print(f"✅ 目標頻道: {entity.title}")
    return entity


# ============================================================
# 模式 1：即時監聽轉發
# ============================================================

async def mode_realtime(client):
    """即時監聽來源群組，自動轉發到目標頻道"""
    groups = await list_groups(client)
    sources = await select_groups(groups, "\n選擇要監聽的來源群組（逗號分隔）: ")

    if not sources:
        print("未選擇任何群組")
        return

    target = await get_target(client, TARGET_CHANNEL)

    source_ids = [s.entity.id for s in sources]
    source_names = {s.entity.id: s.title for s in sources}

    print(f"\n即時監聽中... (Ctrl+C 停止)")
    print(f"來源: {', '.join(s.title for s in sources)}")
    print(f"目標: {target.title}")
    print("-" * 50)

    count = 0

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count
        try:
            await client.forward_messages(target, event.message)
            count += 1
            source_name = source_names.get(event.chat_id, "未知")
            time_str = datetime.now().strftime("%H:%M:%S")
            preview = (event.text or "[媒體]")[:50]
            print(f"  [{time_str}] #{count} {source_name} → {preview}")
        except FloodWaitError as e:
            print(f"  ⚠️  限速 {e.seconds}s，等待中...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"  ❌ 轉發失敗: {e}")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print(f"\n\n停止監聽，共轉發 {count} 則訊息")


# ============================================================
# 模式 2：歷史批量轉發
# ============================================================

async def mode_batch(client):
    """批量轉發歷史訊息"""
    groups = await list_groups(client)
    sources = await select_groups(groups, "\n選擇要轉發的來源群組（逗號分隔）: ")

    if not sources:
        print("未選擇任何群組")
        return

    target = await get_target(client, TARGET_CHANNEL)

    # 設定數量
    limit_input = input("\n每個群組轉發幾則訊息？(0=全部, 預設 100): ").strip()
    limit = int(limit_input) if limit_input else 100
    if limit == 0:
        limit = None

    print(f"\n即將從 {len(sources)} 個群組轉發訊息到 {target.title}")
    confirm = input("確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return

    total = 0
    for source in sources:
        print(f"\n📥 轉發: {source.title}")
        count = 0
        try:
            messages = []
            async for msg in client.iter_messages(source.entity, limit=limit):
                messages.append(msg)

            # 從舊到新轉發
            messages.reverse()

            for msg in messages:
                try:
                    await client.forward_messages(target, msg)
                    count += 1
                    if count % 50 == 0:
                        print(f"    已轉發 {count} 則...")
                    await asyncio.sleep(0.5)  # 避免限速
                except FloodWaitError as e:
                    print(f"    ⚠️  限速 {e.seconds}s，等待中...")
                    await asyncio.sleep(e.seconds)
                    await client.forward_messages(target, msg)
                    count += 1
                except Exception as e:
                    pass  # 跳過無法轉發的訊息

            print(f"    ✅ 完成: {count} 則")
            total += count

        except Exception as e:
            print(f"    ❌ 失敗: {e}")

    print(f"\n{'='*50}")
    print(f"全部完成! 共轉發 {total} 則訊息")


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  Telegram 訊息轉發工具")
    print("=" * 55)
    print()
    print("  [1] 即時監聽 - 新訊息自動轉發")
    print("  [2] 歷史批量轉發")
    print()

    mode = input("選擇模式 (1/2): ").strip()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"\n✅ 登入: {me.first_name} (@{me.username})")

    try:
        if mode == "1":
            await mode_realtime(client)
        elif mode == "2":
            await mode_batch(client)
        else:
            print("無效選擇")
    except KeyboardInterrupt:
        print("\n\n使用者中斷")
    finally:
        await client.disconnect()
        print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())
