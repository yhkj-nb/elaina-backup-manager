# ElainaBot 备份管理插件

> **选择性备份与迁移 Bot 核心数据 — 配置文件 · 插件数据 · 一键导入导出**

[![版本](https://img.shields.io/badge/版本-v1.5-brightgreen)](https://github.com/yhkj-nb/elaina-backup-manager/releases)
[![许可证](https://img.shields.io/badge/许可证-MIT-green)](LICENSE)
[![ElainaBot](https://img.shields.io/badge/框架-ElainaBot%20v2-blue)](https://github.com/ElainaCore/ElainaBot_v2)
[![Python](https://img.shields.io/badge/Python-3.11+-purple)](https://python.org)
[![QQ群](https://img.shields.io/badge/QQ交流群-点击链接查看所有群-blue)](https://api.yhkj.ddns-ip.net/qun.php)

---

## 📑 目录

- [功能特性](#-功能特性)
- [安装部署](#-安装部署)
- [使用说明](#-使用说明)
- [备份范围](#-备份范围)
- [API 参考](#-api-参考)
- [更新日志](#-更新日志)
- [常见问题](#-常见问题)
- [贡献指南](#-贡献指南)
- [许可证](#-许可证)

---

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 📦 **智能备份** | 自动打包 config/ 目录配置文件与所有插件 data/ 数据文件 |
| 🔄 **ZIP 导入/导出** | 标准 ZIP 格式，支持上传备份文件进行恢复 |
| 🎨 **现代化 UI** | 浅色主题面板，侧边栏导航，响应式布局 |
| 📊 **仪表盘** | 实时展示备份统计、存储空间、最近备份记录 |
| 🔓 **免验证访问** | 所有 API 路由 `auth=False`，无需登录即可调用 |
| 🛡️ **安全校验** | 路径穿越防护、ZIP 完整性检测、文件名白名单过滤 |
| ⚡ **热重载支持** | 插件更新即时生效，无需重启框架 |

---

## 📥 安装部署

### 方式一：手动安装

```bash
# 1.在面板点击插件市场→安装备份工具
# 2. 重启 ElainaBot 框架
# 或在 Web 面板 → 插件管理 中启用

# 3. 访问 Web 面板，侧边栏将出现"重要信息备份"入口
```

### 方式二：从 GitHub 安装

```bash
cd /www/wwwroot/QQBOT/plugins
git clone https://github.com/yhkj-nb/elaina-backup-manager.git
mv elaina-backup-manager/plugins/备份工具 .
rm -rf elaina-backup-manager
```

### 依赖说明

本插件使用 Python 标准库，**无需额外安装第三方依赖**：

```
json, zipfile, yaml, pathlib, datetime, uuid, os, urllib.parse
```

---

## 📖 使用说明

### 1. 总览面板

进入插件后默认展示仪表盘页面：

- **统计数据**：备份总数、总大小、最新备份时间
- **快捷操作**：新建备份、导入备份、查看历史
- **存储概况**：备份目录占用空间

### 2. 新建备份

1. 点击侧边栏「新建备份」
2. 选择要包含的目录（默认全选）
3. 点击「开始备份」生成 ZIP 文件
4. 备份文件名格式：`backup_YYYYMMDD_HHMMSS.zip`
5. 备份完成后自动出现在历史记录中

### 3. 导入备份

1. 点击侧边栏「导入备份」
2. 选择本地 ZIP 文件上传
3. 系统校验 ZIP 完整性
4. 预览备份内容清单
5. 确认后解压恢复到对应目录

### 4. 备份历史

1. 点击侧边栏「备份历史」
2. 查看所有已生成的备份记录
3. 支持操作：
   - **下载**：导出备份文件到本地
   - **详情**：查看备份包含的文件列表
   - **删除**：移除指定备份（不可恢复）

---

## 📂 备份范围

### 默认包含的目录

| 目录 | 内容 | 示例文件 |
|------|------|----------|
| `config/` | 框架核心配置 | `bot.yaml`, `settings.yaml` |
| `plugins/*/data/` | 各插件数据 | `*.yaml`, `*.json`, `*.db` |

### 排除的文件

```yaml
excludes:
  - "*.pyc"              # Python 字节码
  - "__pycache__/"       # 缓存目录
  - "*.tmp"              # 临时文件
  - "logs/"              # 日志目录（可选）
```

### 自定义备份

在 `main.py` 的 `BACKUP_CONFIG` 中可自定义备份路径：

```python
BACKUP_CONFIG = {
    'include_dirs': [
        'config/',
        'plugins/*/data/',
    ],
    'exclude_patterns': [
        '*.pyc',
        '__pycache__',
    ],
    'backup_dir': '/www/wwwroot/QQBOT/backups/',  # 备份存储路径
}
```

---

## 🔌 API 参考

所有 API 路径前缀：`/api/ext/backup_manager`

### 通用请求

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/page` | ❌ | 打开 Web 面板 |

### 备份管理

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/api/stats` | ❌ | 获取备份统计信息 |
| `GET` | `/api/list` | ❌ | 获取备份文件列表 |
| `POST` | `/api/create` | ❌ | 创建新备份 |
| `POST` | `/api/import` | ❌ | 上传并导入备份 |
| `GET` | `/api/download?fn=<name>` | ❌ | 下载备份文件 |
| `DELETE` | `/api/delete?fn=<name>` | ❌ | 删除备份文件 |
| `GET` | `/api/detail?fn=<name>` | ❌ | 获取备份文件详情 |

### 请求示例

```bash
# 获取备份列表
curl http://localhost:5200/api/ext/backup_manager/api/list

# 创建备份
curl -X POST http://localhost:5200/api/ext/backup_manager/api/create

# 下载备份
curl -o backup.zip "http://localhost:5200/api/ext/backup_manager/api/download?fn=backup_20250415_120000.zip"

# 删除备份
curl -X DELETE "http://localhost:5200/api/ext/backup_manager/api/delete?fn=backup_20250415_120000.zip"
```

### 响应格式

```json
{
    "code": 200,
    "msg": "success",
    "data": { ... }
}
```

---

## 📋 更新日志

### v1.5 (2026-07)

#### ✨ 新增功能
- 全新浅色主题 Web 面板，侧边栏导航设计
- 仪表盘页面，展示备份统计与快捷操作
- ZIP 备份导入/导出完整流程
- 备份历史管理（查看、下载、删除）
- ZIP 完整性校验（`testzip()`）

#### 🎨 界面优化
- CSS 变量与父面板同步，支持主题切换
- 响应式布局，适配移动端
- 可折叠侧边栏，节省屏幕空间
- 加载动画与操作反馈提示

#### 🔧 技术改进
- 全部路由设置 `auth=False`，免验证访问
- 路径参数改为查询参数（`?fn=`）
- 统一使用 `web.json_response()` 返回
- 文件名安全校验，防止路径穿越
- HTML 文件更名为 `panel.html`

#### 🐛 Bug 修复
- 修复 404 状态码问题
- 修复 JSON 返回格式错误
- 修复文件下载路径拼接问题

---

### v1.0 (初始版本)

- 基础备份功能
- 简单的 Web 面板
- ZIP 压缩/解压

---

## ❓ 常见问题

### Q1: 备份文件在哪里？

默认存储在 `/www/wwwroot/QQBOT/backups/` 目录下，可在 `main.py` 中自定义路径。

### Q2: 如何恢复备份？

1. 进入「导入备份」页面
2. 选择之前导出的 ZIP 文件
3. 确认恢复范围
4. 点击「开始恢复」

### Q3: 备份失败怎么办？

- 检查磁盘空间是否充足
- 查看面板控制台错误日志
- 确认备份目录有写入权限

### Q4: 可以自定义备份哪些目录吗？

可以，编辑 `main.py` 中的 `BACKUP_CONFIG` 配置项。

### Q5: 为什么 API 不需要认证？

按用户需求设置 `auth=False`，如需开启认证，修改 `register_route` 中的 `auth` 参数为 `True`。

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境搭建

```bash
# 1. 克隆仓库
git clone https://github.com/yhkj-nb/elaina-backup-manager.git
cd elaina-backup-manager

# 2. 链接到 ElainaBot
ln -s $(pwd)/plugins/备份工具 /path/to/ElainaBot/plugins/

# 3. 重启框架
python /path/to/ElainaBot/main.py
```

### 提交规范

```
feat: 新增XXX功能
fix: 修复XXX问题
docs: 更新文档
style: 代码格式调整
refactor: 重构代码
test: 添加测试
chore: 构建流程/依赖更新
```

---

## 📜 许可证

本项目采用 [MIT 许可证](LICENSE)。

```
Copyright (c) 2025 yhkj-nb

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 📬 联系方式

| 渠道 | 链接 |
|------|------|
| 📦 GitHub | [yhkj-nb/elaina-backup-manager](https://github.com/yhkj-nb/elaina-backup-manager) |
| 💬 QQ 群 | [点击链接查看全部群](https://api.yhkj.ddns-ip.net/qun.php) |
| 📧 Issue | [GitHub Issues](https://github.com/yhkj-nb/elaina-backup-manager/issues) |

---

**Made with ❤️ by [yhkj-nb](https://github.com/yhkj-nb)**
