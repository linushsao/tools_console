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
import shutil 
import pyperclip 
import sys
import fnmatch  # 引入萬用字元比對庫

# PDF 支援庫檢查
try:
    import fitz  # PyMuPDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

PROGRAM_VERSION = "V0.4-060-PluginSystem"
MAX_HEADER_LINES = 15

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
                    'file': fname
                }
            except Exception as e:
                print(f"[外掛載入失敗] {fname}: {e}")
                traceback.print_exc()

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
# 工具組 (VersionParser, Archiver Core)
# ==============================================================================

class VersionParser:
    VERSION_PATTERN = r'(V\d+\.\d+-\d{3})' 
    VERSION_REGEX = re.compile(r'#\s*Version:\s*(' + VERSION_PATTERN + r'(.*?))\s*(\((.*?)\))?$')

    def __init__(self, file_path):
        self.file_path = file_path
        self.relative_path = ""
        self.version_full = None
        self.error = None

    def analyze(self, root_dir):
        self.relative_path = os.path.relpath(self.file_path, root_dir)
        try:
            if not os.path.isfile(self.file_path): return
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = [f.readline() for _ in range(MAX_HEADER_LINES)]
            for line in lines:
                if not line: break
                mv = self.VERSION_REGEX.search(line)
                if mv:
                    self.version_full = mv.group(1)
                    return
            self.error = "找不到標籤"
        except Exception as e: self.error = str(e)

    def generate_new_header(self, new_v, new_log):
        new_date = datetime.now().strftime('%Y-%m-%d')
        return [f"# Version: {new_v}\n", f"# 更新日期: {new_date}\n", f"# {new_v}: {new_log}\n"]

