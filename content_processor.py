"""
內容處理模組
1. 圖片指紋混淆 — 微調圖片讓 MD5 改變，視覺無差異
2. 文案清洗 — 移除原始連結/帳號 + 同義詞隨機替換
"""

import os
import random
import re

from PIL import Image, ImageEnhance


# ============================================================
# 1. 圖片指紋混淆
# ============================================================

def obfuscate_image(filepath):
    """
    微調圖片讓 MD5 改變，但視覺上看不出差異
    隨機進行：裁切邊緣 1-2px / 調整亮度 / 調整飽和度 / 微旋轉
    """
    try:
        img = Image.open(filepath)

        # 隨機選 2-3 種處理
        ops = random.sample(["crop", "brightness", "saturation", "quality"], k=random.randint(2, 3))

        for op in ops:
            if op == "crop":
                # 裁切邊緣 1-2px
                w, h = img.size
                left = random.randint(0, 2)
                top = random.randint(0, 2)
                right = w - random.randint(0, 2)
                bottom = h - random.randint(0, 2)
                if right > left + 10 and bottom > top + 10:
                    img = img.crop((left, top, right, bottom))

            elif op == "brightness":
                # 亮度微調 +/- 1-2%
                factor = random.uniform(0.98, 1.02)
                img = ImageEnhance.Brightness(img).enhance(factor)

            elif op == "saturation":
                # 飽和度微調 +/- 1-2%
                factor = random.uniform(0.98, 1.02)
                img = ImageEnhance.Color(img).enhance(factor)

            elif op == "quality":
                # 對比度微調
                factor = random.uniform(0.99, 1.01)
                img = ImageEnhance.Contrast(img).enhance(factor)

        # 儲存（JPEG 品質隨機 88-95，改變壓縮指紋）
        quality = random.randint(88, 95)
        if filepath.lower().endswith(".png"):
            img.save(filepath, "PNG")
        else:
            img = img.convert("RGB")
            img.save(filepath, "JPEG", quality=quality)

        return True
    except Exception as e:
        return False


# ============================================================
# 2. 文案清洗 + 同義詞替換
# ============================================================

# 同義詞表（隨機替換增加唯一性）
SYNONYM_MAP = {
    "溫柔": ["貼心", "細心", "親切", "溫暖", "柔情"],
    "漂亮": ["美麗", "好看", "迷人", "動人", "亮眼"],
    "身材好": ["身材棒", "曲線優美", "體態迷人", "身段好"],
    "服務好": ["服務到位", "服務滿分", "服務超讚", "服務優質"],
    "推薦": ["大推", "力推", "強推", "必約"],
    "配合度高": ["配合度滿分", "超配合", "很配合"],
    "年輕": ["青春", "活力", "朝氣"],
    "性感": ["火辣", "撩人", "誘惑", "嫵媚"],
    "甜美": ["甜甜的", "可愛", "清新", "萌萌的"],
    "好評": ["五星好評", "強力好評", "滿分好評"],
    "約": ["預約", "安排"],
    "妹妹": ["佳麗", "女孩", "美眉"],
    "小姐": ["佳麗", "女孩", "小姊姊"],
    "外送": ["到府", "外出"],
    "CP值高": ["超值", "划算", "物超所值"],
    "回沖率高": ["回訪率高", "很多人回約", "常客多"],
    "顏值高": ["顏值爆表", "顏值滿分", "長得很正"],
}

# 要完全移除的模式
REMOVE_PATTERNS = [
    r"@[\w]{3,}",                          # @username
    r"https?://t\.me/\+?[\w-]+/?[\w]*",    # t.me 連結
    r"https?://telegram\.me/[\w-]+",        # telegram.me
    r"https?://line\.me/[\S]+",             # LINE 連結
    r"https?://[\w.-]+\.(?:com|net|org|vip|top)/[\S]*",  # 一般網址
    r"(?:LINE|line|賴|加賴|密賴)[：:\s]*[\w@]+",  # LINE ID
    r"(?:Gleezy|gleezy)[：:\s]*[\w]+",     # Gleezy 帳號
    r"(?:微信|WeChat|wechat)[：:\s]*[\w]+", # 微信
]


def clean_text(text):
    """
    清洗文案：
    1. 移除所有原始連結/帳號
    2. 同義詞隨機替換
    回傳清洗後的文字
    """
    if not text:
        return text

    # Step 1: 移除連結和帳號
    for pattern in REMOVE_PATTERNS:
        text = re.sub(pattern, "", text)

    # 清除多餘空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # Step 2: 同義詞隨機替換
    for word, synonyms in SYNONYM_MAP.items():
        if word in text:
            # 50% 機率替換（不是每次都換，更自然）
            if random.random() > 0.5:
                replacement = random.choice(synonyms)
                text = text.replace(word, replacement, 1)

    return text


def process_content(text, image_path=None):
    """
    一次處理文案 + 圖片
    text: 原始文案
    image_path: 圖片路徑（選填）
    回傳: (處理後文案, 圖片是否處理成功)
    """
    cleaned_text = clean_text(text)

    img_ok = True
    if image_path and os.path.exists(image_path):
        img_ok = obfuscate_image(image_path)

    return cleaned_text, img_ok
