# ==============================================================================
# plugins/hash_export.py
# 外掛：計算選取檔案的雜湊值，輸出為 JSON
# ==============================================================================

import os
import json
import hashlib
from datetime import datetime

__plugin_command__ = "HASH"
__plugin_name__ = "雜湊值計算"
__plugin_description__ = "對選取檔案計算雜湊值（MD5/SHA1/SHA256/SHA512），輸出 JSON"
__plugin_usage__ = "HASH [purge]  -> 選擇雜湊演算法後，對選取的檔案計算並輸出結果 JSON；加 purge 會先刪除目前目錄下舊的 hash_*.json 檔"

ALGO_OPTIONS = {"1": "md5", "2": "sha1", "3": "sha256", "4": "sha512"}
ALGO_CONFIG_FILE = "hash_plugin.json"
HASH_PREFIX = "hash_"
HASH_EXT = ".json"


def _load_default_algo(fm):
    path = os.path.join(fm.conf_dir, ALGO_CONFIG_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f).get('algo', 'sha256')
        except Exception:
            pass
    return 'sha256'


def _save_default_algo(fm, algo):
    path = os.path.join(fm.conf_dir, ALGO_CONFIG_FILE)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'algo': algo}, f, indent=4)
    except Exception as e:
        print(f"⚠️ 儲存雜湊演算法預設值失敗: {e}")


def _hash_file(full_path, algo):
    h = hashlib.new(algo)
    with open(full_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def run(fm, args):
    if not fm.selected_items:
        print("❌ 未選取任何檔案")
        input()
        return

    purge = any(a.strip().lower() == 'purge' for a in (args or []))
    if purge:
        try:
            old_hashes = [
                fn for fn in os.listdir(fm.current_path)
                if fn.startswith(HASH_PREFIX) and fn.endswith(HASH_EXT)
                and os.path.isfile(os.path.join(fm.current_path, fn))
            ]
        except Exception as e:
            print(f"⚠️ 搜尋舊雜湊檔失敗: {e}")
            old_hashes = []

        if old_hashes:
            print(f"🗑️ purge: 偵測到 {len(old_hashes)} 個舊雜湊檔，刪除中...")
            for fn in old_hashes:
                try:
                    os.remove(os.path.join(fm.current_path, fn))
                    print(f"   - 已刪除: {fn}")
                except Exception as e:
                    print(f"   - 刪除失敗: {fn} ({e})")
        else:
            print("ℹ️ purge: 目前目錄未找到舊雜湊檔。")

    default_algo = _load_default_algo(fm)
    print("\n請選擇雜湊演算法:")
    for k, v in ALGO_OPTIONS.items():
        mark = " (預設)" if v == default_algo else ""
        print(f"  [{k}] {v.upper()}{mark}")
    choice = input(f"請輸入選項 (直接 Enter 沿用預設 {default_algo.upper()}): ").strip()

    algo = ALGO_OPTIONS.get(choice, default_algo)
    if algo != default_algo:
        _save_default_algo(fm, algo)

    results = {}
    errors = {}
    print(f"\n開始以 {algo.upper()} 計算選取檔案雜湊值...")
    for rel in sorted(list(fm.selected_items)):
        full_path = os.path.normpath(os.path.join(fm.work_path, rel))
        if not os.path.isfile(full_path):
            continue
        try:
            results[rel.replace(os.path.sep, '/')] = _hash_file(full_path, algo)
        except Exception as e:
            errors[rel.replace(os.path.sep, '/')] = str(e)

    output_data = {
        "algorithm": algo,
        "generated_at": datetime.now().isoformat(),
        "files": results
    }
    if errors:
        output_data["errors"] = errors

    out_name = f"hash_{algo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path = os.path.join(fm.current_path, out_name)
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        print(f"✅ 完成！成功 {len(results)} 筆，失敗 {len(errors)} 筆")
        print(f"輸出檔案: {out_name}")
    except Exception as e:
        print(f"❌ 寫入結果檔失敗: {e}")

    fm.scan_directory()
    input("按 Enter 繼續...")
