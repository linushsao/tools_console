# ==============================================================================
# plugins/export_tree.py
#
# 外掛指令: TREE_EXPORT / ETREE
# 功能: 匯出目錄樹結構，自動套用系統的過濾設定
# Version: V1.0.0
# ==============================================================================

__plugin_command__ = "TREE_EXPORT"
__plugin_aliases__ = ["ETREE", "EXPORT_TREE"]
__plugin_name__ = "匯出目錄樹"
__plugin_description__ = "匯出目錄樹檔案結構，支援套用系統忽略清單與過濾設定"
__plugin_usage__ = "TREE_EXPORT [選項] - 匯出目錄樹 | 選項: --format txt/md/json --depth N --output FILE --current --no-filter --include-hidden"

import os
import json
import fnmatch
from datetime import datetime

# 為了讓 PluginManager 也能認得別名
PLUGIN_COMMAND = "TREE_EXPORT"
PLUGIN_DESC = __plugin_description__
PLUGIN_USAGE = __plugin_usage__

def _get_ignore_patterns(file_manager):
    """嘗試從 FileManager 取得所有過濾設定，相容多個版本"""
    patterns = []
    
    # 1. 常見屬性名稱
    for attr in ['ignore_patterns', 'ignore_list', 'ignores', 'ignore_config', 'filter_patterns']:
        if hasattr(file_manager, attr):
            val = getattr(file_manager, attr)
            if isinstance(val, (list, set, tuple)):
                patterns.extend(list(val))
            elif isinstance(val, dict):
                # 有些版本是 dict 分組
                for v in val.values():
                    if isinstance(v, (list, set)):
                        patterns.extend(list(v))
    
    # 2. 從 config dict
    if hasattr(file_manager, 'config') and isinstance(file_manager.config, dict):
        for key in ['ignore', 'ignores', 'ignore_patterns', 'exclude']:
            if key in file_manager.config:
                v = file_manager.config[key]
                if isinstance(v, (list, set)):
                    patterns.extend(list(v))
    
    # 3. 從 current_ignore 或類似結構
    if hasattr(file_manager, 'current_ignore_patterns'):
        patterns.extend(list(file_manager.current_ignore_patterns))
    
    # 去重並正規化
    cleaned = []
    seen = set()
    for p in patterns:
        if not p or not isinstance(p, str):
            continue
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            cleaned.append(p)
    return cleaned

def _is_ignored(path, name, ignore_patterns, root_path, include_hidden=False):
    """判斷是否被過濾，邏輯與主程式 FileManager.scan_directory 保持一致"""
    # 隱藏檔處理
    if not include_hidden and name.startswith('.'):
        return True
    
    rel_path = os.path.relpath(os.path.join(path, name), root_path)
    # 套用 fnmatch
    for pat in ignore_patterns:
        # 支援目錄結尾 /  以及萬用字元
        # 1. 直接比對檔名
        if fnmatch.fnmatch(name, pat):
            return True
        # 2. 比對相對路徑
        if fnmatch.fnmatch(rel_path, pat):
            return True
        # 3. 比對相對路徑的任意層級 ( ** 效果 )
        if fnmatch.fnmatch(rel_path, f"**/{pat}") or fnmatch.fnmatch(rel_path, f"**/{pat}/**"):
            return True
        # 4. 如果 pattern 是資料夾名稱，排除整個資料夾
        if rel_path == pat or rel_path.startswith(pat + os.sep):
            return True
    return False

def _walk_filtered(root_path, ignore_patterns, max_depth=None, include_hidden=False, include_files=True):
    """回傳過濾後的樹狀結構 dict"""
    tree = {}
    
    def _walk(current_path, current_dict, depth):
        if max_depth is not None and depth > max_depth:
            return
        try:
            entries = os.listdir(current_path)
        except PermissionError:
            current_dict['__error__'] = 'Permission Denied'
            return
        
        # 分離目錄與檔案，排序
        dirs = []
        files = []
        for e in entries:
            full = os.path.join(current_path, e)
            if _is_ignored(current_path, e, ignore_patterns, root_path, include_hidden):
                continue
            if os.path.isdir(full):
                dirs.append(e)
            else:
                if include_files:
                    files.append(e)
        
        dirs.sort(key=lambda x: x.lower())
        files.sort(key=lambda x: x.lower())
        
        for d in dirs:
            sub_dict = {}
            current_dict[d + '/'] = sub_dict
            _walk(os.path.join(current_path, d), sub_dict, depth+1)
        for f in files:
            current_dict[f] = None  # 檔案葉節點
    
    _walk(root_path, tree, 1)
    return tree

