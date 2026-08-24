# plugins/备份工具/app/__init__.py
"""
备份工具应用包 - v1.6

模块化拆分:
- constants: 路径常量与插件元数据
- utils: 通用工具函数
- backup: 本地备份创建
- restore: 备份恢复
- backup_list: 本地备份列表管理
- cloud: 云盘备份(WebDAV / S3 兼容 / FTP)
- routes: Web 路由
- lifecycle: 插件生命周期
"""

from .constants import (
    PLUGIN_DIR, PROJECT_ROOT, CONFIG_DIR, DATA_DIR,
    CLOUD_CONFIG_PATH, __plugin_meta__,
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
    'CLOUD_CONFIG_PATH', '__plugin_meta__',
    'log', 'format_size',
    'create_backup',
    'restore_backup', 'parse_backup_info',
    'get_backups_list', 'delete_backup_file',
    'cloud', 'routes', 'lifecycle',
]
