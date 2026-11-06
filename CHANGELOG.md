# 📋 更新日志 (Changelog)

> **重要信息备份与迁移工具** — 所有版本更新记录

[![最新版本](https://img.shields.io/badge/最新-v2.8-brightgreen)](https://github.com/yhkj-nb/elaina-backup-manager/releases)
[![许可证](https://img.shields.io/badge/许可证-MIT-green)](LICENSE)
[![框架](https://img.shields.io/badge/框架-ElainaBot%20v2-blue)](https://github.com/ElainaCore/ElainaBot_v2)

---

## v2.8 (2026-11-06)

> **分片上传重做** —— 修复「导入备份时上传大文件失败」的根本问题，绕开框架请求体上限，并修复恢复流程一处隐藏 bug。

### 🐛 修复的问题
- **上传大备份包失败 / 报「文件过大」/ 413**：ElainaBot v2 框架的 aiohttp `Application` 使用 `client_max_size=20MB` 限制**整个请求体**，而旧版一次性 POST 整个 ZIP。备份包含全部插件源码 + 运行数据，很容易超过 20MB，被 aiohttp 在解析阶段直接 413 拒绝，根本进不到上传路由
- **恢复流程 `/restore` 双重 multipart bug**：旧版连续调用了两次 `await request.multipart()`（同一请求体只能消费一次），导致 `temp_path` 永远读不到，恢复逻辑走偏；恢复时还会把整个 ZIP 再 POST 一次，同样会撞 20MB 上限
- **上传临时文件堆积**：`temp/upload_*.zip` / 分片从不清理，长期占用磁盘
- **`max_upload_mb` 配置形同虚设**：前后端各自硬编码 500MB，配置项从未被读取
- **前端进度条是假的**：`fetch` 无法报进度，旧版写死 30%→100%

### ✨ 新增 / 改进
- **分片上传**：前端按 `chunk_size_mb`（默认 4MB，远小于框架上限）切片，逐个上传，服务端按序落盘后流式合并；彻底绕开框架 `client_max_size`，插件不依赖框架配置即可分发
- **真实进度**：按已上传分片显示百分比与「第 N / 共 M 片」，支持「取消上传」
- **单片 413 自动减半重试**：若目标框架 `client_max_size` 更小，前端自动把单片减半重新初始化会话，最小可降到 64KB
- **断点续传**：`init` 返回已接收分片，重复分片自动跳过；单片失败自动重试 3 次
- **完整性校验**：合并后核对总大小 + `ZipFile.testzip()` CRC 校验，损坏 / 非 ZIP 直接拒绝
- **安全加固**：`upload_id` 服务端生成 32 位 hex 并严格校验；文件名 basename 化 + 白名单；恢复用 `temp_path` 必须 resolve 到 temp 目录内（防任意文件恢复 / 路径穿越）
- **自动清理**：合并成功即删分片会话；`init` 时清理超过 6 小时的孤儿会话与残留临时 ZIP
- **配置生效**：`max_upload_mb` / `chunk_size_mb` 从 `config.yaml` 读取并前后端共用（新增 `GET /upload/config`）
- **恢复优化**：分片上传完成后服务端已保存完整 ZIP，恢复只传 `temp_path`（短字符串），不再重传整个文件

### 🔌 新增 API
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/upload/config` | 获取上传配置（总上限 / 单片大小） |
| `POST` | `/upload/init` | 初始化分片上传会话，返回 `upload_id` / 分片参数 |
| `POST` | `/upload/chunk` | 上传单个分片 |
| `POST` | `/upload/complete` | 合并 + 校验 + 解析，返回 `temp_path` / 备份信息 |
| `POST` | `/upload/abort` | 取消上传，清理会话 |

> 旧 `POST /upload`（一次性上传）保留兼容，用于小文件 / 第三方脚本，上限改为读取配置。

### 🧩 结构
- 新增 `app/chunk_upload.py`：分片会话管理（纯逻辑，可离线单测）
- `constants.py` 新增 `get_upload_limits()`；`routes.py` 新增 5 个路由并重写上传 / 恢复

---

## v2.7 (2026-11-02)

> 备份范围扩展 + 只保留 Web 面板：插件 / 模块的「配置文件与静态资源」一起打包，「数据文件」与「配置文件」可分别开关，备份工具自身也纳入备份。

### 🛠 备份工具自身
- 备份范围新增 `plugins/备份工具`：源码 (`main.py`、`app/*.py`、`app/panel.html`、文档) 与 `data/config.yaml` 等配置一起打包，迁移后不必再单独配置插件
- `plugins_scan.py` 新增 `_data_exclude_dir()` / `_is_self_artifact()`：备份输出目录默认就是插件自身 `data/`，因此改为按文件名跳过 `*.zip` / `*.part` 备份产物，防止历史备份（最大 275 MB）被递归打包
- `scan_utils.iter_payload_files()` 新增 `skip_files` 参数，支持文件级个案过滤（不改变其它插件 / 模块的排除规则）
- 恢复端仍跳过 `plugins/备份工具/...`，避免旧备份覆盖正在运行的插件代码与云盘凭据
- 包内 `README.md` 与项目 `README.md` 的「不含备份工具自身」说明同步更新为「含自身，但跳过其备份包」

### 🗂 配置文件与资源
- `plugins_scan.py` / `modules_scan.py` 的源码扫描不再只收 `*.py`，改为收集插件 / 模块目录下**除 `data/` 以外的全部文件**：`app/panel.html`、`manifest.json`、`requirements.txt`、`README.md` 等不再遗漏
- 运行数据仍单独收集 `plugins/<名>/data/**`、`modules/<名>/data/**`（含插件 `data/config.yaml` 等自带配置文件）以及 `modules/modules_enabled.json`
- 排除规则不变：`__pycache__` / `.git` / 虚拟环境 / 缓存目录，`.pyc` / 日志 / 临时文件 / 隐藏文件，以及自定义备份输出目录
- 面板、`README.md`（备份包内）与统计文案统一由「插件源码 / 模块源码」改为「源码/配置」，数量口径改为文件数（不再写「个 .py」）

### ⚙️ 备份内容可选
- 面板「新建备份」页顶部新增两个可点选标签：**数据文件**（`plugins/*/data/**`、`modules/*/data/**`）与 **配置文件**（插件 / 模块除 `data/` 外的全部文件：`*.py`、`panel.html`、`json/yaml`、资源等），默认都开启，点击切换
- 标签内实时显示「已选插件 / 模块」范围内的文件数与体积；两者都关闭时前端提示、后端也拒绝（`请至少勾选「数据文件」或「配置文件」`）
- `create_backup()` 参数简化为 `plugins` / `modules` / `include_data_files` / `include_config_files`（框架 `config/` 与项目根 `data/` 仍默认不打包）
- `POST /api/ext/backup_manager/backup` 支持 `{"plugins": [...], "modules": [...], "data": true, "config": false}`，响应额外返回实际生效的 `scope`
- 概览页与新建备份页的说明文案同步为「数据文件 / 配置文件可分别开关」

### 🧹 移除聊天指令
- 删除 `app/commands.py`：`备份` / `备份状态` / `备份列表` / `备份帮助` 指令不再注册，全部功能收归 Web 面板（插件加载后 handler 数为 0）
- `main.py` / `app/__init__.py` 文档同步标注「v2.7 起不再提供聊天指令」

### 📦 版本
- 备份版本号 `2.6 → 2.7`，插件版本 `2.6.0 → 2.7.0`

---

## v2.6 (2026-10-31)

> 面板新增「自定义选择」：可选择只备份哪些插件 / 模块（数据 + 源码仍一起打包）。

### 🎯 自定义选择范围
- 面板「新建备份」页的插件 / 模块列表由只读展示改为可点选标签：点击切换选中，配 `全选` / `清空` 按钮，标题栏实时显示「已选 x/y 个 · 数据 n 文件 / 源码 m 个 .py / 体积」
- 首次进入默认全选；刷新统计时保留已有勾选，并自动剔除已不存在的插件 / 模块
- 一个都不选时前端提示、后端也拒绝（`请至少选择一个插件或模块`），避免生成空备份
- `POST /api/ext/backup_manager/backup` 支持请求体 `{"plugins": [...], "modules": [...]}`：字段缺省或为 `null` 表示全选，空数组表示该分类不备份；非数组 / 非字符串参数返回明确错误
- 数据 + 源码仍然固定一起打包，面板只提供「选择哪些插件 / 模块」这一项，不再出现其它勾选项

### 🎨 界面
- 新增 `.pick-chip` 选择标签样式（沿用框架设计令牌与 `--accent-soft` 高亮），选中状态以实心圆点 + 边框高亮提示
- 概览页范围说明同步为「起始全选 · 新建备份时可自定义选择」

---

## v2.5 (2026-10-31)

> 备份范围收敛为「插件 + 模块 的数据与源码」，界面按框架样式重构，作为后续可选范围的基础。

## v2.4 (2026-10-31)

> 插件 / 模块的源码 (`.py`) 纳入备份，并重构 `backup.py` 为统一条目模型。

### 🧬 插件与模块源码
- `plugins_scan.py` / `modules_scan.py` 新增源码扫描：`plugins/<名>/**/*.py`、`modules/<名>/**/*.py` 以相同前缀写入 ZIP
- 源码扫描自动跳过 `data/` 子树（运行数据可能数百 MB）、`__pycache__`、日志与自定义备份输出目录
- 备份开关拆分为「插件数据 / 插件源码 / 模块数据 / 模块源码」，源码默认开启，可单独关闭以只迁移数据
- `backup_info.json` 新增 `include_plugin_src` / `plugin_src_count` / `plugin_src_file_count` / `plugin_src_size` / `plugin_src` 与对应 `module_src_*` 字段，README 同步说明
- 恢复时源码文件单独计入 `restored_plugin_src` / `restored_module_src`，日志与面板可区分"数据"与"覆盖代码"

### 🧩 模块数据（补齐 2.3 内容）
- 备份 `modules/<名>/data` 与 `modules/modules_enabled.json`，支持按模块勾选

### ⚡ backup.py 重构与优化
- 所有内容统一为 `(源文件, ZIP 内路径)` 条目：一次扫描同时供元数据、README 与 ZIP 写入，不再重复扫盘
- 合并 `_plugin_stats` / `_module_stats` 为通用 `_group_stats`，合并体积统计为 `_entries_size`
- 新增 `scan_utils.py` 收敛插件 / 模块重复的排除规则，`os.walk` 遍历阶段直接剪枝（不进入缓存目录与备份输出目录）
- 写入前按 ZIP 内路径去重并排序；单个文件写入失败只跳过该文件，不再中断整次备份
- 统计接口支持复用同一份 inventory，面板统计只扫盘一次

---

## v2.2 (2026-10-31)

> 补齐插件级备份：插件运行数据可扫描、可勾选、可恢复，并新增主人聊天命令入口。

### 🧩 插件数据备份
- 新增 `app/plugins_scan.py`：扫描 `plugins/*/data` 下的插件运行数据，生成 `plugins/<插件名>/data/...` 形式的 ZIP 条目
- 备份元数据 `backup_info.json` 新增 `include_plugins` / `plugin_count` / `plugin_file_count` / `plugin_size` / `plugins` 明细，`README.md` 内同步标注每个插件的文件数与体积
- 安全排除：备份工具自身（含云盘凭据与历史备份）、`__pycache__`、`.git`、`node_modules`、`venv`、缓存/临时/日志/隐藏文件，以及自定义备份输出目录
- 不备份插件源码，只迁移运行数据，避免恢复时覆盖运行中的代码

### 🔄 恢复与面板
- `app/restore.py` 支持 `plugins/` 前缀安全恢复映射，写入前校验解析后路径必须位于 `plugins/` 内，并拒绝恢复备份工具自身
- 新建备份页新增「插件数据」开关与插件勾选列表（全选 / 全不选）、汇总统计；历史列表与导入预览展示插件数量
- 恢复成功提示补充插件文件数量

### 🤖 聊天命令（主人专用）
- 新增 `app/commands.py`：`备份` 创建全量备份，`备份状态` / `备份列表` / `备份帮助` 查看统计与历史

---

## v2.1 (2026-10-24)

> 代号「暗夜」—— Web 面板正式支持深色模式，并对备份核心逻辑做了稳定性与性能优化。

### 🌙 新增功能
- **深色 / 浅色主题**: Web 面板新增完整的深色模式支持
  - 页头新增「深色 / 浅色」一键切换按钮
  - 主题偏好通过 `localStorage` 持久化，下次访问自动记忆
  - 首次访问自动跟随系统 `prefers-color-scheme` 设定（深色 / 浅色自适应）
  - 引入 `[data-theme="dark"]` 变量体系，覆盖背景、文字、边框、强调色、阴影及表格行 / 滚动条等组件
  - 首屏绘制前内联应用主题，**无闪烁 (FOUC)**
- 备份归档 `backup_info.json` 内的「备份工具版本」同步升级为 `v2.1`

### ⚡ 备份逻辑优化 (`app/backup.py`)
- **时间戳一致性**: `datetime.now()` 仅取一次，备份文件名、`backup_info.json`、`README.md` 三处时间同源，消除多文件各自取时可能错位的隐患
- **去重扫描**: 文件清单只扫描一遍，同时供「元数据生成」与「写入 ZIP」复用，避免重复目录遍历
- **防递归打包**: 数据备份自动排除备份输出目录自身（含 `temp/`），避免把历史备份又打进新备份导致体积无限膨胀
- **版本对齐**: 备份归档内部版本号统一为 `v2.1`，失败清理逻辑更稳健

### 🐛 问题修复 (`app/routes.py`)
- **修复面板 500**: 原 `serve_page` 对 `ctx.get_resource_path()` 的返回值直接调用 `.exists()`，而框架在不同版本返回的是 `str`（非 `Path`），导致面板路由持续返回 `500`、深色主题无法显示。改为以 `routes.py` 同目录的 `panel.html` 可靠定位，并修正 aiohttp 不支持的 `content_type='text/html; charset=...'` 写法（改用 `charset` 参数），面板恢复 `200`

---

## 历史版本

| 版本 | 时间 | 概要 |
|------|------|------|
| **v2.0** | — | 模块化重构，插件结构规范化（详见 [README](README.md)） |
| **v1.6** | 2026-08 | 云盘备份（WebDAV / S3 兼容 / FTP）、配置自动生成、单文件拆分为 `app/` 9 模块 |
| v1.0 ~ v1.5 | — | 早期版本，记录见 [README](README.md) |

> 历史版本的完整说明见仓库 [README](README.md) 的「更新日志」章节。