def _render_txt(tree, prefix=""):
    lines = []
    items = list(tree.items())
    for idx, (name, subtree) in enumerate(items):
        is_last = idx == len(items) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{name}")
        if isinstance(subtree, dict):
            extension = "    " if is_last else "│   "
            lines.extend(_render_txt(subtree, prefix + extension))
    return lines

def _render_md(tree, depth=0):
    lines = []
    for name, subtree in tree.items():
        indent = "  " * depth + "- "
        if name.endswith('/'):
            lines.append(f"{indent}📁 **{name.rstrip('/')}**")
        else:
            lines.append(f"{indent}📄 {name}")
        if isinstance(subtree, dict):
            lines.extend(_render_md(subtree, depth+1))
    return lines

def _count_nodes(tree):
    dir_c = 0
    file_c = 0
    for name, subtree in tree.items():
        if isinstance(subtree, dict):
            dir_c += 1
            dc, fc = _count_nodes(subtree)
            dir_c += dc
            file_c += fc
        else:
            file_c += 1
    return dir_c, file_c

def run(file_manager, args):
    """
    file_manager: 主程式 FileManager 實例
    args: list[str] 指令後面的參數
    """
    import argparse
    
    # 解析參數，手動解析避免與主程式衝突
    # 支援: --format txt/md/json --depth 3 --output out.txt --current --no-filter --include-hidden --dirs-only
    fmt = 'txt'
    max_depth = None
    output_file = None
    use_filter = True
    include_hidden = False
    include_files = True
    base_path = None
    show_help = False
    
    # 簡易參數解析
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ('--format', '-f'):
            if i+1 < len(args):
                fmt = args[i+1].lower()
                i += 2
                continue
        elif a in ('--depth', '-d'):
            if i+1 < len(args):
                try:
                    max_depth = int(args[i+1])
                except:
                    pass
                i += 2
                continue
        elif a in ('--output', '-o'):
            if i+1 < len(args):
                output_file = args[i+1]
                i += 2
                continue
        elif a in ('--current', '-c'):
            base_path = 'current'
        elif a in ('--no-filter', '--no-ignore'):
            use_filter = False
        elif a in ('--include-hidden', '--all'):
            include_hidden = True
        elif a in ('--dirs-only', '--dir-only'):
            include_files = False
        elif a in ('--help', '-h'):
            show_help = True
        i += 1
    
    if show_help:
        print(f"""
[{__plugin_name__}] {__plugin_description__}

用法:
  TREE_EXPORT [--format txt|md|json] [--depth N] [--output FILE] [--current] [--no-filter] [--dirs-only]

參數:
  --format, -f       輸出格式: txt (預設), md (Markdown), json
  --depth, -d N      最大深度，例如 --depth 3
  --output, -o FILE  輸出到檔案，預設自動命名 tree_YYYYMMDD_HHMMSS.txt
  --current, -c      使用目前瀏覽路徑 ({getattr(file_manager, 'current_path', 'N/A')}) 而非工作根目錄
  --no-filter        不套用系統忽略清單
  --dirs-only        只匯出目錄，不含檔案
  --include-hidden   包含隱藏檔 (.開頭)

範例:
  TREE_EXPORT
  TREE_EXPORT --format md --depth 3 --output ./tree.md
  TREE_EXPORT --current --dirs-only
  TREE_EXPORT --no-filter --format json
""")
        input("按 Enter 繼續...")
        return

    # 決定根目錄
    if base_path == 'current':
        root_path = getattr(file_manager, 'current_path', getattr(file_manager, 'work_path', '.'))
    else:
        root_path = getattr(file_manager, 'work_path', getattr(file_manager, 'current_path', '.'))

    root_path = os.path.normpath(root_path)
    
    if not os.path.exists(root_path):
        print(f"❌ 路徑不存在: {root_path}")
        input("按 Enter...")
        return

    # 取得過濾設定
    ignore_patterns = []
    if use_filter:
        ignore_patterns = _get_ignore_patterns(file_manager)
        # 如果 FileManager 有自定義的 is_ignored 方法，優先嘗試收集
        if hasattr(file_manager, 'is_ignored_file'):
            # 僅作為參考，我們仍用自己的 fnmatch 邏輯
            pass

    print(f"\n{'='*60}")
    print(f" [{__plugin_name__}] 正在掃描...")
    print(f" 根目錄: {root_path}")
    print(f" 過濾: {'啟用' if use_filter else '停用'} ({len(ignore_patterns)} 條規則)")
    if use_filter and ignore_patterns:
        print(f"  規則: {', '.join(ignore_patterns[:10])}{' ...' if len(ignore_patterns)>10 else ''}")
    print(f" 深度: {max_depth if max_depth else '無限制'} | 格式: {fmt}")
    print(f"{'='*60}")

    tree_data = _walk_filtered(root_path, ignore_patterns if use_filter else [], max_depth, include_hidden, include_files)
    dir_count, file_count = _count_nodes(tree_data)

    # 渲染
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"tree_{timestamp}.{fmt if fmt!='txt' else 'txt'}"
    
    if not output_file:
        # 預設輸出到工作目錄下
        output_file = os.path.join(root_path, default_name)
        # 如果沒有寫入權限，改輸出到 script 目錄
        if not os.access(root_path, os.W_OK):
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_file = os.path.join(os.path.dirname(script_dir), default_name)
    else:
        # 相對路徑轉絕對
        if not os.path.isabs(output_file):
            output_file = os.path.join(root_path, output_file)

    content = ""
    if fmt == 'json':
        # json 格式保留完整結構
        export_obj = {
            "root": root_path,
            "generated_at": datetime.now().isoformat(),
            "filter_enabled": use_filter,
            "ignore_patterns": ignore_patterns,
            "max_depth": max_depth,
            "stats": {"directories": dir_count, "files": file_count},
            "tree": tree_data
        }
        content = json.dumps(export_obj, ensure_ascii=False, indent=2)
    elif fmt == 'md':
        lines = [
            f"# 目錄樹 - {os.path.basename(root_path)}",
            f"",
            f"- 根目錄: `{root_path}`",
            f"- 產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 過濾: {'啟用' if use_filter else '停用'} ({len(ignore_patterns)} 條)",
            f"- 統計: {dir_count} 個目錄, {file_count} 個檔案",
            f"",
            f"```",
            f"{os.path.basename(root_path)}/",
        ]
        lines.extend(_render_txt(tree_data))
        lines.extend(["```", "", "## Markdown 樹狀", ""])
        lines.extend(_render_md(tree_data))
        content = "\n".join(lines)
    else: # txt
        lines = [
            f"目錄樹 - {os.path.basename(root_path)}",
            f"根目錄: {root_path}",
            f"產生時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"過濾: {'啟用' if use_filter else '停用'} ({len(ignore_patterns)} 條) - {', '.join(ignore_patterns) if ignore_patterns else '無'}",
            f"統計: {dir_count} 個目錄, {file_count} 個檔案",
            f"{'='*60}",
            f"{os.path.basename(root_path)}/",
        ]
        lines.extend(_render_txt(tree_data))
        content = "\n".join(lines)

    # 寫檔
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n✅ 匯出完成!")
        print(f"   檔案: {output_file}")
        print(f"   目錄: {dir_count} 個 | 檔案: {file_count} 個")
        print(f"   大小: {len(content)} 字元")
        # 預覽前 30 行
        print(f"\n--- 預覽 (前 30 行) ---")
        for line in content.splitlines()[:30]:
            print(line)
        if len(content.splitlines()) > 30:
            print(f"... 還有 {len(content.splitlines())-30} 行")
    except Exception as e:
        print(f"❌ 寫入失敗: {e}")
        # fallback 輸出到剪貼簿
        try:
            import pyperclip
            pyperclip.copy(content)
            print("已複製到剪貼簿")
        except:
            pass

    input("\n按 Enter 返回主選單...")

# 相容舊版 PluginManager 會找 main()
def main(file_manager, args):
    run(file_manager, args)
