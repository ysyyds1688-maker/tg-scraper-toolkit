"""診斷兩個群組的差異"""
import asyncio
from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import ChatAdminRequiredError



async def diagnose_group(client, dialog):
    entity = dialog.entity
    print(f"\n{'='*60}")
    print(f"群組名稱: {dialog.title}")
    print(f"群組 ID: {entity.id}")
    print(f"-" * 60)

    # 基本屬性
    print(f"  類型: {'超級群組/頻道 (Channel)' if hasattr(entity, 'megagroup') else '普通群組 (Chat)'}")
    if hasattr(entity, "megagroup"):
        print(f"  megagroup: {entity.megagroup}")
    if hasattr(entity, "broadcast"):
        print(f"  broadcast (頻道): {entity.broadcast}")
    if hasattr(entity, "participants_count"):
        print(f"  成員數: {entity.participants_count}")

    # 取得完整資訊
    try:
        full = await client(GetFullChannelRequest(entity))
        full_chat = full.full_chat
        print(f"  hidden_prehistory: {getattr(full_chat, 'hidden_prehistory', 'N/A')}")
        print(f"  can_view_participants: {getattr(full_chat, 'can_view_participants', 'N/A')}")
        print(f"  can_set_username: {getattr(full_chat, 'can_set_username', 'N/A')}")
        print(f"  participants_count: {getattr(full_chat, 'participants_count', 'N/A')}")
        print(f"  admins_count: {getattr(full_chat, 'admins_count', 'N/A')}")
        print(f"  online_count: {getattr(full_chat, 'online_count', 'N/A')}")
    except Exception as e:
        print(f"  GetFullChannel 失敗: {e}")

    # 嘗試抓成員
    try:
        participants = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=0,
            limit=10,
            hash=0,
        ))
        print(f"  抓取測試: 成功! 取得 {len(participants.users)} 位 (共 {participants.count} 位)")
    except ChatAdminRequiredError:
        print(f"  抓取測試: 失敗 (ChatAdminRequiredError)")
    except Exception as e:
        print(f"  抓取測試: 失敗 ({e})")


async def main():
    client = TelegramClient("tg_session", API_ID, API_HASH)
    await client.start()

    dialogs = await client.get_dialogs()
    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)

    target_indices = [6, 8, 9, 10, 12, 13, 16]
    for idx in target_indices:
        if idx <= len(groups):
            await diagnose_group(client, groups[idx - 1])

    await client.disconnect()

asyncio.run(main())
