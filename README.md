# ElainaBot 备份管理插件

> **选择性备份与迁移 Bot 核心数据 — 配置文件 · 插件数据 · 一键导入导出**

[![版本](https://img.shields.io/badge/版本-v1.6-brightgreen)](https://github.com/yhkj-nb/elaina-backup-manager/releases)
[![许可证](https://img.shields.io/badge/许可证-MIT-green)](LICENSE)
[![ElainaBot](https://img.shields.io/badge/框架-ElainaBot%20v2-blue)](https://github.com/ElainaCore/ElainaBot_v2)
[![Python](https://img.shields.io/badge/Python-3.11+-purple)](https://python.org)
[![QQ群](https://img.shields.io/badge/QQ交流群-点击链接查看所有群-blue)](https://api.yhkj.ddns-ip.net/qun.php)

---

## 📑 目录

- [功能特性](#-功能特性)
- [安装部署](#-安装部署)
- [使用说明](#-使用说明)
- [云盘备份](#-云盘备份)
- [备份范围](#-备份范围)
- [项目结构](#-项目结构)
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
| ☁️ **云盘备份** | 支持上传到 WebDAV / S3 兼容 / FTP 三大类云盘 |
| 🎨 **现代化 UI** | 浅色主题面板，侧边栏导航，响应式布局 |
| 📊 **仪表盘** | 实时展示备份统计、存储空间、最近备份记录 |
| 🔓 **免验证访问** | 所有 API 路由 `auth=False`，无需登录即可调用 |
| 🛡️ **安全校验** | 路径穿越防护、ZIP 完整性检测、文件名白名单过滤 |
| ⚡ **热重载支持** | 插件更新即时生效，无需重启框架 |
| 🧩 **模块化结构** | main.py 拆分到 app/ 目录，按职责划分模块 |

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

本插件主要使用 Python 标准库 + 框架自带库，**无需额外安装第三方依赖**：

```
json, zipfile, yaml, pathlib, datetime, os, urllib.parse, hashlib, hmac, ftplib
aiohttp (Web 服务 + WebDAV / S3 客户端, 框架自带)
core.plugin.*, core.base.logger (框架自带)
```

> 云盘备份功能基于 `aiohttp` 实现 WebDAV / S3 兼容协议, 基于 `ftplib` 实现 FTP, 均不引入额外依赖。

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
   - **☁️ 上传到云盘**：把该备份推送到已配置的云盘
   - **⬇️ 下载**：导出备份文件到本地
   - **🗑️ 删除**：移除指定备份（不可恢复）
4. 已上传到云盘的备份会显示紫色 ☁ 徽标

### 5. 云盘备份

进入「云盘备份」页面，可添加 / 编辑 / 测试 / 删除多个云盘配置，所有配置统一保存在插件 `data/config.yaml` 的 `providers` 字段下（首次加载自动生成）。

1. 点击「添加云盘」，选择云盘类型
2. 填写名称与凭据（详见下方各云盘示例）
3. 点击「测试连接」验证凭据
4. 保存后即可在「备份历史」中点击 ☁️ 上传该备份
5. 进入「云盘文件」页面可浏览、下载、删除云盘上的备份文件

---

## ☁️ 云盘备份

本插件通过三类协议覆盖市面上绝大多数常见网盘 / 对象存储 / NAS：

### 协议与对应服务

| 协议 | 适用云盘 / 服务 | 凭据要点 |
|------|----------------|----------|
| **WebDAV** | 坚果云 / NextCloud / ownCloud / Koofr / Box / 群晖 Drive | URL + 账号 + 密码 (坚果云请用应用密码) |
| **S3 兼容** | AWS S3 / Cloudflare R2 / Backblaze B2 / MinIO / 阿里云 OSS / 腾讯云 COS | Endpoint + Region + Bucket + Access Key + Secret Key |
| **FTP / FTPS** | NAS / 虚拟主机 / 传统 FTP 服务器 | 主机 + 端口 + 用户名 + 密码 (+ TLS) |

### 各云盘配置示例

#### 坚果云 (WebDAV)

| 字段 | 值 |
|------|------|
| 类型 | `webdav` |
| 名称 | `我的坚果云` |
| URL | `https://dav.jianguoyun.com/dav/` |
| 账号 | 你的坚果云登录邮箱 |
| 密码 | **应用密码** (坚果云 → 安全选项 → 添加应用, 不要用登录密码) |

#### Cloudflare R2 (S3 兼容)

| 字段 | 值 |
|------|------|
| 类型 | `s3` |
| Endpoint | `https://<account_id>.r2.cloudflarestorage.com` |
| Region | `auto` |
| Bucket | 你的 R2 bucket 名 |
| Access Key | R2 → Manage R2 API Tokens → 创建的 Access Key ID |
| Secret Key | 对应的 Secret Access Key |
| Path-Style | ✅ 开启 (R2 必须开启) |

#### Backblaze B2 (S3 兼容)

| 字段 | 值 |
|------|------|
| 类型 | `s3` |
| Endpoint | `https://s3.<region>.backblazeb2.com` |
| Region | 同 endpoint 中的 region |
| Bucket | B2 bucket 名 |
| Access Key | B2 → App Keys → keyID |
| Secret Key | 对应的 applicationKey |
| Path-Style | ✅ 开启 |

#### MinIO (S3 兼容, 自建)

| 字段 | 值 |
|------|------|
| 类型 | `s3` |
| Endpoint | `http(s)://your-minio:9000` |
| Region | `us-east-1` (任意, 自建固定填) |
| Bucket | 已创建的 bucket |
| Access Key / Secret Key | MinIO 启动时设置的 root 凭据或用户凭据 |
| Path-Style | ✅ 必须开启 |

#### 阿里云 OSS (S3 兼容)

| 字段 | 值 |
|------|------|
| 类型 | `s3` |
| Endpoint | `https://oss-<region>.aliyuncs.com` |
| Region | `oss-cn-hangzhou` 等 |
| Service | `oss` (重要: 不是 s3) |
| Bucket | OSS bucket 名 |
| Access Key / Secret Key | RAM 用户 AccessKey |
| Path-Style | ✅ 开启 |

#### 腾讯云 COS (S3 兼容)

| 字段 | 值 |
|------|------|
| 类型 | `s3` |
| Endpoint | `https://cos.<region>.myqcloud.com` |
| Region | `ap-guangzhou` 等 |
| Service | `cos` (重要: 不是 s3) |
| Bucket | 形如 `name-1234567890` |
| Access Key / Secret Key | CAM 用户的 SecretId / SecretKey |
| Path-Style | ✅ 开启 |

#### NAS / 虚拟主机 (FTP)

| 字段 | 值 |
|------|------|
| 类型 | `ftp` |
| 主机 | `nas.example.com` 或内网 IP |
| 端口 | `21` (FTPS 一般也是 21, 显式 TLS) |
| 用户名 / 密码 | FTP 账号 |
| 启用 FTPS (TLS) | 视服务端开启情况勾选 |

### 配置文件位置

所有配置（备份路径 + 云盘 provider）统一保存在插件 `data/config.yaml`，由框架 `ctx.ensure_config()` 在首次加载时自动生成：

```yaml
providers:
  nutstore_xxxxx:
    type: webdav
    name: 我的坚果云
    url: https://dav.jianguoyun.com/dav/
    username: me@example.com
    password: app_password_here
    remote_path: backups/
    timeout: 60
    updated_at: '2026-08-24T10:00:00'
  r2_xxxxx:
    type: s3
    name: 我的 R2
    endpoint: https://<id>.r2.cloudflarestorage.com
    region: auto
    bucket: my-backups
    access_key: AKxxx
    secret_key: SKxxx
    service: s3
    path_style: true
    remote_path: ''
last_used: nutstore_xxxxx
```

> 凭据以明文存储在本机配置文件中, 请确保服务器访问权限受控。面板返回给前端时会自动脱敏。

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

### 自定义备份范围

备份逻辑固定打包 `config/` 与 `data/` 目录, 排除「备份工具」自身目录下的文件。如需修改备份源, 编辑 `app/backup.py` 中 `create_backup()` 函数的 glob 规则。

**自定义备份存储路径**: 编辑插件 `data/config.yaml` 中的 `backup_dir` 字段：

```yaml
# 留空 (默认) -> 直接放在框架自动创建的 data/ 目录下
backup_dir: ''
# 或指定绝对路径 -> 备份文件保存到该目录
backup_dir: /www/backups
```

修改后下次备份即生效，无需重启框架。目录不存在时会自动创建。

---

## 🗂️ 项目结构

自 v1.6 起, 单文件 `main.py` 拆分为模块化 `app/` 目录:

```
备份工具/
├── main.py                # 入口 (仅触发 app 包导入, 完成路由与生命周期注册)
├── app/
│   ├── __init__.py        # 包入口, 导出公开 API
│   ├── constants.py       # 路径常量、插件元数据
│   ├── utils.py           # format_size / 文件扫描 / 磁盘使用
│   ├── backup.py          # 本地备份创建 (ZIP 打包)
│   ├── restore.py         # 备份恢复、备份信息解析
│   ├── backup_list.py     # 本地备份列表、删除
│   ├── cloud.py           # 云盘备份 (WebDAV / S3 / FTP)
│   ├── routes.py          # 所有 Web 路由 (含云盘路由)
│   ├── lifecycle.py       # on_load / on_unload
│   └── panel.html         # Web 面板
├── data/                  # 框架加载时自动生成 (运行数据目录)
│   ├── config.yaml            # 统一配置: 备份路径 + 云盘 provider (首次加载自动生成)
│   ├── cloud_sync_state.json  # 云盘同步状态记录
│   └── *.zip                  # 备份 ZIP 文件 (默认直接放 data/ 下, 可由 config.yaml 改路径)
├── README.md
└── LICENSE
```

加载流程: 框架加载 `main.py` → 触发 `import app` → `app/__init__.py` 顺序导入各子模块 → `routes.py` 中的 `@register_route` 装饰器注册路由, `lifecycle.py` 中的 `@on_load` / `@on_unload` 装饰器注册生命周期钩子, `on_load` 时通过 `ctx.ensure_config()` 自动生成默认配置文件。

---

## 🔌 API 参考

所有 API 路径前缀：`/api/ext/backup_manager`

### 页面

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `` (前缀根) | ❌ | 打开 Web 面板 |

### 本地备份

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/stats` | ❌ | 获取备份统计 + 磁盘使用 |
| `GET` | `/disk_usage` | ❌ | 仅获取磁盘使用 |
| `GET` | `/backups` | ❌ | 获取备份列表 |
| `POST` | `/backup` | ❌ | 创建新备份 (body: `{include_config, include_data}`) |
| `POST` | `/upload` | ❌ | 上传备份文件 (multipart, 返回解析信息) |
| `POST` | `/restore` | ❌ | 恢复上传的备份 (multipart) |
| `GET` | `/download?fn=<name>` | ❌ | 下载备份文件 |
| `DELETE` | `/delete?fn=<name>` | ❌ | 删除备份文件 |

### 云盘备份

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/cloud/schema` | ❌ | 获取云盘类型表单 schema |
| `GET` | `/cloud/list` | ❌ | 列出所有云盘配置 (脱敏) |
| `GET` | `/cloud/get?pid=<id>` | ❌ | 获取单个云盘配置 (脱敏) |
| `POST` | `/cloud/save` | ❌ | 新增或更新云盘配置 (body 含可选 `id`) |
| `DELETE` | `/cloud/delete?pid=<id>` | ❌ | 删除云盘配置 |
| `POST` | `/cloud/test` | ❌ | 测试连接 (body: `{pid}` 或临时配置) |
| `GET` | `/cloud/files?pid=<id>&path=<path>` | ❌ | 列出云盘备份文件 |
| `POST` | `/cloud/upload` | ❌ | 上传本地备份到云盘 (body: `{pid, filename}`) |
| `GET` | `/cloud/download?pid=<id>&path=<path>` | ❌ | 从云盘下载备份到本地 |
| `DELETE` | `/cloud/delete_file?pid=<id>&path=<path>` | ❌ | 删除云盘上的备份 |
| `GET` | `/cloud/sync_state` | ❌ | 获取本地↔云盘同步状态 |

### 请求示例

```bash
# 获取备份列表
curl http://localhost:5200/api/ext/backup_manager/backups

# 创建备份
curl -X POST http://localhost:5200/api/ext/backup_manager/backup \
  -H 'Content-Type: application/json' \
  -d '{"include_config": true, "include_data": true}'

# 下载备份
curl -o backup.zip "http://localhost:5200/api/ext/backup_manager/download?fn=backup_20250415_120000.zip"

# 列出云盘配置
curl http://localhost:5200/api/ext/backup_manager/cloud/list

# 上传备份到云盘
curl -X POST http://localhost:5200/api/ext/backup_manager/cloud/upload \
  -H 'Content-Type: application/json' \
  -d '{"pid": "nutstore_xxx", "filename": "backup_20250415_120000.zip"}'

# 测试云盘连接
curl -X POST http://localhost:5200/api/ext/backup_manager/cloud/test \
  -H 'Content-Type: application/json' \
  -d '{"pid": "nutstore_xxx"}'
```

### 响应格式

统一返回 JSON, 字段以 `success` 布尔值标记结果:

```json
{
  "success": true,
  "filename": "backup_20250415_120000.zip"
}
```

失败时返回:

```json
{
  "success": false,
  "error": "错误描述"
}
```

---

## 📋 更新日志

### v1.6 (2026-08)

#### ✨ 新增功能
- **云盘备份**: 把本地备份一键上传到云盘, 支持三类常见协议
  - **WebDAV**: 坚果云 / NextCloud / ownCloud / Koofr / Box / 群晖 Drive
  - **S3 兼容**: AWS S3 / Cloudflare R2 / Backblaze B2 / MinIO / 阿里云 OSS / 腾讯云 COS
  - **FTP / FTPS**: NAS / 虚拟主机 / 传统 FTP 服务器
- 云盘配置管理面板: 添加 / 编辑 / 删除 / 测试连接, 凭据自动脱敏
- 云盘文件浏览器: 列出 / 下载 / 删除云盘上的备份
- 备份历史新增「上传到云盘」按钮, 已上传的备份显示紫色 ☁ 徽标
- 同步状态记录 (`data/cloud_sync_state.json`), 跨重启保留

#### 🔧 框架规范化 (遵循 ElainaBot v2 插件开发文档)
- **路径解析**: 完全使用框架注入的 `ctx.plugin_dir` / `ctx.data_dir`, 移除所有 `sys.path` hack
- **配置自动生成**: `on_load` 时调用 `ctx.ensure_config()` 自动生成
  - `data/config.yaml` (统一配置: `backup_dir` / `include_config` / `include_data` / `max_upload_mb` / `providers` / `last_used`)
- **可配置备份路径**: 在 `data/config.yaml` 中修改 `backup_dir` 即可改备份 ZIP 输出位置; 留空则直接放在框架自动创建的 `data/` 目录下
- **资源文件路径**: Web 面板 HTML 通过 `ctx.get_resource_path('app/panel.html')` 定位
- **Web 面板注册**: `register_page` 使用 `html_file=` 参数, 由框架读取并托管
- **日志**: 通过 `_LogProxy` 懒代理 `ctx.log` (文档 §9); ctx 不可用时 fallback 到标准 `logging`

#### 🧩 模块化重构
- 单文件 `main.py` 拆分为 `app/` 目录下 9 个模块:
  - `constants.py` / `utils.py` / `backup.py` / `restore.py` / `backup_list.py`
  - `cloud.py` (新增云盘实现) / `routes.py` / `lifecycle.py` / `panel.html`
- `main.py` 仅保留入口逻辑, 通过 `importlib` 顺序加载 `app/` 下公开子模块
- WebDAV 客户端基于 `aiohttp` 实现 (PROPFIND / PUT / DELETE / MKCOL)
- S3 客户端基于 `aiohttp` 手动实现 AWS Signature V4 签名 (无需 boto3)
- FTP 客户端基于标准库 `ftplib`, 同步调用通过线程池异步化
- 敏感字段 (`password` / `secret_key` / `access_key` / `token`) 在 API 返回时自动脱敏

#### 📚 文档
- README 新增「云盘备份」「项目结构」章节, 列出各云盘配置示例
- API 参考表与实际路由对齐, 补充云盘相关接口

---

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

默认直接存储在框架自动创建的 `data/` 目录下，可在 `data/config.yaml` 的 `backup_dir` 字段中自定义绝对路径。框架加载插件时自动创建 `data/` 目录与 `config.yaml` 配置骨架。

### Q2: 如何恢复备份？

1. 进入「导入备份」页面
2. 选择之前导出的 ZIP 文件
3. 确认恢复范围
4. 点击「开始恢复」

### Q3: 备份失败怎么办？

- 检查磁盘空间是否充足
- 查看面板控制台错误日志
- 确认 `data/` 目录 (或 `backup_dir` 自定义路径) 有写入权限

### Q4: 可以自定义备份哪些目录吗？

可以，编辑 `app/backup.py` 中 `create_backup()` 函数的 glob 规则；备份输出路径在 `data/config.yaml` 的 `backup_dir` 字段修改。

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
