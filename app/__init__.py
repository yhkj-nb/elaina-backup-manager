# plugins/备份工具/app/__init__.py
"""
备份工具应用包 - v2.7

模块化拆分:
- constants: 路径常量与插件元数据
- utils: 通用工具函数
- scan_utils: 扫描通用工具 (遍历剪枝 + 排除规则, 插件/模块共用)
- backup: 本地备份创建 (统一条目模型, 数据文件 / 配置文件可分别开关)
- restore: 备份恢复
- backup_list: 本地备份列表管理
- cloud: 云盘备份(WebDAV / S3 兼容 / FTP)
- routes: Web 路由
- lifecycle: 插件生命周期
- plugins_scan: 插件 data/ 与源码/配置 (除 data/ 外全部文件) 扫描 (v2.2 / v2.4 / v2.7)
- modules_scan: 框架模块 data/ 与源码/配置、modules_enabled.json 扫描 (v2.3 / v2.4 / v2.7)

注: v2.7 起不再提供聊天指令 (app/commands.py 已移除), 功能全部走 Web 面板;
    备份范围含备份工具自身 (源码 + data 配置, 跳过其生成的备份包)。
"""

from .constants import (
    PLUGIN_DIR, PROJECT_ROOT, CONFIG_DIR, DATA_DIR,
    __plugin_meta__,
    get_backup_dir,
    DEFAULT_CONFIG, CONFIG_COMMENTS,
)
from .utils import log, format_size
from .backup import create_backup
from .restore import restore_backup, parse_backup_info
from .backup_list import get_backups_list, delete_backup_file
from . import cloud
from . import routes  # noqa: F401  (注册路由)
from . import lifecycle  # noqa: F401  (注册生命周期)

__all__ = [
    'PLUGIN_DIR', 'PROJECT_ROOT', 'CONFIG_DIR', 'DATA_DIR',
    '__plugin_meta__',
    'get_backup_dir',
    'DEFAULT_CONFIG', 'CONFIG_COMMENTS',
    'log', 'format_size',
    'create_backup',
    'restore_backup', 'parse_backup_info',
    'get_backups_list', 'delete_backup_file',
    'cloud', 'routes', 'lifecycle',
]
