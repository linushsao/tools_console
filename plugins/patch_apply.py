# ==============================================================================
# plugins/patch_apply.py
# 外掛：套用補丁 (.patch)，支援剪貼簿或目前目錄搜尋來源，記住 -pN 參數
# 並提供執行紀錄 (PCH history)、套用後自動刪除來源檔（僅限目錄搜尋來源，無論成功或失敗）
# ==============================================================================

import os
import json
import shlex
import subprocess
from datetime import datetime

try:
    import pyperclip
except ImportError:
    pyperclip = None

__plugin_command__ = "PCH"
__plugin_name__ = "套用補丁"
__plugin_description__ = "套用補丁 (.patch)，可用剪貼簿或搜尋目前目錄，並記住 -pN 參數；支援 PCH history 查看執行紀錄"
__plugin_usage__ = "PCH [history]  -> 不帶參數執行套用流程；history 顯示最近執行紀錄"

HISTORY_FILE = "pch_history.json"


def on_load(fm):
    if not pyperclip:
        print("⚠️ [PCH 外掛] 未安裝 pyperclip，剪貼簿補丁來源將無法使用 (pip install pyperclip)")
    if not hasattr(fm, 'patch_default_level'):
        fm.patch_default_level = "-p1"
    if not hasattr(fm, 'pch_history_max'):
        fm.pch_history_max = 10
    if not hasattr(fm, 'pch_auto_delete'):
        fm.pch_auto_delete = True


def _load_history(fm):
    path = os.path.join(fm.conf_dir, HISTORY_FILE)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _add_history_entry(fm, success, rel_path, level=""):
    history = _load_history(fm)
    history.append({
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "result": "成功" if success else "失敗",
        "path": rel_path,
        "level": level
    })
    max_len = getattr(fm, 'pch_history_max', 10)
    if max_len > 0:
        history = history[-max_len:]
    path = os.path.join(fm.conf_dir, HISTORY_FILE)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ 寫入補丁執行紀錄失敗: {e}")


def _show_history(fm):
    history = _load_history(fm)
    print(f"\n{'='*20} PCH 執行紀錄（最近 {getattr(fm, 'pch_history_max', 10)} 筆） {'='*20}")
    if not history:
        print("(尚無任何執行紀錄)")
    else:
        print(f"{'時間':<20} {'結果':<6} {'參數':<6} 補丁路徑")
        print("-" * 75)
        for entry in reversed(history):
            print(f"{entry.get('time',''):<20} {entry.get('result',''):<6} {entry.get('level','-'):<6} {entry.get('path','')}")
    input("\n按 Enter 返回...")


