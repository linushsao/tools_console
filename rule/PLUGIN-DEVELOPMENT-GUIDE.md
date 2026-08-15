# Archive Tool CLI - 外掛程式撰寫規範
Version: V0.4-060-PluginSystem

## 1. 核心設計理念

主程式 `archive_tool_cli.py` 內建 `PluginManager`，啟動時自動掃描專案根目錄下的 `plugins/` 資料夾。

> **原則：主程式不需修改，只需在 `plugins/` 新增一個 `.py` 檔案即可成為新指令。**

## 2. 目錄與載入規則

```
project_root/
├── archive_tool_cli.py
└── plugins/
    ├── __init__.py         # 必須存在 (可為空)
    ├── py_rename.py        # 範例
    └── my_plugin.py        # 你的外掛
```

載入規則：
1.  檔名必須以 `.py` 結尾，且不以 `_` 開頭
2.  使用 `importlib.util.spec_from_file_location` 動態載入，不需要安裝
3.  載入失敗會在控制台顯示 `[外掛載入失敗]`，不影響主程式
4.  可用 `RELOAD_PLUG` 或 `PLUG` 指令重新掃描

## 3. 外掛必須遵守的介面規範

一個合法的外掛必須包含以下 4 個變數 + 1 個函式。

### 3.1 必要變數

```python
__plugin_name__ = "MyTool"  # 顯示名稱，字串
__plugin_command__ = "MYTOOL" # 觸發指令，必須大寫，建議 2-10 字元，無空格
__plugin_description__ = "這是做什麼的，一行說明"
__plugin_usage__ = "MYTOOL [參數1] [參數2] --dry-run"
```

主程式會讀取這些變數顯示在 `display()` 和 `PLUG` 列表中。

### 3.2 必要函式

```python
def run(file_manager, args):
    """
    外掛入口函式，主程式會呼叫此函式
    :param file_manager: FileManager 實例，提供以下常用屬性與方法
    :param args: List[str] 使用者在指令後的參數，例如輸入 RENAME a.py b.py，則 args = ['a.py', 'b.py']
    """
    pass
```

`file_manager` 提供的上下文 (Context)：
- `file_manager.work_path` : 專案根目錄 (str / Path)
- `file_manager.current_path` : 目前瀏覽的目錄
- `file_manager.selected_items` : set，存放已選取的相對路徑
- `file_manager.ignored_items` : set，目前忽略清單
- `file_manager.scan_directory()` : 重新掃描目前目錄
- `file_manager.save_config()` : 儲存設定

### 3.3 參數處理建議

外掛應自行處理互動邏輯，主程式不介入。

推薦模式：
1.  如果 `args` 足夠，直接執行 (適合自動化)
2.  如果 `args` 不足，使用 `input()` 詢問使用者
3.  支援 `--dry-run` 或 `--help`

## 4. 開發注意事項

1.  **獨立性**：外掛不應 `import` 主程式，只能依賴 `file_manager` 傳入的物件和標準庫
2.  **排除清單**：處理檔案時，務必排除 `EXCLUDE_DIRS = {'.git', '__pycache__', 'venv', '.venv', 'plugins'}`，避免改到自己
3.  **編碼**：所有檔案讀寫請用 `encoding='utf-8', errors='ignore'`
4.  **錯誤處理**：請自行 `try/except`，並用 `input("按 Enter 返回...")` 暫停，讓使用者看得到錯誤
5.  **不要使用 pyperclip 等重依賴**，若必要請 `try: import ... except:`
6.  檔名即外掛 ID，請勿重複

## 5. 外掛生命週期

1.  主程式啟動 -> `PluginManager.scan()` -> 載入所有 `plugins/*.py`
2.  主程式顯示 `🔌 已載入外掛: [RENAME] Py-Rename | [HELLO] Hello Example`
3.  使用者輸入指令 `HELLO arg1 arg2`
4.  主程式先檢查原生指令 (A, ZIP, TREE...)，若無匹配，再檢查 `plugin_manager.plugins` 是否有 `HELLO`
5.  若有，呼叫 `plugin_module.run(file_manager, ['arg1', 'arg2'])`
6.  外掛執行完畢，回到主迴圈

## 6. 範例：最小外掛

見 `plugins/example_hello.py`

## 7. 提交檢查清單

- [ ] 檔案放在 `plugins/` 下
- [ ] 包含 `__plugin_name__`, `__plugin_command__`, `__plugin_description__`, `__plugin_usage__`
- [ ] 包含 `def run(file_manager, args):`
- [ ] 在 `run()` 結尾呼叫 `input("按 Enter...")` 或 `file_manager.scan_directory()`
- [ ] 測試 `PLUG` 能列出你的外掛
- [ ] 測試 `YOUR_CMD --help` 能正常運作