def archive_selected_files(work_path, selected_items, project_name="Default"):
    files_data = {}  # 用於存放符合新邏輯的檔案映射
    file_count = 0
    for rel_path in sorted(list(selected_items)):
        full_path = os.path.normpath(os.path.join(work_path, rel_path))
        if not os.path.isfile(full_path): continue
        json_key = rel_path.replace(os.path.sep, '/')
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                files_data[json_key] = f.read()
        except:
            with open(full_path, 'rb') as f:
                files_data[json_key] = base64.b64encode(f.read()).decode('utf-8')
        file_count += 1
    
    # 建立符合規範的全新結構
    archive_data = {
        "project_name": project_name,
        "files": files_data,
        "__metadata": {  # 保留中介資料供 CLI 工具內部分析，不影響標準規範讀取
            "original_root_name": os.path.basename(work_path),
            "archive_timestamp": datetime.now().isoformat(),
            "file_count": file_count
        }
    }
    return archive_data, file_count

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
        
        self.config_full_path = os.path.join(self.script_dir, "config.json")
        self.conf_dir = os.path.join(self.script_dir, "conf")
        if not os.path.exists(self.conf_dir): os.makedirs(self.conf_dir)
        
        self.selected_rows_per_page = 10  # 預設選取區行數
        self.selected_current_page = 1     # 選取區目前頁碼
        
        # --- 預先初始化忽略清單結構 ---
        self.all_ignore_versions = {"default": sorted(list(self.ignored_items))}
        self.current_ignore_version = "default"
        
        self.plugin_manager = PluginManager(self.script_dir)
        self.load_config()
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

    def handle_project_tree(self):
        """TREE 指令：掃描並顯示目前所在目錄的樹狀結構"""
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
            "pdf_export_format": self.pdf_export_format
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
        print(f" PDF: 門檻={self.pdf_margin_threshold}, 格式={self.pdf_export_format}\n{'-'*75}")

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
        print(" [A]            : 打包選取檔案為 JSON (含目錄樹)")
        print(" [ZIP]          : 壓縮選取檔案為 ZIP 壓縮檔")
        print(" [UA]           : 解包選取的 JSON 檔案並還原至同目錄結構")
        print(" [PDF]          : 轉換 PDF (座標過濾去行號)")
        print(" [I <ptn/n>]    : 忽略指定模式(支援 * 萬用字元)或列表編號")
        print(" [D <數字>]     : 刪除列表中指定編號的檔案/資料夾")
        print(" [S ALL/CLR]    : 遞迴全選所有檔案 / 清空選取")
        print(" [S <始> <終>]  : 選取列表中指定範圍的檔案")
        print(" [PA <pattern>] : 在已選取檔案中搜尋特定內容")
        print(" [CONF]         : 切換設定檔 | [RP] 專案管理")
        print(" [VC]           : 更新版本標籤 | [N/P] 換頁 | [E] 退出")
        print(" [A] 打包選取   [UA] 解包JSON   [ZIP] 壓縮選取   [TREE] 專案完整目錄樹")
        print(" [PLUG]         : 列出所有已載入外掛及使用方式")
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
        if not args: print("❌ 請指定編號"); input(); return
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

    def handle_pattern_analysis(self, args):
        if not args: print("❌ 請輸入要搜尋的 Pattern"); input(); return
        if not self.selected_items: print("❌ 未選取任何檔案"); input(); return
        
        pattern = " ".join(args)
        found_list = []
        print(f"正在搜尋關鍵字: '{pattern}' ...")
        
        for rel in sorted(list(self.selected_items)):
            full_path = os.path.join(self.work_path, rel)
            if not os.path.isfile(full_path): continue
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if pattern in content:
                        found_list.append(rel)
            except Exception: pass

        if found_list:
            print(f"\n{'='*10} 符合條件的檔案 ({len(found_list)}) {'='*10}")
            for p in found_list: print(f" [MATCH] {p}")
        else:
            print(f"❌ 未在選取的檔案中找到關鍵字: '{pattern}'")
        input("\n按 Enter 繼續...")

    def handle_updir(self):
        p = os.path.dirname(self.current_path)
        if p != self.current_path: self.current_path = p; self.current_page = 1; self.scan_directory()

    def handle_pdf_convert(self):
        if not PDF_SUPPORT: print("❌ 未安裝 PyMuPDF"); input(); return
        pdf_targets = [os.path.join(self.work_path, p) for p in self.selected_items if p.lower().endswith('.pdf')]
        if not pdf_targets: print("❌ 未選取 PDF"); input(); return
        
        print(f"\n[PDF] 1.開始 2.格式({self.pdf_export_format}) 3.門檻({self.pdf_margin_threshold})")
        c = input("選擇: ").strip()
        if c == '2':
            self.pdf_export_format = "txt" if self.pdf_export_format == "md" else "md"
            self.save_config(); return self.handle_pdf_convert()
        elif c == '3':
            v = input("新門檻: ").strip()
            if v.isdigit(): self.pdf_margin_threshold = int(v); self.save_config()
            return self.handle_pdf_convert()
        elif c != '1': return

        for pdf_path in pdf_targets:
            out = pdf_path.rsplit('.', 1)[0] + "." + self.pdf_export_format
            try:
                doc = fitz.open(pdf_path)
                res = []
                for i, page in enumerate(doc):
                    blocks = page.get_text("blocks")
                    clean = [b[4].strip() for b in blocks if b[0] > self.pdf_margin_threshold]
                    if self.pdf_export_format == "md": res.append(f"\n## --- Page {i+1} ---\n")
                    res.extend(clean)
                with open(out, "w", encoding="utf-8") as f: f.write("\n".join(res))
                print(f"✅ 成功: {os.path.basename(out)}")
            except Exception as e: print(f"❌ 失敗: {os.path.basename(pdf_path)} ({e})")
        self.scan_directory(); input("按 Enter 繼續...")

    def handle_archive(self):
        if not self.selected_items: print("❌ 未選取"); input(); return
        data, count = archive_selected_files(self.work_path, self.selected_items, self.current_work_path_name)
        tree_str = self.generate_tree_string(self.selected_items)
        data["__metadata"]["tree_view"] = tree_str
        name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(os.path.join(self.current_path, name), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ 打包成功!\n{tree_str}"); input("Enter 繼續...")

    def handle_zip(self):
        import zipfile
        if not self.selected_items: 
            print("❌ 未選取任何檔案，無法進行壓縮"); 
            input(); 
            return
        
        zip_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(self.current_path, zip_name)
        
        print(f"📦 開始將選取的 {len(self.selected_items)} 個項目打包為 ZIP...")
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for rel_path in self.selected_items:
                    full_path = os.path.normpath(os.path.join(self.work_path, rel_path))
                    if os.path.isfile(full_path):
                        zipf.write(full_path, rel_path)
                        print(f"  ➕ 已加入檔案: {rel_path}")
                    elif os.path.isdir(full_path):
                        print(f"  📂 正在打包資料夾: {rel_path}")
                        for root, dirs, files in os.walk(full_path):
                            for file in files:
                                f_full = os.path.join(root, file)
                                f_rel = os.path.relpath(f_full, self.work_path)
                                zipf.write(f_full, f_rel)
            
            tree_str = self.generate_tree_string(self.selected_items)
            print(f"\n✅ ZIP 壓縮成功!\n產出檔案: {zip_name}\n\n【包含結構】\n{tree_str}")
        except Exception as e:
            print(f"❌ ZIP 壓縮失敗: {str(e)}")
        input("按 Enter 繼續...")

    def handle_unarchive(self):
        json_targets = [p for p in self.selected_items if p.lower().endswith('.json')]
        if not json_targets:
            print("❌ 未選取任何封存 JSON 檔案進行解包。")
            input("按 Enter 繼續...")
            return

        print(f"發現 {len(json_targets)} 個選取的 JSON 封存檔，開始解包還原...")
        for rel_json_path in json_targets:
            full_json_path = os.path.normpath(os.path.join(self.work_path, rel_json_path))
            if not os.path.isfile(full_json_path):
                print(f"⚠️ 找不到實體檔案: {rel_json_path}")
                continue
            
            json_dir = os.path.dirname(full_json_path)
            print(f"\n正在解包處理: {rel_json_path} -> 還原至目錄: {json_dir}")
            
            try:
                with open(full_json_path, 'r', encoding='utf-8') as f:
                    archive_data = json.load(f)
                
                files_dict = archive_data.get("files", archive_data)
                
                if "__metadata" not in archive_data and "files" not in archive_data:
                    print(f"⚠️ 檔案 {rel_json_path} 不包含合法的封存特徵，跳過。")
                    continue
                
                unpack_count = 0
                for file_key, content in files_dict.items():
                    if file_key in ("__metadata", "project_name"):
                        continue
                    
                    local_rel_path = file_key.replace('/', os.path.sep)
                    
                    clean_rel_path = local_rel_path
                    sep_str = os.path.sep
                    parent_prefix = '..' + sep_str
                    
                    while clean_rel_path.startswith(parent_prefix) or clean_rel_path == '..':
                        if clean_rel_path == '..':
                            clean_rel_path = ''
                            break
                        clean_rel_path = clean_rel_path[len(parent_prefix):]
                    
                    clean_rel_path = clean_rel_path.lstrip(sep_str)
                    
                    full_dest_path = os.path.normpath(os.path.join(json_dir, clean_rel_path))
                    
                    dest_dir = os.path.dirname(full_dest_path)
                    if dest_dir and not os.path.exists(dest_dir):
                        os.makedirs(dest_dir, exist_ok=True)
                    
                    is_base64 = False
                    if isinstance(content, str) and not any(c in content for c in " \t\n\r{},;:\"'()[]<>#-_!@$%^&*=|\\~`"):
                        if len(content) % 4 == 0 and re.match(r'^[A-Za-z0-9+/]*={0,2}$', content):
                            try:
                                decoded_bytes = base64.b64decode(content)
                                ext = os.path.splitext(file_key)[1].lower()
                                if ext in ['.py', '.json', '.lua', '.md', '.txt', '.html', '.css', '.js', '.yaml', '.yml', '.sh', '.conf', '.mod']:
                                    is_base64 = False
                                elif ext in ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz', '.7z', '.rar']:
                                    is_base64 = True
                                else:
                                    if b'\x00' in decoded_bytes or len([b for b in decoded_bytes if b < 32 and b not in (9, 10, 13)]) > len(decoded_bytes) * 0.1:
                                        is_base64 = True
                                    else:
                                        is_base64 = False
                            except:
                                is_base64 = False
                    
                    if is_base64:
                        with open(full_dest_path, 'wb') as out_f:
                            out_f.write(base64.b64decode(content))
                    else:
                        with open(full_dest_path, 'w', encoding='utf-8') as out_f:
                            out_f.write(content)
                    
                    print(f"  [DEBUG] 還原檔案: {file_key} -> {full_dest_path}")
                    unpack_count += 1
                
                print(f"✅ 成功還原該包內共 {unpack_count} 個檔案結構。")
            except Exception as e:
                print(f"❌ 解包檔案 {rel_json_path} 失敗: {e}")
                
        self.scan_directory()
        input("\n還原完畢，按 Enter 繼續...")

    def generate_tree_string(self, selected_items):
        tree = {}
        for path in sorted(selected_items):
            parts = path.replace(os.path.sep, '/').split('/')
            curr = tree
            for p in parts: curr = curr.setdefault(p, {})
        lines = [f"📦 {self.current_work_path_name}"]
        def build(node, prefix=""):
            items = sorted(node.keys())
            for i, name in enumerate(items):
                is_l = (i == len(items)-1); conn = "└── " if is_l else "├── "
                lines.append(f"{prefix}{conn}{name}")
                if node[name]: build(node[name], prefix + ("    " if is_l else "│   "))
        build(tree); return "\n".join(lines)

    # --- 修改後的 handle_ignore ---
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

    def handle_vc(self):
        parsers = []
        for rel in self.selected_items:
            p = VersionParser(os.path.join(self.work_path, rel)); p.analyze(self.work_path); parsers.append(p)
        for p in parsers: print(f" - {p.relative_path}: {p.version_full or p.error}")
        v = input("新版本號: "); log = input("日誌: ")
        if v:
            for p in parsers:
                if p.error and p.error != "找不到標籤": continue
                new_h = p.generate_new_header(v, log)
                with open(p.file_path, 'r', encoding='utf-8') as f: content = f.readlines()
                with open(p.file_path, 'w', encoding='utf-8') as f: f.writelines(new_h + content)
            input("✅ 版本更新完成")

# ==============================================================================
# 主程式
# ==============================================================================

def main():
    fm = FileManager()
    while True:
        fm.display()
        inp_str = input("\n指令 (H 查看幫助): ").strip()
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
            print(f"✅ 已重新掃描，發現 {len(fm.plugin_manager.plugins)} 個外掛")
            input("按 Enter...")
        elif cmd == '00': fm.current_path = fm.work_path; fm.scan_directory()
        elif cmd == '0': fm.handle_updir()
        elif cmd.isdigit(): fm.handle_click(cmd)
        elif cmd == 'I': fm.handle_ignore(inp[1:])
        elif cmd == 'D': fm.handle_delete(inp[1:])
        elif cmd == 'A': fm.handle_archive()
        elif cmd == 'UA': fm.handle_unarchive()
        elif cmd == 'ZIP': fm.handle_zip()
        elif cmd == 'PDF': fm.handle_pdf_convert()
        elif cmd == 'RP': fm.handle_rp(inp[1].upper() if len(inp)>1 else None)
        elif cmd == 'VC': fm.handle_vc()
        elif cmd == 'CONF': fm.handle_conf_switch()
        elif cmd == 'PA': fm.handle_pattern_analysis(inp[1:])
        elif cmd == 'TREE': fm.handle_project_tree()
        elif cmd == 'S' and len(inp)>1:
            arg1 = inp[1].upper()
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
        else:
            # --- 外掛分派：不需修改主程式，自動呼叫 ---
            if hasattr(fm, 'plugin_manager') and cmd in fm.plugin_manager.plugins:
                fm.plugin_manager.run(cmd, fm, inp[1:])
            else:
                print(f"❌ 未知指令: {cmd} (輸入 H 查看幫助, PLUG 查看外掛)")
                input("按 Enter...")

if __name__ == "__main__":
    main()
