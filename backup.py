"""
一鍵備份重要檔案
打包所有設定、記錄、session、名單到一個 zip
換電腦時只要解壓縮就能用
"""

import os
import zipfile
from datetime import datetime

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))

# 要備份的檔案
BACKUP_FILES = [
    # 設定
    "config.py",
    "accounts.json",
    "agents.json",
    # 記錄
    "dm_sent_log.csv",
    "dm_state.json",
    "forward_log.json",
    "published_log.json",
    # Session
    "tg_session.session",
    "bot_session.session",
    # 名單
    "all_members.csv",
    "members_with_username.csv",
    "members_no_username.csv",
]

# 要備份的資料夾
BACKUP_DIRS = [
    "sessions",
    "data",
]


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"tg_backup_{ts}.zip"
    zip_path = os.path.join(os.path.expanduser("~/Downloads"), zip_name)

    print("  打包備份中...\n")

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 備份檔案
        for f in BACKUP_FILES:
            fp = os.path.join(TOOLKIT_DIR, f)
            if os.path.exists(fp):
                zf.write(fp, f)
                size = os.path.getsize(fp)
                print(f"  ✅ {f} ({size:,} bytes)")
                count += 1

        # 備份資料夾
        for d in BACKUP_DIRS:
            dp = os.path.join(TOOLKIT_DIR, d)
            if os.path.isdir(dp):
                for root, dirs, files in os.walk(dp):
                    for file in files:
                        full = os.path.join(root, file)
                        rel = os.path.relpath(full, TOOLKIT_DIR)
                        zf.write(full, rel)
                        count += 1
                print(f"  ✅ {d}/ ({len(os.listdir(dp))} 個檔案)")

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\n  備份完成!")
    print(f"  檔案: {zip_path}")
    print(f"  大小: {size_mb:.1f} MB")
    print(f"  共 {count} 個檔案")
    print(f"\n  換電腦時：解壓縮到專案資料夾即可")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    main()
