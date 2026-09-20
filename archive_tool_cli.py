# ==============================================================================
# archive_tool_cli.py
#
# Version: V0.4-060-PluginSystem (Plugin System Support)
# 更新日期: 2026-07-17
# 描述: 新增外掛系統，支援 plugins/ 目錄自動掃描，新增 RENAME 重命名外掛。
# ==============================================================================

import os
import math
import json
import base64
import re 
from datetime import datetime

TREE_EXPORT_PREFIX = "tree_"
TREE_EXPORT_EXT = ".txt"
import shutil 
import sys
import fnmatch  # 引入萬用字元比對庫
import atexit
try:
    import readline  # Linux/macOS 內建，支援上下鍵瀏覽指令歷史
except ImportError:
    readline = None  # Windows 無 readline，需安裝 pyreadline3 才可使用此功能
try:
    import pyperclip  # 用於讀取系統剪貼簿補丁內容
except ImportError:
    pyperclip = None

PROGRAM_VERSION = "V0.4-060-PluginSystem"

# ==============================================================================
# 外掛系統 (Plugin System)
# ==============================================================================
import importlib.util
import traceback

class PluginManager:
    def __init__(self, script_dir):
        self.script_dir = script_dir
        self.plugins_dir = os.path.join(script_dir, "plugins")
        self.plugins = {}  # cmd -> {module, info}
        self.ensure_dir()
        self.scan()

    def ensure_dir(self):
        if not os.path.exists(self.plugins_dir):
            os.makedirs(self.plugins_dir)
            # 建立 __init__.py 讓它可被當成 package
            init_file = os.path.join(self.plugins_dir, "__init__.py")
            if not os.path.exists(init_file):
                open(init_file, 'w').close()

    def scan(self):
        self.plugins = {}
        if not os.path.exists(self.plugins_dir):
            return
        for fname in os.listdir(self.plugins_dir):
            if fname.startswith('_'): continue
            if not fname.endswith('.py'): continue
            fpath = os.path.join(self.plugins_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(f"plugins.{fname[:-3]}", fpath)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                # 讀取外掛資訊
                cmd = getattr(mod, '__plugin_command__', None) or getattr(mod, 'PLUGIN_COMMAND', None)
                name = getattr(mod, '__plugin_name__', None) or fname[:-3]
                desc = getattr(mod, '__plugin_description__', '') or getattr(mod, 'PLUGIN_DESC', '')
                usage = getattr(mod, '__plugin_usage__', '') or getattr(mod, 'PLUGIN_USAGE', '')
                if not cmd:
                    continue
                cmd = cmd.upper()
                self.plugins[cmd] = {
                    'module': mod,
                    'name': name,
                    'cmd': cmd,
                    'desc': desc,
                    'usage': usage,
                    'file': fname,
                    'loaded': False
                }
            except Exception as e:
                print(f"[外掛載入失敗] {fname}: {e}")
                traceback.print_exc()

    def notify_loaded(self, file_manager):
        """呼叫各外掛的 on_load(fm) hook（若有實作），每個外掛僅呼叫一次。
        外掛應在此自行檢查相依套件是否存在，並將結果記錄於自身狀態中，
        不應由主程式判斷外掛的相依性。"""
        for plug in self.plugins.values():
            if plug['loaded']:
                continue
            plug['loaded'] = True
            if hasattr(plug['module'], 'on_load'):
                try:
                    plug['module'].on_load(file_manager)
                except Exception as e:
                    print(f"[外掛 on_load 錯誤] {plug['name']}: {e}")

    def list_plugins(self):
        return self.plugins

    def run(self, cmd, file_manager, args):
        cmd = cmd.upper()
        if cmd not in self.plugins:
            return False
        plug = self.plugins[cmd]
        try:
            if hasattr(plug['module'], 'run'):
                plug['module'].run(file_manager, args)
            elif hasattr(plug['module'], 'main'):
                plug['module'].main(file_manager, args)
            else:
                print(f"外掛 {plug['name']} 沒有 run() 入口")
        except Exception as e:
            print(f"[外掛執行錯誤] {plug['name']}: {e}")
            traceback.print_exc()
            input("按 Enter 繼續...")
        return True


# ==============================================================================
# 工具組（VC 已改為外掛，見 plugins/version_control.py）
# ==============================================================================

# ==============================================================================
# 檔案管理員 (FileManager)
# ==============================================================================

class FileManager:
    def __init__(self, start_path=".", rows_per_page=15):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.work_path = os.path.normpath(os.path.abspath(start_path))
        self.current_path = self.work_path
        self.work_paths = {}
        self.current_work_path_name = "Default"
        self.selected_items = set()
        self.ignored_items = {".git", "__pycache__", "venv", ".vscode"}
        self.file_list = []
        self.rows_per_page = rows_per_page
        self.current_page = 1
        self.total_pages = 1
        
        self.pdf_margin_threshold = 50
        self.pdf_export_format = "md"
        self.patch_default_level = "-p1"  # 套用補丁時的預設參數（例如 -p1）
        self.pch_history_max = 10        # PCH 執行紀錄保留筆數上限
        self.pch_auto_delete = True      # PCH 成功套用後是否自動刪除來源 .patch 檔（僅限目錄搜尋來源）
        
        self.config_full_path = os.path.join(self.script_dir, "config.json")
        self.conf_dir = os.path.join(self.script_dir, "conf")
        if not os.path.exists(self.conf_dir): os.makedirs(self.conf_dir)

        self.history_file = os.path.join(self.conf_dir, "command_history.txt")
        self.history_max = 500
        
        self.selected_rows_per_page = 10  # 預設選取區行數
        self.selected_current_page = 1     # 選取區目前頁碼
        
        # --- 預先初始化忽略清單結構 ---
        self.all_ignore_versions = {"default": sorted(list(self.ignored_items))}
        self.current_ignore_version = "default"
        
        self.plugin_manager = PluginManager(self.script_dir)
        self.load_config()
        self.plugin_manager.notify_loaded(self)
        self.scan_directory()
    
    def is_ignored(self, rel_path):
        """檢查路徑是否符合使用者設定的忽略模式（支援 * 萬用字元比對）"""
        # 將路徑統一轉換為正斜線，便於模式匹配
        normalized_path = rel_path.replace(os.path.sep, '/')
        base_name = os.path.basename(normalized_path)

        for pattern in self.ignored_items:
            # 統一將模式中的反斜線轉為正斜線
            pattern_norm = pattern.replace(os.path.sep, '/')
            
            # 1. 支援萬用字元 (fnmatch 比對)
            if '*' in pattern_norm or '?' in pattern_norm:
                # 既比對完整相對路徑，也比對單純檔名
                if fnmatch.fnmatch(normalized_path, pattern_norm) or fnmatch.fnmatch(base_name, pattern_norm):
                    return True
            # 2. 標準精確或部分路徑匹配
            else:
                if pattern_norm in normalized_path or normalized_path.startswith(pattern_norm):
                    return True
        return False

    # --- 修改後的 load_config ---
    def load_config(self, config_path=None):
        target = config_path if config_path else self.config_full_path
        if os.path.exists(target):
            try:
                with open(target, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    self.selected_rows_per_page = cfg.get('selected_rows_per_page', 10)                    
                    raw_ignored = cfg.get('ignored_items', {})
                    if isinstance(raw_ignored, list): 
                        self.all_ignore_versions = {"default": raw_ignored}
                    else:
                        self.all_ignore_versions = raw_ignored
                    
                    self.current_ignore_version = cfg.get('current_ignore_version', 'default')
                    current_list = self.all_ignore_versions.get(self.current_ignore_version, [])
                    self.ignored_items = set(current_list)

                    self.work_paths = cfg.get('work_path_list', {})
                    self.pdf_margin_threshold = cfg.get('pdf_margin_threshold', 50)
                    self.pdf_export_format = cfg.get('pdf_export_format', "md")
                    self.patch_default_level = cfg.get('patch_default_level', "-p1")
                    self.pch_history_max = cfg.get('pch_history_max', 10)
                    self.pch_auto_delete = cfg.get('pch_auto_delete', True)
                    name = cfg.get('current_work_path_name')
                    if name in self.work_paths:
                        self.current_work_path_name = name
                        self.work_path = os.path.normpath(self.work_paths[name])
                        self.current_path = self.work_path
                return True
            except Exception as e:
                print(f"載入設定失敗: {e}")
        return False

    def generate_project_tree(self, current_dir, prefix=""):
        """
        遞迴走訪實體目錄，產生符合忽略條件（ignored_items）的完整專案樹狀圖
        """
        lines = []
        try:
            items = sorted(os.listdir(current_dir))
        except Exception as e:
            return [prefix + f"⚠️ 無法讀取目錄 ({e})"]

        valid_items = []
        for item in items:
            full_path = os.path.join(current_dir, item)
            rel_path = os.path.relpath(full_path, self.work_path)
            
            # 使用統一的 is_ignored 進行檢查
            if self.is_ignored(rel_path):
                continue
            valid_items.append((item, full_path))

        total = len(valid_items)
        for i, (item, full_path) in enumerate(valid_items):
            is_last = (i == total - 1)
            connector = "└── " if is_last else "├── "
            
            if os.path.isdir(full_path):
                lines.append(f"{prefix}{connector}📁 {item}")
                next_prefix = prefix + ("    " if is_last else "│   ")
                lines.extend(self.generate_project_tree(full_path, next_prefix))
            else:
                lines.append(f"{prefix}{connector}{item}")
                
        return lines

    def generate_tree_from_selected(self):
        """依 selected_items 相對路徑組成的樹狀圖（不掃描實體目錄）"""
        dir_name = self.current_work_path_name or os.path.basename(self.work_path) or "Selected"
        tree_lines = [f"📦 {dir_name} (僅選取檔案)"]
        items = sorted(list(self.selected_items))
        total = len(items)
        for i, rel_path in enumerate(items):
            is_last = (i == total - 1)
            connector = "└── " if is_last else "├── "
            tree_lines.append(f"{connector}{rel_path.replace(os.path.sep, '/')}")
        return tree_lines

    def handle_project_tree(self, args=None):
        """TREE 指令：掃描並顯示目錄樹狀結構，支援 purge 參數"""
        args = args or []
        purge = any(a.strip().lower() == 'purge' for a in args)

        if purge:
            try:
                old_trees = [
                    fn for fn in os.listdir(self.current_path)
                    if fn.startswith(TREE_EXPORT_PREFIX) and fn.endswith(TREE_EXPORT_EXT)
                    and os.path.isfile(os.path.join(self.current_path, fn))
                ]
            except Exception as e:
                print(f"⚠️ 搜尋舊目錄樹檔失敗: {e}")
                old_trees = []

            if old_trees:
                print(f"🗑️ purge: 偵測到 {len(old_trees)} 個舊目錄樹檔，刪除中...")
                for fn in old_trees:
                    try:
                        os.remove(os.path.join(self.current_path, fn))
                        print(f"   - 已刪除: {fn}")
                    except Exception as e:
                        print(f"   - 刪除失敗: {fn} ({e})")
            else:
                print("ℹ️ purge: 目前目錄未找到舊目錄樹檔。")

        scope_selected = False
        if self.selected_items:
            ans = input(f"目前有 {len(self.selected_items)} 個已選取檔案，是否僅針對選取檔案產生目錄樹？(y/N): ").strip().lower()
            scope_selected = ans in ('y', 'yes')

        if scope_selected:
            tree_lines = self.generate_tree_from_selected()
        else:
            target_dir = self.current_path
            print(f"\n正在掃描目錄: {target_dir} (已自動忽略 -I 設定之項目)...")
            dir_name = os.path.basename(target_dir) or "Current Dir"
            tree_lines = [f"📦 {dir_name}"]
            tree_lines.extend(self.generate_project_tree(target_dir))

        full_tree_str = "\n".join(tree_lines)

        print("\n" + "="*40)
        print(full_tree_str)
        print("="*40)

        try:
            pyperclip.copy(full_tree_str)
            print("📋 [提示] 目錄樹已自動複製到您的剪貼簿！")
        except:
            pass

        ans2 = input("是否另存新檔？(y/N): ").strip().lower()
        if ans2 in ('y', 'yes'):
            name = f"{TREE_EXPORT_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}{TREE_EXPORT_EXT}"
            save_path = os.path.join(self.current_path, name)
            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(full_tree_str)
                print(f"✅ 已另存新檔: {name}")
            except Exception as e:
                print(f"⚠️ 儲存失敗: {e}")

        input("\n按 Enter 繼續...")

    def save_config(self):
        self.all_ignore_versions[self.current_ignore_version] = sorted(list(self.ignored_items))
        cfg = {
            "ignored_items": self.all_ignore_versions, 
            "current_ignore_version": self.current_ignore_version,
            "work_path_list": self.work_paths, 
            "current_work_path_name": self.current_work_path_name, 
            "work_path": self.work_path,
            "pdf_margin_threshold": self.pdf_margin_threshold,
            "pdf_export_format": self.pdf_export_format,
            "patch_default_level": self.patch_default_level,
            "pch_history_max": self.pch_history_max,
            "pch_auto_delete": self.pch_auto_delete
        }
        with open(self.config_full_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    def scan_directory(self):
        try:
            # 修正：過濾列表項目時，統一呼叫 is_ignored 邏輯，使萬用字元過濾在主畫面即生效
            items = []
            for i in os.listdir(self.current_path):
                full_p = os.path.join(self.current_path, i)
                rel_p = os.path.relpath(full_p, self.work_path)
                if not self.is_ignored(rel_p):
                    items.append(i)

            dirs = sorted([d for d in items if os.path.isdir(os.path.join(self.current_path, d))])
            files = sorted([f for f in items if os.path.isfile(os.path.join(self.current_path, f))])
            self.file_list = [{'name': d, 'type': 'dir'} for d in dirs] + [{'name': f, 'type': 'file'} for f in files]
            self.total_pages = max(1, math.ceil(len(self.file_list) / self.rows_per_page))
        except:
            self.file_list = []; self.total_pages = 1
            if self.current_path != self.work_path: self.handle_updir()

    def display(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{'='*75}\n  工具管理員 {PROGRAM_VERSION} | 專案: [{self.current_work_path_name}]\n{'-'*75}")
        print(f" 路徑: {self.current_path}")
        print(f"{'-'*75}")

        start = (self.current_page - 1) * self.rows_per_page
        for i, item in enumerate(self.file_list[start : start + self.rows_per_page]):
            idx = start + i + 1
            rel = os.path.relpath(os.path.join(self.current_path, item['name']), self.work_path)
            sel = "[ + ]" if rel in self.selected_items else "[   ]"
            icon = "[ DIR ]" if item['type'] == 'dir' else sel
            print(f"{idx:3} {icon} {item['name']}")
        print(f" 目錄分頁: {self.current_page}/{self.total_pages}")
        
        print(f"{'-'*30} 已選取檔案清單 {'-'*30}")

        sorted_sel = sorted(list(self.selected_items))
        sel_count = len(sorted_sel)
        sel_total_pages = max(1, math.ceil(sel_count / self.selected_rows_per_page))
        
        self.selected_current_page = max(1, min(self.selected_current_page, sel_total_pages))
        s_start = (self.selected_current_page - 1) * self.selected_rows_per_page
        display_sel = sorted_sel[s_start : s_start + self.selected_rows_per_page]

        if not display_sel:
            print(" (目前尚未選取任何檔案)")
        else:
            for i, rel_path in enumerate(display_sel):
                s_idx = s_start + i + 1
                print(f" {s_idx:2}. {rel_path}")
        
        print(f"{'-'*75}")
        print(f" 選取區分頁: {self.selected_current_page}/{sel_total_pages} (總計: {sel_count})")
        # --- 顯示已發現的外掛 ---
        if hasattr(self, 'plugin_manager') and self.plugin_manager.plugins:
            print(f"{'-'*75}")
            print(f"  🔌 已載入外掛 ({len(self.plugin_manager.plugins)}):", end=" ")
            plugs = [f"[{p['cmd']}] {p['name']}" for p in self.plugin_manager.plugins.values()]
            print(" | ".join(plugs))
        print(f" 指令: [N/P] 目錄翻頁 | [SN/SP] 選取區翻頁 | [H] 幫助 | [PLUG] 外掛列表")

    def show_help(self):
        print(f"\n{'='*20} 指令說明 {'='*20}")
        print(" [數字]         : 選取檔案 / 進入目錄")
        print(" [0]            : 回上一層 | [00] 回專案根目錄")
        print(" [PLUG]         : 列出所有已載入外掛及使用方式（A/ZIP/UA/PDF/PCH/PA/VC 已改為外掛，見 PLUG 列表）")
        print(" [I <ptn/n>]    : 忽略指定模式(支援 * 萬用字元)或列表編號")
        print(" [D <數字>]     : 刪除列表中指定編號的檔案/資料夾")
        print(" [S ALL/CLR]    : 遞迴全選所有檔案 / 清空選取")
        print(" [S <始> <終>]  : 選取列表中指定範圍的檔案")
        print(" [S <萬用字元> [ALL|RECU]] : 依檔名比對選取，預設僅目前頁面；ALL=根目錄遞迴，RECU=目前目錄遞迴 (例: S *.py ALL)")
        print(" [CONF]         : 切換設定檔 | [RP] 專案管理")
        print(" [N/P] 換頁 | [E] 退出")
        print(" [TREE]         : 顯示專案完整目錄樹")
        if hasattr(self, 'plugin_manager') and self.plugin_manager.plugins:
            print(f"\n{'='*20} 已載入外掛 {'='*20}")
            for p in self.plugin_manager.plugins.values():
                print(f" [{p['cmd']}] {p['name']}: {p['desc']}")
                if p['usage']:
                    print(f"      用法: {p['usage']}")
        print("-" * 50)
        input("按 Enter 返回...")

    def handle_click(self, idx_str):
        try:
            idx = int(idx_str) - 1
            if 0 <= idx < len(self.file_list):
                item = self.file_list[idx]
                path = os.path.join(self.current_path, item['name'])
                if item['type'] == 'dir':
                    self.current_path = path; self.current_page = 1; self.scan_directory()
                else:
                    rel = os.path.relpath(path, self.work_path)
                    if rel in self.selected_items: self.selected_items.remove(rel)
                    else: self.selected_items.add(rel)
        except: pass

    def handle_delete(self, args):
        if not args:
            if not self.selected_items:
                print("❌ 未選取任何檔案，且未指定編號")
                input("按 Enter 繼續...")
                return
            self.handle_delete_selected()
            return
        try:
            idx = int(args[0]) - 1
            item = self.file_list[idx]
            path = os.path.join(self.current_path, item['name'])
            confirm = input(f"⚠️ 確定要刪除 {item['type']} '{item['name']}'? (y/N): ").lower()
            if confirm == 'y':
                if item['type'] == 'dir':
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                print(f"✅ 已刪除: {item['name']}")
                self.scan_directory()
        except Exception as e: print(f"❌ 刪除失敗: {e}")
        input("按 Enter 繼續...")

    def handle_delete_selected(self):
        """依目前 S 選取的內容執行刪除（無指定編號時的 D 指令行為）"""
        items = sorted(list(self.selected_items))
        print(f"\n目前已選取 {len(items)} 個項目:")
        for rel in items:
            print(f"  - {rel}")
        confirm = input(f"⚠️ 確定要刪除以上 {len(items)} 個已選取項目? (y/N): ").strip().lower()
        if confirm != 'y':
            print("已取消刪除。")
            input("按 Enter 繼續...")
            return

        success, failed = 0, []
        for rel in items:
            full_path = os.path.normpath(os.path.join(self.work_path, rel))
            try:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                elif os.path.isfile(full_path):
                    os.remove(full_path)
                else:
                    failed.append((rel, "路徑不存在"))
                    continue
                success += 1
                self.selected_items.discard(rel)
            except Exception as e:
                failed.append((rel, str(e)))

        print(f"✅ 完成，成功刪除 {success} 項，失敗 {len(failed)} 項")
        for rel, err in failed:
            print(f"  - 刪除失敗: {rel} ({err})")
        self.scan_directory()
        input("按 Enter 繼續...")

    def handle_recursive_select(self):
        print(f"正在從 {self.current_path} 遞迴選取所有檔案...")
        count = 0
        for root, dirs, files in os.walk(self.current_path):
            # 動態過濾不應進入的資料夾
            dirs[:] = [d for d in dirs if not self.is_ignored(os.path.relpath(os.path.join(root, d), self.work_path))]
            for f in files:
                full_p = os.path.join(root, f)
                rel = os.path.relpath(full_p, self.work_path)
                if self.is_ignored(rel): 
                    continue
                self.selected_items.add(rel)
                count += 1
        print(f"✅ 已成功遞迴選取 {count} 個檔案。")
        input("按 Enter 繼續...")

    def handle_range_select(self, start_str, end_str):
        try:
            s_idx = int(start_str) - 1
            e_idx = int(end_str) - 1
            if s_idx > e_idx: s_idx, e_idx = e_idx, s_idx
            count = 0
            for i in range(max(0, s_idx), min(len(self.file_list), e_idx + 1)):
                item = self.file_list[i]
                if item['type'] == 'file':
                    path = os.path.join(self.current_path, item['name'])
                    rel = os.path.relpath(path, self.work_path)
                    self.selected_items.add(rel)
                    count += 1
            print(f"✅ 已從當前列表選取 {count} 個檔案。")
        except Exception as e: print(f"❌ 範圍選取失敗: {e}")
        input("按 Enter 繼續...")

    def handle_wildcard_select(self, pattern, mode=None):
        count = 0
        if mode == 'ALL':
            scope_desc = "專案根目錄遞迴"
            base_dir = self.work_path
        elif mode == 'RECU':
            scope_desc = "目前目錄遞迴"
            base_dir = self.current_path
        else:
            base_dir = None

        if base_dir is not None:
            for root, dirs, files in os.walk(base_dir):
                dirs[:] = [d for d in dirs if not self.is_ignored(os.path.relpath(os.path.join(root, d), self.work_path))]
                for f in files:
                    if not fnmatch.fnmatch(f, pattern): continue
                    rel = os.path.relpath(os.path.join(root, f), self.work_path)
                    if self.is_ignored(rel): continue
                    self.selected_items.add(rel)
                    count += 1
        else:
            scope_desc = "目前列表頁面"
            for item in self.file_list:
                if item['type'] == 'file' and fnmatch.fnmatch(item['name'], pattern):
                    rel = os.path.relpath(os.path.join(self.current_path, item['name']), self.work_path)
                    self.selected_items.add(rel)
                    count += 1

        print(f"✅ 已依萬用字元 '{pattern}' 於「{scope_desc}」選取 {count} 個檔案。")
        input("按 Enter 繼續...")

    def handle_updir(self):
        p = os.path.dirname(self.current_path)
        if p != self.current_path: self.current_path = p; self.current_page = 1; self.scan_directory()

    def handle_ignore(self, args):
        self.load_config()
        if not args:
            print("\n" + "="*30)
            print("  現有忽略名單版本列表:")
            versions = sorted(list(self.all_ignore_versions.keys()))
            for i, v in enumerate(versions, 1):
                status = "(使用中)" if v == self.current_ignore_version else ""
                print(f"  {i}. {v} {status}")
            print("="*30)
            
            sel = input("請選擇要載入的版本編號 (或按 Enter 取消): ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(versions):
                self.current_ignore_version = versions[int(sel)-1]
                self.ignored_items = set(self.all_ignore_versions[self.current_ignore_version])
                self.save_config()
                self.scan_directory()
                print(f"✅ 已切換至版本: {self.current_ignore_version}")
            return

        target = args[0]
        if target.isdigit():
            try:
                name = self.file_list[int(target)-1]['name']
                self.ignored_items.add(name)
            except:
                print("❌ 無效編號"); return
        else:
            # 直接加入使用者輸入的過濾模式（例如 *.pdf）
            self.ignored_items.add(target)

        print("\n已暫時加入名單。請選擇要儲存的目的地:")
        versions = sorted(list(self.all_ignore_versions.keys()))
        for i, v in enumerate(versions, 1):
            print(f"  {i}. 更新到現有版本: {v}")
        print(f"  {len(versions)+1}. 另存為新版本")
        
        save_sel = input("請選擇 (預設直接更新目前版本): ").strip()
        
        if save_sel == str(len(versions)+1):
            new_v_name = input("請輸入新版本名稱: ").strip()
            if new_v_name:
                self.current_ignore_version = new_v_name
        elif save_sel.isdigit() and 1 <= int(save_sel) <= len(versions):
            self.current_ignore_version = versions[int(save_sel)-1]

        self.save_config()
        self.scan_directory()
        input(f"✅ 忽略清單已更新並存入版本 [{self.current_ignore_version}]")
        
    def handle_rp(self, sub=None):
        if sub == 'S':
            keys = sorted(self.work_paths.keys())
            for i, k in enumerate(keys, 1): print(f" [{i}] {k}: {self.work_paths[k]}")
            try:
                sel = int(input("選擇專案: ")) - 1
                self.current_work_path_name = keys[sel]
                self.work_path = os.path.normpath(self.work_paths[self.current_work_path_name])
                self.current_path = self.work_path; self.selected_items.clear(); self.save_config(); self.scan_directory()
            except: pass
        else:
            n = input(f"名稱 (預設 {os.path.basename(self.current_path)}): ") or os.path.basename(self.current_path)
            self.work_paths[n] = os.path.normpath(self.current_path)
            self.current_work_path_name = n; self.work_path = self.work_paths[n]; self.save_config()

    def handle_conf_switch(self):
        files = sorted([f for f in os.listdir(self.conf_dir) if f.endswith('.json')])
        print(f"\n[設定檔] 0.預設核心")
        for i, f in enumerate(files, 1): print(f" {i}. {f}")
        idx = input("切換編號: ").strip()
        try:
            if idx == '0': self.load_config()
            else: self.load_config(os.path.join(self.conf_dir, files[int(idx)-1]))
            self.scan_directory(); input("✅ 已切換設定")
        except: pass

    # --- 指令歷史（上下鍵瀏覽） ---
    def load_history(self):
        if not readline:
            return
        readline.set_history_length(self.history_max)
        if os.path.exists(self.history_file):
            try:
                readline.read_history_file(self.history_file)
            except Exception as e:
                print(f"⚠️ 讀取指令歷史失敗: {e}")

    def save_history(self):
        if not readline:
            return
        try:
            readline.write_history_file(self.history_file)
        except Exception as e:
            print(f"⚠️ 儲存指令歷史失敗: {e}")

# ==============================================================================
# 主程式
# ==============================================================================

def main():
    fm = FileManager()
    fm.load_history()
    atexit.register(fm.save_history)
    if not readline:
        print("⚠️ 未偵測到 readline，Windows 請安裝 pyreadline3 以啟用上下鍵指令歷史。")
    while True:
        fm.display()
        inp_str = input("\n指令 (H 查看幫助): ").strip()
        if readline:
            n = readline.get_current_history_length()
            if n > 0:
                dup = n > 1 and readline.get_history_item(n) == readline.get_history_item(n - 1)
                if not inp_str or dup:
                    readline.remove_history_item(n - 1)
        if not inp_str: fm.scan_directory(); continue
        inp = inp_str.split()
        cmd = inp[0].upper()
        
        if cmd == 'E': break
        elif cmd == 'N': fm.current_page = min(fm.total_pages, fm.current_page + 1)
        elif cmd == 'P': fm.current_page = max(1, fm.current_page - 1)
        elif cmd == 'SN':
            sel_total_pages = max(1, math.ceil(len(fm.selected_items) / fm.selected_rows_per_page))
            fm.selected_current_page = min(sel_total_pages, fm.selected_current_page + 1)
        elif cmd == 'SP':
            fm.selected_current_page = max(1, fm.selected_current_page - 1)        
        elif cmd == 'H': fm.show_help()
        elif cmd == 'PLUG':
            fm.plugin_manager.scan()
            print(f"\n{'='*20} 外掛列表 {'='*20}")
            if not fm.plugin_manager.plugins:
                print(" (plugins/ 目錄下沒有發現外掛)")
            else:
                for p in fm.plugin_manager.plugins.values():
                    print(f" [{p['cmd']}] {p['name']} - {p['desc']}")
                    print(f"      檔案: {p['file']} | 用法: {p['usage']}")
            input("\n按 Enter 返回...")
        elif cmd == 'RELOAD_PLUG':
            fm.plugin_manager.scan()
            fm.plugin_manager.notify_loaded(fm)
            print(f"✅ 已重新掃描，發現 {len(fm.plugin_manager.plugins)} 個外掛")
            input("按 Enter...")
        elif cmd == '00': fm.current_path = fm.work_path; fm.scan_directory()
        elif cmd == '0': fm.handle_updir()
        elif cmd.isdigit(): fm.handle_click(cmd)
        elif cmd == 'I': fm.handle_ignore(inp[1:])
        elif cmd == 'D': fm.handle_delete(inp[1:])
        elif cmd == 'RP': fm.handle_rp(inp[1].upper() if len(inp)>1 else None)
        elif cmd == 'CONF': fm.handle_conf_switch()
        elif cmd == 'TREE': fm.handle_project_tree(inp[1:])
        elif cmd == 'S' and len(inp)>1:
            arg1_raw = inp[1]
            arg1 = arg1_raw.upper()
            if arg1 == 'ALL':
                fm.handle_recursive_select()
            elif arg1 == 'CLR':
                # s clr all = 清除所有選取項目
                if len(inp) > 2 and inp[2].upper() == 'ALL':
                    count = len(fm.selected_items)
                    fm.selected_items.clear()
                    input(f"✅ 已清空所有選取內容 ({count} 項)。")
                else:
                    # s clr = 遞迴清除目前位置以及子目錄中被選取者
                    rel_current = os.path.relpath(fm.current_path, fm.work_path)
                    if rel_current == '.':
                        rel_current = ''
                    
                    if rel_current == '':
                        to_remove = set(fm.selected_items)
                    else:
                        to_remove = set()
                        prefix = rel_current + os.sep
                        for item in fm.selected_items:
                            if item == rel_current or item.startswith(prefix):
                                to_remove.add(item)
                    
                    if to_remove:
                        fm.selected_items -= to_remove
                        display_path = rel_current or '.'
                        input(f"✅ 已遞迴清除 [{display_path}] 底下的 {len(to_remove)} 項選取。")
                    else:
                        display_path = rel_current or '.'
                        input(f"ℹ️ 在 [{display_path}] 底下沒有已選取的項目。")
            elif arg1.isdigit() and len(inp) > 2 and inp[2].isdigit():
                fm.handle_range_select(inp[1], inp[2])
            elif '*' in arg1_raw or '?' in arg1_raw:
                mode = inp[2].upper() if len(inp) > 2 else None
                fm.handle_wildcard_select(arg1_raw, mode)
        else:
            # --- 外掛分派：不需修改主程式，自動呼叫 ---
            if hasattr(fm, 'plugin_manager') and cmd in fm.plugin_manager.plugins:
                fm.plugin_manager.run(cmd, fm, inp[1:])
            else:
                print(f"❌ 未知指令: {cmd} (輸入 H 查看幫助, PLUG 查看外掛)")
                input("按 Enter...")

if __name__ == "__main__":
    main()
