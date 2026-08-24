# plugins/备份工具/app/constants.py
"""路径常量与插件元数据

所有路径基于框架注入的插件上下文 (core.plugin.context.ctx):
- ctx.plugin_dir     插件根目录 (本文件所在目录的父目录)
- ctx.data_dir       插件 data/ 目录 (框架加载时自动创建)
- ctx.get_resource_path(filename)  资源文件路径
- ctx.get_data_path(filename)       data/ 下文件路径

配置文件约定:
- data/cloud_backup.yaml   云盘 provider 列表 + 备份路径等运行配置
- data/config.yaml          备份选项默认值 (框架 ensure_config 自动生成)
"""

from pathlib import Path
from typing import Any, Dict

# ==================== 插件元数据 ====================

__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb',
    'description': '选择性备份和迁移 Bot 配置、框架配置、插件数据，支持上传至云盘',
    'version': '1.6.0',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'license': 'MIT',
}


# ==================== 上下文与路径 ====================


def _get_ctx():
    """获取框架注入的插件上下文。框架在加载插件期间已设置好 ctx。"""
    from core.plugin.context import ctx as _ctx
    return _ctx


def _resolve_paths():
    """初始化路径常量。允许在框架 ctx 未就绪时 (例如单测) 用本地推断兜底。"""
    global PLUGIN_DIR, PROJECT_ROOT, CONFIG_DIR, DATA_DIR, CLOUD_CONFIG_PATH

    ctx = None
    try:
        ctx = _get_ctx()
    except Exception:
        ctx = None

    if ctx is not None and getattr(ctx, 'plugin_dir', None):
        # 框架正常加载路径
        PLUGIN_DIR = Path(ctx.plugin_dir)
        DATA_DIR = Path(ctx.data_dir)
    else:
        # 兜底: 用本文件位置推断 (单测 / 直接 import 时使用)
        PLUGIN_DIR = Path(__file__).resolve().parent.parent
        DATA_DIR = PLUGIN_DIR / 'data'

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 项目根目录 = 插件目录上两级 (plugins/备份工具 -> 项目根)
    PROJECT_ROOT = PLUGIN_DIR.parent.parent
    # 框架核心配置目录 (用于读取/恢复 bot.yaml 等, 不在此写入)
    CONFIG_DIR = PROJECT_ROOT / 'config'
    # 云盘配置文件, 放在插件 data/ 下, 由 ctx 管理
    CLOUD_CONFIG_FILE = 'cloud_backup.yaml'
    if ctx is not None:
        CLOUD_CONFIG_PATH = Path(ctx.get_data_path(CLOUD_CONFIG_FILE))
    else:
        CLOUD_CONFIG_PATH = DATA_DIR / CLOUD_CONFIG_FILE


# 默认占位, 真实值在模块导入末尾通过 _resolve_paths() 填充
PLUGIN_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Path = PLUGIN_DIR.parent.parent
CONFIG_DIR: Path = PROJECT_ROOT / 'config'
DATA_DIR: Path = PLUGIN_DIR / 'data'
CLOUD_CONFIG_PATH: Path = DATA_DIR / 'cloud_backup.yaml'


# ==================== 默认配置 ====================

# 备份选项默认值, 由 ctx.ensure_config('config.yaml') 写入 data/config.yaml
# 备份路径 (backup_dir) 留空表示用插件 data/backups/ 子目录;
# 用户可在 Web 面板或直接编辑 yaml 修改为任意绝对路径。
DEFAULT_BACKUP_CONFIG: Dict[str, Any] = {
    'backup_dir': '',          # 留空 = 插件 data/backups/; 也可填绝对路径如 /www/backups
    'include_config': True,   # 默认备份 config/
    'include_data': True,     # 默认备份 data/
    'max_upload_mb': 500,     # 上传备份文件大小上限
}

# 配置文件字段注释, 由 ctx.save_config(comments=...) 渲染
CONFIG_COMMENTS: Dict[str, Any] = {
    '__desc__': '备份工具配置 - 修改后无需重启, 下次备份即生效',
    'backup_dir': '备份文件存储目录; 留空使用插件目录下的 data/backups/, 也可填绝对路径',
    'include_config': '是否默认备份框架 config/ 目录',
    'include_data': '是否默认备份框架 data/ 目录',
    'max_upload_mb': 'Web 面板上传备份文件的大小上限 (MB)',
}

# 云盘配置默认值, 由 ctx.ensure_config('cloud_backup.yaml') 写入 data/cloud_backup.yaml
# providers 是用户配置的云盘列表, 初始为空字典
DEFAULT_CLOUD_CONFIG: Dict[str, Any] = {
    'providers': {},          # 云盘 provider 列表, 由 Web 面板管理
    'last_used': None,        # 最近使用的 provider id
}

# 云盘配置字段注释
CLOUD_CONFIG_COMMENTS: Dict[str, Any] = {
    '__desc__': '云盘备份配置 - 由 Web 面板管理, 一般无需手动编辑',
    'providers': '云盘 provider 字典, key 为 provider id, value 为各云盘配置',
    'last_used': '最近一次使用的 provider id',
}


def get_backup_dir() -> Path:
    """读取当前配置的备份输出目录, 目录不存在时自动创建。"""
    try:
        from core.plugin.context import ctx as _ctx
        cfg = _ctx.read_config('config.yaml') if _ctx else {}
    except Exception:
        cfg = {}
    custom = (cfg.get('backup_dir') or '').strip()
    if custom:
        p = Path(custom)
    else:
        p = DATA_DIR / 'backups'
    p.mkdir(parents=True, exist_ok=True)
    return p


_resolve_paths()
