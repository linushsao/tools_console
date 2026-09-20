# ==============================================================================
# plugins/pattern_lookup.py
# 外掛：以關鍵字(支援萬用字元 * ?)搜尋目前目錄下文字檔內容，RECU 遞迴子目錄
# ==============================================================================

import os
import re

__plugin_command__ = "LOOKUP"
__plugin_name__ = "內容關鍵字查找"
__plugin_description__ = "以關鍵字(支援萬用字元)搜尋目前目錄內文字檔內容，符合者表列顯示"
__plugin_usage__ = "LOOKUP <pattern> [RECU]  -> 搜尋目前目錄文字檔內容；加 RECU 遞迴搜尋子目錄"


def _wildcard_to_regex(pattern):
    """將含 * ? 萬用字元的關鍵字轉為可在檔案內容中任意位置比對的正規表示式"""
    parts = []
    for ch in pattern:
        if ch == '*':
            parts.append('.*')
        elif ch == '?':
            parts.append('.')
        else:
            parts.append(re.escape(ch))
    return re.compile(''.join(parts), re.DOTALL)


def _is_binary(content):
    return '\x00' in content


def run(fm, args):
    if not args:
        print("❌ 請輸入要搜尋的關鍵字 (支援 * ? 萬用字元)")
        input()
        return

    recursive = False
    pattern_parts = []
    for a in args:
        if a.strip().upper() == 'RECU':
            recursive = True
        else:
            pattern_parts.append(a)

    if not pattern_parts:
        print("❌ 請輸入要搜尋的關鍵字 (支援 * ? 萬用字元)")
        input()
        return

    pattern = " ".join(pattern_parts)
    regex = _wildcard_to_regex(pattern)

    target_dir = fm.current_path
    candidates = []

    if recursive:
        for root, dirs, files in os.walk(target_dir):
            rel_root = os.path.relpath(root, fm.work_path)
            dirs[:] = [d for d in dirs if not fm.is_ignored(
                os.path.normpath(os.path.join(rel_root, d)) if rel_root != '.' else d)]
            for fn in files:
                full_path = os.path.join(root, fn)
                rel_path = os.path.relpath(full_path, fm.work_path)
                if fm.is_ignored(rel_path):
                    continue
                candidates.append(full_path)
    else:
        try:
            for fn in sorted(os.listdir(target_dir)):
                full_path = os.path.join(target_dir, fn)
                if not os.path.isfile(full_path):
                    continue
                rel_path = os.path.relpath(full_path, fm.work_path)
                if fm.is_ignored(rel_path):
                    continue
                candidates.append(full_path)
        except Exception as e:
            print(f"⚠️ 讀取目錄失敗: {e}")
            candidates = []

    found_list = []
    print(f"正在搜尋關鍵字: '{pattern}' ({'遞迴' if recursive else '僅目前目錄'}) ...")

    for full_path in candidates:
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue
        if _is_binary(content):
            continue
        if regex.search(content):
            rel_path = os.path.relpath(full_path, fm.work_path).replace(os.path.sep, '/')
            found_list.append(rel_path)

    found_list.sort()
    if found_list:
        print(f"\n{'='*10} 符合條件的檔案 ({len(found_list)}) {'='*10}")
        for p in found_list:
            print(f" [MATCH] {p}")
    else:
        print(f"❌ 未找到符合關鍵字 '{pattern}' 的文字檔")

    input("\n按 Enter 繼續...")
