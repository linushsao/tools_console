# ==============================================================================
# plugins/patch_apply.py
# 外掛：套用補丁 (.patch)，支援剪貼簿或目前目錄搜尋來源，記住 -pN 參數
# ==============================================================================

import os
import subprocess

try:
    import pyperclip
except ImportError:
    pyperclip = None

__plugin_command__ = "PCH"
__plugin_name__ = "套用補丁"
__plugin_description__ = "套用補丁 (.patch)，可用剪貼簿或搜尋目前目錄，並記住 -pN 參數"
__plugin_usage__ = "PCH  -> 選擇補丁來源(剪貼簿/目前目錄)，輸入 -pN 參數後執行 patch"


def on_load(fm):
    if not pyperclip:
        print("⚠️ [PCH 外掛] 未安裝 pyperclip，剪貼簿補丁來源將無法使用 (pip install pyperclip)")
    if not hasattr(fm, 'patch_default_level'):
        fm.patch_default_level = "-p1"


def run(fm, args):
    print(f"\n{'='*20} 套用補丁 (PCH) {'='*20}")

    # 1. 詢問補丁來源：使用系統剪貼簿資料 或 搜尋目前目錄
    found_patches = []
    selected_patches = []
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
        print(f"\n📄 套用補丁: {os.path.basename(patch_file)}")
        try:
            result = subprocess.run(
                ["patch", fm.patch_default_level, "-i", patch_file],
                cwd=fm.work_path,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(result.stdout.rstrip())
            if result.stderr:
                print(result.stderr.rstrip())
            if result.returncode == 0:
                print(f"✅ 套用成功 (returncode=0)")
            else:
                print(f"❌ 套用失敗 (returncode={result.returncode})")
        except FileNotFoundError:
            print("❌ 找不到系統的 'patch' 指令，請確認已安裝 patch 工具並存在於 PATH 中。")
            break
        except Exception as e:
            print(f"❌ 執行時發生例外: {e}")

    print(f"{'-'*75}")
    input("補丁套用流程結束，按 Enter 返回主選單...")
