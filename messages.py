"""
私訊訊息模板庫
每組模板是 list，代表分段發送的多則訊息
{name} = 對方名稱, {group_link} = 群組邀請連結
"""

import random

TEMPLATES = [
    # --- 模板 1：輕鬆打招呼 ---
    [
        "嗨 {name}～你好呀 👋",
        "最近我們有個不錯的社群，裡面會分享一些蠻實用的資訊",
        "有興趣的話可以來看看 {group_link}\n沒興趣也沒關係哦～",
    ],
    # --- 模板 2：直接推薦 ---
    [
        "Hi {name} 你好！",
        "想邀請你加入我們的交流群，裡面有很多實用的分享和討論 💬\n{group_link}",
        "歡迎來看看，有問題隨時問我～",
    ],
    # --- 模板 3：好奇引導 ---
    [
        "{name} 你好～想問一下你對這個領域有興趣嗎？",
        "我們最近組了一個蠻活躍的社群\n大家都會在裡面交流心得",
        "這是群組連結 {group_link}\n歡迎來聊聊 😊",
    ],
    # --- 模板 4：朋友推薦 ---
    [
        "嘿 {name}！",
        "朋友推薦我找你聊聊，覺得你可能會對這個感興趣",
        "我們有個交流群，氛圍很好，來看看吧 👇\n{group_link}",
    ],
    # --- 模板 5：簡短型 ---
    [
        "哈囉 {name} 👋 推薦一個不錯的群給你",
        "{group_link}\n裡面都是志同道合的朋友，歡迎加入～",
    ],
]

EMOJI_VARIANTS = ["👋", "😊", "💬", "🙌", "✨", "🎉"]


def get_personalized_messages(name, group_link):
    """取得一組個人化的訊息"""
    template = random.choice(TEMPLATES)
    rendered = []
    for msg in template:
        text = msg.replace("{name}", name).replace("{group_link}", group_link)
        for emoji in EMOJI_VARIANTS:
            if emoji in text and random.random() > 0.5:
                text = text.replace(emoji, random.choice(EMOJI_VARIANTS))
        rendered.append(text)
    return rendered
