# TG Scraper Toolkit

Telegram 自動化工具包 — 撈名單、訊息轉發、私訊導流。基於 [Telethon](https://github.com/LonamiWebs/Telethon)。

## 快速開始

```bash
# 1. 建立虛擬環境
python3 -m venv venv
source venv/bin/activate

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 設定 API 憑證
# 編輯 config.py，填入 API_ID、API_HASH、PHONE

# 4. 執行任一腳本
python3 1_scraper.py
python3 2_forwarder.py
python3 3_dm.py
```

首次執行會要求手機驗證碼登入 Telegram，之後自動記住。

## API 憑證取得

1. 到 https://my.telegram.org 登入
2. 點「API development tools」
3. 建立應用程式，取得 `api_id` 和 `api_hash`
4. 填入 `config.py`

---

## 三個核心腳本

### 1. `1_scraper.py` — 撈名單

從 Telegram 群組中撈取成員名單。

```bash
python3 1_scraper.py
```

**四種模式：**

| 模式 | 說明 |
|------|------|
| 撈單一群組 | 選擇一個群組，撈取全部成員 |
| 批量撈取 | 自動掃描所有已加入的群組，一鍵批量撈取 |
| 關鍵字搜尋 | 用預設關鍵字搜尋公開群組並撈取成員 |
| 只做合併去重 | 不撈取，只合併現有的 CSV 檔案 |

**特色：**
- 非管理員自動切換逐字搜尋模式
- 自動跳過已爬過的群組
- 撈取完自動合併去重
- 輸出三個檔案：`all_members.csv`、`members_with_username.csv`、`members_no_username.csv`

---

### 2. `2_forwarder.py` — 訊息轉發

把群組訊息轉發到你的頻道。

```bash
python3 2_forwarder.py
```

**兩種模式：**

| 模式 | 說明 |
|------|------|
| 即時監聽 | 持續監聽來源群組，有新訊息自動轉發到目標頻道 |
| 歷史批量 | 一次性把群組的歷史訊息批量轉發到頻道 |

**特色：**
- 支援多個來源群組同時監聽
- 可設定轉發數量（全部或指定則數）
- 自動處理限速
- 按 Ctrl+C 優雅停止

---

### 3. `3_dm.py` — 私訊導流

擬人化私訊名單上的用戶，邀請加入群組。

```bash
python3 3_dm.py
```

**特色：**

| 功能 | 說明 |
|------|------|
| 擬人化 | 模擬打字狀態、分段發送、隨機延遲 |
| 多組話術 | 5 組訊息模板隨機輪換，每人收到不同內容 |
| 防封號 | 每日上限、隨機間隔 60-180 秒、限流自動等待 |
| 斷點續傳 | 記錄已發送名單，中斷後重跑自動跳過 |
| 發送報告 | 自動記錄到 `dm_sent_log.csv` |

**自訂話術：** 編輯 `messages.py` 修改訊息模板。

---

## 設定檔 `config.py`

```python
# API 憑證
API_ID = 12345678
API_HASH = "your_api_hash"
PHONE = "+886912345678"

# 轉發目標頻道（2_forwarder.py 用）
TARGET_CHANNEL = ""

# 群組邀請連結（3_dm.py 用）
GROUP_INVITE_LINK = "https://t.me/+xxxxxxxx"

# 私訊延遲（秒）
DM_MIN_DELAY = 60
DM_MAX_DELAY = 180
DM_DAILY_LIMIT = 30

# 名單檔案
DM_CONTACT_FILES = ["all_members.csv"]
```

## 輸出結構

```
tg-scraper-toolkit/
├── 1_scraper.py              # 撈名單
├── 2_forwarder.py            # 訊息轉發
├── 3_dm.py                   # 私訊導流
├── config.py                 # 設定檔
├── messages.py               # 訊息模板
├── requirements.txt
├── data/                     # 撈取的原始資料
│   └── *.csv
├── all_members.csv           # 合併去重後全部成員
├── members_with_username.csv # 有 username（可私訊）
├── members_no_username.csv   # 無 username
├── dm_sent_log.csv           # 私訊發送記錄
└── _archive/                 # 舊版腳本備份
```

### CSV 欄位

| 欄位 | 說明 |
|------|------|
| `user_id` | Telegram 用戶 ID |
| `username` | 用戶名（有的話可私訊）|
| `first_name` | 名 |
| `last_name` | 姓 |
| `phone` | 電話（少量有）|
| `is_bot` | 是否為 Bot |
| `source_group` | 來源群組 |

## 防封號建議

- 私訊間隔建議 60 秒以上
- 每日私訊上限建議 30 則（新帳號 20）
- 新帳號建議先養號幾天再大量操作
- 加入群組間隔 15-30 秒
- 遇到限速自動等待，不要硬衝

## 注意事項

- `.session` 檔包含登入憑證，請勿分享
- `config.py` 含 API 憑證，已加入 `.gitignore`
- 請遵守 Telegram ToS 和當地法規

## License

MIT