def run(fm, args):
    if args and args[0].strip().upper() in ('HISTORY', 'H'):
        _show_history(fm)
        return

    print(f"\n{'='*20} 套用補丁 (PCH) {'='*20}")

    # 1. 詢問補丁來源：使用系統剪貼簿資料 或 搜尋目前目錄
    found_patches = []
    selected_patches = []
    search_sourced = set()  # 僅記錄「搜尋目前目錄」找到的實體檔案路徑，供成功後自動刪除判斷
    print("補丁來源: [1] 使用系統剪貼簿資料  [2] 搜尋目前目錄")
    src_ans = input("請選擇 (預設 2): ").strip()

    if src_ans == '1':
        if not pyperclip:
            print("❌ 未安裝 pyperclip，請執行 pip install pyperclip 後再試（Linux 需另裝 xclip 或 xsel）。")
            input("按 Enter 返回...")
            return
        try:
            clip_text = pyperclip.paste()
        except Exception as e:
            print(f"❌ 讀取剪貼簿失敗: {e}")
            input("按 Enter 返回...")
            return
        if not clip_text or not clip_text.strip():
            print("❌ 剪貼簿內容為空。")
            input("按 Enter 返回...")
            return
        clip_path = os.path.join(fm.conf_dir, "clipboard_patch.tmp")
        try:
            if not clip_text.endswith('\n'):
                clip_text += '\n'  # 剪貼簿常會遺失檔尾換行，導致 patch 判定「檔案在行中間結束」
            with open(clip_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(clip_text)
            selected_patches.append(clip_path)
            print(f"✅ 已將剪貼簿內容寫入暫存補丁: {clip_path}")
        except Exception as e:
            print(f"❌ 寫入暫存補丁檔失敗: {e}")
            input("按 Enter 返回...")
            return
    else:
        # 搜尋目前目錄中的 .patch 檔（不遞迴子目錄）
        try:
            for fname in sorted(os.listdir(fm.current_path)):
                fpath = os.path.join(fm.current_path, fname)
                if os.path.isfile(fpath) and fname.lower().endswith('.patch'):
                    found_patches.append(fpath)
        except Exception as e:
            print(f"⚠️ 搜尋目錄失敗: {e}")

        selected_patches = list(found_patches)  # 找到的補丁檔預設自動勾選

        if found_patches:
            print(f"\n✅ 找到 {len(found_patches)} 個補丁檔（已自動勾選）:")
            for i, fp in enumerate(found_patches, 1):
                print(f"  [{i}] {os.path.basename(fp)}")
            adj = input("若要取消勾選，輸入要排除的編號 (以空白分隔，直接 Enter 全部套用): ").strip()
            if adj:
                exclude_idx = set()
                for tok in adj.split():
                    if tok.isdigit() and 1 <= int(tok) <= len(found_patches):
                        exclude_idx.add(int(tok) - 1)
                selected_patches = [fp for i, fp in enumerate(found_patches) if i not in exclude_idx]
        else:
            print("\n(目前目錄下未找到 .patch 檔)")

        search_sourced = set(selected_patches)  # 僅這批「搜尋目前目錄」的結果才符合自動刪除資格

    # 允許手動輸入其他補丁檔路徑（可補充或取代自動搜尋結果）
    manual = input("是否要手動輸入其他補丁檔路徑？(直接 Enter 跳過，多個路徑以空白分隔): ").strip()
    if manual:
        for tok in manual.split():
            mp = tok if os.path.isabs(tok) else os.path.join(fm.current_path, tok)
            if os.path.isfile(mp):
                selected_patches.append(mp)
            else:
                print(f"⚠️ 找不到檔案，已略過: {tok}")

    if not selected_patches:
        input("❌ 沒有任何補丁檔可套用，按 Enter 返回...")
        return

    # 2. 詢問參數（例如 -p1），並記住成為下次預設值
    level_input = input(f"請輸入 patch 參數 (預設 {fm.patch_default_level}，直接 Enter 沿用): ").strip()
    if level_input:
        fm.patch_default_level = level_input
        fm.save_config()

    # 3. 依序執行套用補丁，並顯示結果
    print(f"\n{'-'*75}")
    print(f" 套用目錄: {fm.work_path}")
    print(f" 使用參數: {fm.patch_default_level}")
    print(f"{'-'*75}")

    for patch_file in selected_patches:
        print(f"\n📄 套用補丁: {os.path.basename(patch_file)} (使用參數: {fm.patch_default_level})")
        success = False
        try:
            level_args = shlex.split(fm.patch_default_level)
            result = subprocess.run(
                ["patch"] + level_args + ["-i", patch_file],
                cwd=fm.work_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip())
            success = (result.returncode == 0)  # 部分成功（returncode!=0）一律視為失敗
            if success:
                print(f"✅ 套用成功 (returncode=0)")
            else:
                print(f"❌ 套用失敗 (returncode={result.returncode})")
        except FileNotFoundError:
            print("❌ 找不到系統的 'patch' 指令，請確認已安裝 patch 工具並存在於 PATH 中。")
            rel_path = os.path.relpath(patch_file, fm.work_path).replace(os.path.sep, '/')
            _add_history_entry(fm, False, rel_path, fm.patch_default_level)
            break
        except Exception as e:
            print(f"❌ 執行時發生例外: {e}")

        rel_path = os.path.relpath(patch_file, fm.work_path).replace(os.path.sep, '/')
        _add_history_entry(fm, success, rel_path, fm.patch_default_level)

        if getattr(fm, 'pch_auto_delete', True) and patch_file in search_sourced:
            try:
                os.remove(patch_file)
                print(f"🗑️ 已自動刪除補丁檔: {os.path.basename(patch_file)}")
            except Exception as e:
                print(f"⚠️ 自動刪除補丁檔失敗: {e}")

    print(f"{'-'*75}")
    input("補丁套用流程結束，按 Enter 返回主選單...")
