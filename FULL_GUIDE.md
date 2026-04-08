# TG 自動化獲客系統 — 從 0 到 1 完整指南

---

## 一、你需要準備的東西

| 項目 | 數量 | 說明 | 取得方式 |
|------|------|------|---------|
| 電腦 | 1 台 | Mac 或 Windows 都可 | 你現有的 |
| TG 帳號 | 10 個 | 每個用不同電話號碼註冊 | 買預付卡/太空卡 |
| 手機 | 1 支 | 用來接收驗證碼 | 你現有的 |
| API 憑證 | 每帳號各一組 | api_id + api_hash | my.telegram.org |
| Bot | 1 個 | 客服導流用 | @BotFather 建立 |
| 代理 IP | 選配 | 不買也能跑（錯開時間） | proxy 服務商 |

---

## 二、系統架構總覽

```
Phase 1               Phase 2              Phase 3             Phase 4
數據採集      →       內容營運      →      私訊導流     →     客服承接

[撈名單]            [抓圖文]           [多帳號私訊]         [Bot 回覆]
1_scraper.py        girl_scraper       3_dm_multi.py       5_bot.py
     │              2_forwarder.py          │                  │
     ▼              4_publisher.py          ▼                  ▼
all_members.csv     你的頻道            dm_sent_log.csv    用戶點按鈕
                    (不顯示來源)        (250-300人/天)     找到客服
```

---

## 三、Step by Step 操作流程

---

### Step 0：環境安裝（只需做一次）

#### 0-1. 安裝 Python
Mac 通常已內建。確認：
```bash
python3 --version
```

#### 0-2. 下載專案
```bash
cd ~/Downloads
git clone https://github.com/ysyyds1688-maker/tg-scraper-toolkit.git
cd tg-scraper-toolkit
```

#### 0-3. 建立虛擬環境 + 安裝套件
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Step 1：申請 TG API 憑證（每個帳號都要做）

#### 1-1. 到 https://my.telegram.org 登入
- 輸入該帳號的手機號碼
- 收驗證碼登入

#### 1-2. 點「API development tools」
- 建立應用程式
- 取得 `api_id`（數字）和 `api_hash`（字串）

#### 1-3. 記錄下來
```
帳號1: phone=+886900000001, api_id=11111111, api_hash=aaaaaa...
帳號2: phone=+886900000002, api_id=22222222, api_hash=bbbbbb...
...
帳號10: phone=+886900000010, api_id=10101010, api_hash=jjjjjj...
```

⚠️ **每個帳號要用各自的手機號碼登入 my.telegram.org，不能共用同一組 api_id/api_hash**

---

### Step 2：設定帳號（填入 accounts.json）

#### 2-1. 編輯 accounts.json
把 10 個帳號的資訊填進去：

```json
{
  "accounts": [
    {
      "name": "帳號1",
      "phone": "+886900000001",
      "api_id": 11111111,
      "api_hash": "aaaaaaaaaa",
      "session_name": "sessions/session_01",
      "proxy": null,
      "daily_limit": 20,
      "delay_min": 60,
      "delay_max": 150,
      "enabled": true
    },
    {
      "name": "帳號2",
      "phone": "+886900000002",
      "api_id": 22222222,
      "api_hash": "bbbbbbbbbb",
      "session_name": "sessions/session_02",
      "proxy": null,
      "daily_limit": 25,
      "delay_min": 70,
      "delay_max": 180,
      "enabled": true
    }
  ]
}
```

⚠️ 重點：
- `proxy` 不買代理就填 `null`
- `daily_limit` 新號填 15-20，養過的號填 30-40
- `delay_min/max` 每個帳號設不同值（更自然）

#### 2-2. 批量登入所有帳號
```bash
PYTHONPATH=. python3 setup_accounts.py
```
- 會逐一要求你輸入每個帳號的驗證碼
- 登入成功後產生 session 檔案在 `sessions/` 資料夾
- 之後不用再輸入驗證碼

---

### Step 3：養號（重要！不要跳過）

每個新帳號需要養 3-7 天再開始大量操作。

#### 3-1. 養號期間要做的事
| 動作 | 說明 |
|------|------|
| 設頭像 | 每個帳號不同頭像 |
| 填個人資料 | 名字、簡介，每個帳號不同 |
| 加正常群 | 加幾個正常的群組（美食、旅遊等） |
| 正常聊天 | 在群裡偶爾發言、看訊息 |
| 不要同時註冊 | 分批註冊，隔幾天一批 |

#### 3-2. 養號時間建議
```
Day 1-2:  設頭像、個人資料、加 3-5 個群
Day 3-4:  在群裡發幾則正常訊息
Day 5-7:  開始小量測試發私訊（每天 5 人）
Day 7+:   可以正式跑自動化
```

---

### Step 4：撈名單

#### 4-1. 執行撈取腳本
```bash
PYTHONPATH=. python3 1_scraper.py
```

#### 4-2. 選擇模式
```
[1] 撈單一群組成員
[2] 批量撈所有已加入的群組
[3] 關鍵字搜尋群組並撈取
[4] 只做合併去重
```

#### 4-3. 產出檔案
| 檔案 | 內容 |
|------|------|
| `all_members.csv` | 全部成員（去重後） |
| `members_with_username.csv` | 有 username 的（可私訊） |
| `members_no_username.csv` | 沒有 username 的 |

---

### Step 5：抓取圖文內容

#### 5-1. 從來源頻道抓取圖片+文字
```bash
PYTHONPATH=. python3 _archive/girl_scraper.py
```
- 選擇來源頻道
- 自動下載圖片到 `data/images/`
- 產生 CSV 記錄圖文對應關係

---

### Step 6：發佈到你的頻道

有兩種方式：

