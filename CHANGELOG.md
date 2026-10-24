# 📋 更新日志 (Changelog)

> **重要信息备份与迁移工具** — 所有版本更新记录

[![最新版本](https://img.shields.io/badge/最新-v2.1-brightgreen)](https://github.com/yhkj-nb/elaina-backup-manager/releases)
[![许可证](https://img.shields.io/badge/许可证-MIT-green)](LICENSE)
[![框架](https://img.shields.io/badge/框架-ElainaBot%20v2-blue)](https://github.com/ElainaCore/ElainaBot_v2)

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
