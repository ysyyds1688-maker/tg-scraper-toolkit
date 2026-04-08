"""
合併所有爬取的 CSV 並去除重複用戶
依據 user_id 去重，保留所有來源群組資訊
"""

import csv
import os
import glob
from datetime import datetime


# 搜尋這些位置的 CSV
TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
SEARCH_PATHS = [
    os.path.join(TOOLKIT_DIR, "data", "*.csv"),
]

# 排除這些檔案
EXCLUDE = ["search_report", "msg_", "dm_sent_log", "all_members"]

OUTPUT_DIR = os.path.join(TOOLKIT_DIR, "data")


def find_csv_files():
    """找到所有成員 CSV"""
    files = []
    for pattern in SEARCH_PATHS:
        for f in glob.glob(pattern):
            basename = os.path.basename(f)
            if any(ex in basename for ex in EXCLUDE):
                continue
            files.append(f)
    return sorted(set(files))


def load_csv(path):
    """載入一個 CSV，回傳成員列表"""
    members = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if "user_id" not in (reader.fieldnames or []):
                return []
            for row in reader:
                members.append(row)
    except Exception as e:
        print(f"  ⚠ 讀取失敗: {e}")
    return members


def merge_and_dedup(all_members):
    """依 user_id 去重，合併來源群組"""
    unique = {}
    for m in all_members:
        uid = m.get("user_id", "")
        if not uid or uid == "":
            continue
        if uid in unique:
            # 合併來源群組
            existing_sources = unique[uid].get("source_group", "")
            new_source = m.get("source_group", "")
            if new_source and new_source not in existing_sources:
                unique[uid]["source_group"] = f"{existing_sources}; {new_source}" if existing_sources else new_source
        else:
            unique[uid] = dict(m)
    return list(unique.values())


def main():
    print("搜尋所有成員 CSV 檔案...\n")
    files = find_csv_files()

    if not files:
        print("找不到任何 CSV 檔案！")
        return

    print(f"找到 {len(files)} 個檔案：")
    total_raw = 0
    all_members = []

    for f in files:
        members = load_csv(f)
        count = len(members)
        total_raw += count
        all_members.extend(members)
        basename = os.path.basename(f)
        print(f"  [{count:>6} 位] {basename}")

    print(f"\n原始總數: {total_raw} 位")

    # 去重
    unique = merge_and_dedup(all_members)
    print(f"去重後:   {len(unique)} 位 (移除 {total_raw - len(unique)} 個重複)")

    if not unique:
        print("沒有資料")
        return

    # 儲存（固定檔名，每次覆蓋）
    output_path = os.path.join(TOOLKIT_DIR, "all_members.csv")

    fieldnames = ["user_id", "username", "first_name", "last_name", "phone", "is_bot", "source_group", "source_group_id"]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(unique)

    print(f"\n已儲存至: {output_path}")

    # 分開有/無 username
    has_username = [m for m in unique if m.get("username")]
    no_username = [m for m in unique if not m.get("username")]

    # 有 username（可私訊）
    path_with = os.path.join(TOOLKIT_DIR, "members_with_username.csv")
    with open(path_with, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(has_username)

    # 無 username
    path_without = os.path.join(TOOLKIT_DIR, "members_no_username.csv")
    with open(path_without, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(no_username)

    print(f"\n統計：")
    print(f"  全部:        {len(unique)} 位 → all_members.csv")
    print(f"  有 username: {len(has_username)} 位 → members_with_username.csv (可私訊)")
    print(f"  無 username: {len(no_username)} 位 → members_no_username.csv")


if __name__ == "__main__":
    main()