#### 方式 A：即時監聽自動重發（推薦）
```bash
PYTHONPATH=. python3 2_forwarder.py
```
選模式 1 或 2：
- 模式 1：即時監聽來源群組，新訊息自動重發到你的頻道
- 模式 2：歷史批量重發

自動處理：
- ✅ 下載媒體再重新上傳（不顯示「轉發自」）
- ✅ 原始連結替換為 @teaprincess_bot
- ✅ 底部加上導流文字

#### 方式 B：從爬取資料發佈
```bash
PYTHONPATH=. python3 4_publisher.py
```
- 讀取 girl_scraper 抓下來的 CSV + 圖片
- 重新發送到你的頻道
- 記錄已發佈的訊息，不重發

---

### Step 7：啟動客服 Bot

#### 7-1. 啟動 Bot
```bash
nohup env PYTHONPATH=. python3 5_bot.py > bot.log 2>&1 &
```
Bot 會在背景持續運行。

#### 7-2. 新增客服
在 Bot 對話中發送指令：
```
/add 大神 daishen_service
/add 極樂 jile_cs
/add 貝兒 beier_service
```
格式：`/add 來源名稱 客服TG帳號`

#### 7-3. 用戶體驗流程
```
用戶在你的頻道看到圖文
    ↓
底部有 @teaprincess_bot 連結
    ↓
點進去看到歡迎語 + 客服按鈕
    ↓
按鈕顯示：🍵 大神-茶莊客服
    ↓
點擊直接跳轉到該客服帳號對話
```

#### 7-4. 管理指令
| 指令 | 功能 |
|------|------|
| `/add 來源 username` | 新增客服 |
| `/remove 來源` | 刪除客服 |
| `/list` | 查看所有客服 |
| `/reload` | 重新載入佳麗資料 |

---

### Step 8：啟動多帳號私訊

#### 8-1. 確認設定
- `accounts.json` 已填好 10 個帳號
- `all_members.csv` 名單已準備好
- `config.py` 中 `GROUP_INVITE_LINK` 已設定

#### 8-2. 一鍵啟動
```bash
PYTHONPATH=. python3 3_dm_multi.py
```

#### 8-3. 系統會自動執行
```
📦 名單預分配：
  帳號1 → 20 人
  帳號2 → 25 人
  帳號3 → 30 人
  ...

🕐 08:00 帳號1 啟動
  ✅ 發送第 1/20 人... 模擬打字... 發送成功
  ⏳ 等待 87 秒
  ✅ 發送第 2/20 人...
  ...
  📊 帳號1 完成: 成功 18, 跳過 2

😴 休息 30 分鐘...

🕐 09:20 帳號2 啟動
  （名單完全不同，不會重複發）
  ...

🕐 18:00 全部完成
  📊 今日總計: 250 人
```

#### 8-4. 中斷與恢復
- 按 `Ctrl+C` 隨時中斷，進度自動保存
- 明天再跑會自動跳過已發的人
- 每日凌晨自動重置各帳號的發送計數

---

## 四、每日 SOP

| 時間 | 動作 | 指令 |
|------|------|------|
| 早上 | 啟動多帳號私訊 | `python3 3_dm_multi.py` |
| 全天 | Bot 保持運行 | `nohup ... 5_bot.py &`（一次啟動） |
| 需要時 | 撈新名單 | `python3 1_scraper.py` |
| 需要時 | 發佈內容到頻道 | `python3 2_forwarder.py` |
| 需要時 | 新增/修改客服 | 在 Bot 中 `/add` `/remove` |

---

## 五、風控與防封號

### 帳號層面
| 策略 | 做法 |
|------|------|
| 獨立 API | 每帳號各自的 api_id/api_hash |
| 獨立電話 | 每帳號不同手機號碼 |
| 養號 | 新號養 3-7 天再大量操作 |
| 個人資料 | 每帳號不同頭像、名字、簡介 |

### 發送層面
| 策略 | 做法 |
|------|------|
| 時間錯開 | 一次只跑一個帳號，中間休息 30 分鐘 |
| 擬人化 | 模擬打字狀態、分段發送 |
| 話術輪換 | 5 組模板隨機，每人不同 |
| 延遲差異化 | 每帳號不同間隔（60-180 秒） |
| 每日上限 | 新號 15-20，老號 30-40 |

### 異常處理
| 情況 | 系統行為 |
|------|---------|
| FloodWait < 5 分鐘 | 自動等待後繼續 |
| FloodWait > 5 分鐘 | 停用該帳號，切下一個 |
| PeerFlood | 立即停用該帳號 |
| 登入失敗 | 跳過，繼續下一個帳號 |
| 程式崩潰 | 重跑自動續傳，不重複 |

### 防重複發送（三層保險）
```
第 1 層：名單預分配 → 每帳號拿到完全不同的人
第 2 層：即時記錄 → 每發一人立刻寫入 CSV
第 3 層：啟動檢查 → 重跑自動跳過已發的人
```

---

## 六、預估產能

| 帳號數 | 每帳號/天 | 每日總量 | 每月總量 |
|--------|----------|---------|---------|
| 5 個 | 25 人 | 125 人 | 3,750 人 |
| 10 個 | 25 人 | 250 人 | 7,500 人 |
| 10 個 | 30 人 | 300 人 | 9,000 人 |

---

## 七、未來擴展

| 功能 | 說明 |
|------|------|
| 代理 IP | 每帳號配獨立 IP，進一步降低風險 |
| 雲端部署 | 部署到 VPS，24 小時不間斷 |
| 訊息內容過濾 | 自動區分活動/商品訊息 |
| 數據統計面板 | 視覺化每日發送/轉化數據 |
| 多 Bot | 不同頻道配不同 Bot |
