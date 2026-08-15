# ==============================================================================
# plugins/py_rename.py
# 外掛名稱: Py-Rename
# 指令: RENAME
# Version: V1.0-001
# 描述: 重命名 .py 檔案並自動修正專案內所有引用
# ==============================================================================
import os
import re
import sys
import shutil
import subprocess
from pathlib import Path

__plugin_name__ = "Py-Rename"
__plugin_command__ = "RENAME"
__plugin_description__ = "重命名 .py 檔案並修正專案內所有 import 引用"
__plugin_usage__ = "RENAME [舊檔] [新檔]  |  RENAME (互動模式)  |  RENAME --dry-run"

EXCLUDE_DIRS = {'.git', '__pycache__', '.venv', 'venv', '.mypy_cache', '.pytest_cache', '.ropeproject', 'node_modules', '.tox', 'build', 'dist', 'plugins'}

def is_excluded(path: Path, root: Path):
    try:
        rel_parts = path.relative_to(root).parts
        for part in rel_parts:
            if part in EXCLUDE_DIRS:
                return True
    except:
        pass
    return False

def find_py_files(root: Path):
    for p in root.rglob("*.py"):
        if is_excluded(p, root):
            continue
        # 跳過自己
        if p.name == "py_rename.py" and "plugins" in str(p):
            continue
        yield p

