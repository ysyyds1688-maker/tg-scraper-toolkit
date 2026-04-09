# Windows 安裝指南

## Step 1：安裝 Python

1. 到 https://www.python.org/downloads/ 下載最新版 Python
2. 執行安裝程式
3. **重要：勾選「Add Python to PATH」**
4. 點 Install Now

驗證安裝成功，打開 CMD 或 PowerShell：
```
python --version
```
看到 `Python 3.x.x` 就 OK

---

## Step 2：安裝 Git

1. 到 https://git-scm.com/download/win 下載
2. 一路 Next 安裝即可

---

## Step 3：下載專案

打開 CMD 或 PowerShell：
```
cd %USERPROFILE%\Desktop
git clone https://github.com/ysyyds1688-maker/tg-scraper-toolkit.git
cd tg-scraper-toolkit
```

---

## Step 4：建立虛擬環境 + 安裝套件

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

看到 `(venv)` 在前面就代表虛擬環境啟動成功

---

## Step 5：啟動系統

```
python tg.py
```

首次執行會自動引導你設定 API ID、API Hash、手機號碼

---

## 每次使用

每次打開 CMD，都要先進入專案目錄並啟動虛擬環境：
```
cd %USERPROFILE%\Desktop\tg-scraper-toolkit
venv\Scripts\activate
python tg.py
```

---

## 背景運行 Bot

Windows 沒有 `nohup`，改用以下方式：

### 方法 1：另開一個 CMD 視窗
```
cd %USERPROFILE%\Desktop\tg-scraper-toolkit
venv\Scripts\activate
set PYTHONPATH=.
python 5_bot.py
```
這個視窗不要關，Bot 就會持續運行

### 方法 2：用 pythonw 背景跑（不顯示視窗）
```
cd %USERPROFILE%\Desktop\tg-scraper-toolkit
venv\Scripts\pythonw.exe 5_bot.py
```
停止：打開工作管理員 → 找到 pythonw.exe → 結束工作

### 方法 3：設定開機自動啟動
1. 按 `Win + R` 輸入 `shell:startup`
2. 在開啟的資料夾建立一個 `start_bot.bat`：
```bat
@echo off
cd %USERPROFILE%\Desktop\tg-scraper-toolkit
call venv\Scripts\activate
set PYTHONPATH=.
python 5_bot.py
```
3. 以後開機就會自動啟動 Bot

---

## 常見問題

### `python` 指令找不到
→ 安裝 Python 時沒勾選「Add to PATH」
→ 解決：重新安裝 Python，記得勾選

### `git` 指令找不到
→ Git 沒安裝或沒加入 PATH
→ 解決：重新安裝 Git

### `pip install` 報錯
→ 試試：
```
python -m pip install -r requirements.txt
```

### 中文顯示亂碼
→ 在 CMD 執行：
```
chcp 65001
```
或改用 Windows Terminal（從 Microsoft Store 安裝）
