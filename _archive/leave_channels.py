"""
自動退出頻道（broadcast）和不需要的群組，騰出加入名額
Telegram 限制每個帳號最多加入約 500 個群組/頻道
"""

import asyncio
import sys

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.types import Channel
from telethon.errors import FloodWaitError


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print("正在載入所有群組/頻道...\n")
    dialogs = await client.get_dialogs()

    channels = []    # 頻道（broadcast）
    megagroups = []  # 超級群組
    others = []      # 其他

    for d in dialogs:
        if not (d.is_group or d.is_channel):
            continue
        entity = d.entity
        if isinstance(entity, Channel):
            if entity.broadcast:
                channels.append(d)
            elif entity.megagroup:
                megagroups.append(d)
            else:
                others.append(d)
        else:
            others.append(d)

    total = len(channels) + len(megagroups) + len(others)
    print(f"總數: {total} 個")
    print(f"  📢 頻道: {len(channels)} 個")
    print(f"  👥 群組: {len(megagroups)} 個")
    print(f"  📎 其他: {len(others)} 個")
    print()

    # 選擇退出模式
    print("退出模式：")
    print("  [1] 只退出所有頻道 (📢)")
    print("  [2] 手動選擇要保留的，其餘退出")
    print("  [3] 退出指定群組/頻道")
    print()

    mode = input("選擇 (1/2/3): ").strip()

    to_leave = []

    if mode == "1":
        to_leave = channels
        print(f"\n即將退出 {len(to_leave)} 個頻道：")
        for d in to_leave:
            count = getattr(d.entity, "participants_count", 0) or 0
            print(f"  📢 {d.title} ({count} 人)")

    elif mode == "2":
        print("\n所有群組/頻道：")
        all_groups = channels + megagroups + others
        for i, d in enumerate(all_groups):
            kind = "📢" if getattr(d.entity, "broadcast", False) else "👥"
            count = getattr(d.entity, "participants_count", 0) or 0
            print(f"  [{i+1:3d}] {kind} {d.title} ({count} 人)")

        print(f"\n輸入要【保留】的編號（逗號分隔），其餘全部退出：")
        keep_input = input("> ").strip()
        if keep_input:
            keep_indices = set(int(n.strip()) - 1 for n in keep_input.split(","))
        else:
            keep_indices = set()

        for i, d in enumerate(all_groups):
            if i not in keep_indices:
                to_leave.append(d)

        print(f"\n即將退出 {len(to_leave)} 個，保留 {len(keep_indices)} 個")

    elif mode == "3":
        all_groups = channels + megagroups + others
        for i, d in enumerate(all_groups):
            kind = "📢" if getattr(d.entity, "broadcast", False) else "👥"
            count = getattr(d.entity, "participants_count", 0) or 0
            print(f"  [{i+1:3d}] {kind} {d.title} ({count} 人)")

        print(f"\n輸入要【退出】的編號（逗號分隔）：")
        leave_input = input("> ").strip()
        if leave_input:
            leave_indices = [int(n.strip()) - 1 for n in leave_input.split(",")]
            to_leave = [all_groups[i] for i in leave_indices if 0 <= i < len(all_groups)]

    else:
        print("無效選擇")
        await client.disconnect()
        return

    if not to_leave:
        print("沒有要退出的")
        await client.disconnect()
        return

    confirm = input(f"\n確認退出 {len(to_leave)} 個群組/頻道？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        await client.disconnect()
        return

    # 開始退出
    print(f"\n開始退出...\n")
    success = 0
    fail = 0

    for d in to_leave:
        kind = "📢" if getattr(d.entity, "broadcast", False) else "👥"
        print(f"  退出: {kind} {d.title}...", end="", flush=True)
        try:
            await client(LeaveChannelRequest(d.entity))
            print(" ✓")
            success += 1
        except FloodWaitError as e:
            print(f" 限速 {e.seconds}秒")
            await asyncio.sleep(e.seconds)
            try:
                await client(LeaveChannelRequest(d.entity))
                print(" ✓ (重試成功)")
                success += 1
            except Exception:
                print(" ✗")
                fail += 1
        except Exception as e:
            print(f" ✗ ({type(e).__name__})")
            fail += 1
        await asyncio.sleep(2)

    print(f"\n完成! 成功退出 {success} 個，失敗 {fail} 個")
    print(f"目前可用名額增加了約 {success} 個")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