def run(file_manager, args):
    """
    外掛入口
    file_manager: 主程式的 FileManager 實例，提供 work_path, current_path, selected_items 等
    args: 使用者輸入的參數列表 (已去掉 RENAME)
    """
    root = Path(file_manager.work_path).resolve()
    current_dir = Path(file_manager.current_path).resolve()

    print(f"\n{'='*20} 🔌 {__plugin_name__} {'='*20}")
    print(f"專案根目錄: {root}")
    print(f"目前目錄: {current_dir}")
    print(f"已選取檔案: {len(file_manager.selected_items)} 個")

    # 參數解析
    old_input_str = None
    new_input_str = None
    dry_run = False

    if args:
        if '--dry-run' in args or '--dry' in args:
            dry_run = True
            args = [a for a in args if not a.startswith('--dry')]
        if len(args) >= 2:
            old_input_str = args[0]
            new_input_str = args[1]
        elif len(args) == 1:
            old_input_str = args[0]

    # 互動模式
    if not old_input_str:
        # 如果有選取檔案，提示可直接選
        if file_manager.selected_items:
            print("\n已選取檔案 (可直接輸入編號選擇要改名的檔案):")
            sel_list = sorted(list(file_manager.selected_items))
            for i, f in enumerate(sel_list[:10], 1):
                if f.endswith('.py'):
                    print(f"  {i}. {f}")
        old_input_str = input("\n請輸入舊檔名 (e.g. utils.py 或 src/utils.py): ").strip()
        if not old_input_str:
            print("已取消")
            input("按 Enter 返回...")
            return

    if not new_input_str:
        # 自動建議新名字
        old_path_tmp = Path(old_input_str)
        suggested = old_path_tmp.stem + "_new" + old_path_tmp.suffix if old_path_tmp.suffix else old_path_tmp.stem + "_new"
        new_input_str = input(f"請輸入新檔名 (預設 {old_path_tmp.stem}_new.py): ").strip()
        if not new_input_str:
            # 如果使用者按 Enter，幫他生成
            new_input_str = str(old_path_tmp.with_stem(old_path_tmp.stem + "_new")) if old_path_tmp.suffix else old_input_str + "_new"
            if not new_input_str.endswith('.py'):
                new_input_str += '.py'
        if not new_input_str:
            print("已取消")
            input("按 Enter 返回...")
            return

    if '--dry-run' not in old_input_str and '--dry-run' not in new_input_str:
        if old_input_str in ('--help', '-h'):
            print(f"用法: {__plugin_usage__}")
            input("按 Enter...")
            return

    # 解析路徑
    old_path = (root / old_input_str) if not Path(old_input_str).is_absolute() else Path(old_input_str)
    if old_path.suffix == '':
        old_path = old_path.with_suffix('.py')
    # 支援直接傳 dotted module
    if not old_path.exists() and '.' not in str(old_path) or old_path.exists() is False:
        # 嘗試在專案中搜尋
        candidates = list(root.rglob(old_path.name))
        if candidates:
            old_path = candidates[0]
            print(f"自動找到: {old_path.relative_to(root)}")

    new_path = (root / new_input_str) if not Path(new_input_str).is_absolute() else Path(new_input_str)
    if new_path.suffix == '':
        new_path = new_path.with_suffix('.py')

    if not old_path.exists():
        print(f"❌ 找不到舊檔案: {old_path}")
        input("按 Enter 返回...")
        return

    old_name = old_path.stem
    new_name = new_path.stem

    try:
        old_rel = old_path.relative_to(root)
        old_dotted = ".".join(old_rel.with_suffix('').parts)
    except:
        old_dotted = old_name

    try:
        new_rel = new_path.relative_to(root)
        new_dotted = ".".join(new_rel.with_suffix('').parts)
    except:
        new_dotted = new_name

    variants = {old_name, old_dotted}
    if '.' in old_dotted:
        parts = old_dotted.split('.')
        if len(parts) > 1:
            variants.add(".".join(parts[-2:]))

    print(f"\n重命名: {old_path.relative_to(root)} ({old_dotted}) -> {new_path.relative_to(root)} ({new_dotted})")
    print(f"將替換變體: {variants}")

    # 收集修改
    to_change = []
    for py_file in find_py_files(root):
        if py_file.resolve() == old_path.resolve():
            continue
        try:
            text = py_file.read_text(encoding='utf-8', errors='ignore')
        except:
            continue
        if old_name not in text:
            continue

        new_text = text
        # 精確替換 import
        for old_variant in sorted(variants, key=len, reverse=True):
            if old_variant == old_dotted:
                new_variant = new_dotted
            elif old_variant == old_name:
                new_variant = new_name
            else:
                new_variant = old_variant.replace(old_name, new_name)

            new_text = re.sub(rf'\bfrom\s+{re.escape(old_variant)}\b', f'from {new_variant}', new_text)
            new_text = re.sub(rf'\bimport\s+{re.escape(old_variant)}\b', f'import {new_variant}', new_text)

        new_text = re.sub(rf'(\bfrom\s+\.+){re.escape(old_name)}\b', rf'\g<1>{new_name}', new_text)
        # from . import old
        # 這裡用函數避免誤替換
        def repl_from_import(m):
            full = m.group(0)
            return full.replace(old_name, new_name)
        new_text = re.sub(rf'\bfrom\s+\.+.*import[^\n]*\b{re.escape(old_name)}\b', repl_from_import, new_text)

        # 替換 old.xxx 用法，如果有 import
        if re.search(rf'^\s*(?:from\s+.*\s+)?import\s+.*\b{re.escape(old_name)}\b', text, re.MULTILINE) or \
           re.search(rf'^\s*from\s+{re.escape(old_name)}\b', text, re.MULTILINE):
            new_text = re.sub(rf'\b{re.escape(old_name)}\s*\.', f'{new_name}.', new_text)

        if new_text != text:
            to_change.append((py_file, text, new_text))

    print(f"\n將修改 {len(to_change)} 個檔案:")
    for f, _, _ in to_change[:20]:
        print(f"  - {f.relative_to(root)}")
    if len(to_change) > 20:
        print(f"  ... 還有 {len(to_change)-20} 個")

    if dry_run:
        print("\n[預覽模式] 不會寫入")
        for f, old_t, new_t in to_change[:2]:
            print(f"\n--- {f.relative_to(root)} ---")
            for o_line, n_line in zip(old_t.splitlines(), new_t.splitlines()):
                if o_line != n_line:
                    print(f"- {o_line}\n+ {n_line}")
        input("\n預覽結束，按 Enter 返回...")
        return

    confirm = input("\n確定執行? [y/N]: ").lower()
    if confirm not in ('y', 'yes'):
        print("已取消")
        input("按 Enter...")
        return

    # 執行改名
    new_path.parent.mkdir(parents=True, exist_ok=True)
    is_git = False
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        is_git = True
    except:
        pass

    if is_git:
        try:
            subprocess.run(["git", "mv", str(old_path.relative_to(root)), str(new_path.relative_to(root))], cwd=root, check=True)
            print(f"[git mv] {old_path.name} -> {new_path.name}")
        except:
            old_path.rename(new_path)
            print(f"[mv] {old_path.name} -> {new_path.name}")
    else:
        old_path.rename(new_path)
        print(f"[mv] {old_path.name} -> {new_path.name}")

    for f, _, new_t in to_change:
        f.write_text(new_t, encoding='utf-8')

    # 清理
    for p in root.rglob("__pycache__"):
        if not is_excluded(p, root):
            shutil.rmtree(p, ignore_errors=True)

    print(f"✅ 完成，共更新 {len(to_change)} 個檔案，已清理 __pycache__")
    file_manager.scan_directory()
    input("按 Enter 返回...")

# 為了讓外掛也能獨立執行
if __name__ == "__main__":
    class DummyFM:
        def __init__(self):
            self.work_path = os.getcwd()
            self.current_path = os.getcwd()
            self.selected_items = set()
            def scan(): pass
            self.scan_directory = scan
    run(DummyFM(), sys.argv[1:])
