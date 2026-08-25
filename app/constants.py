# plugins/备份工具/app/constants.py
"""路径常量与插件元数据

所有路径基于框架注入的插件上下文 (core.plugin.context.ctx):
- ctx.plugin_dir     插件根目录 (本文件所在目录的父目录)
- ctx.data_dir       插件 data/ 目录 (框架加载时自动创建, 代码无需 mkdir)
- ctx.get_resource_path(filename)  资源文件路径
- ctx.get_data_path(filename)       data/ 下文件路径

配置文件约定:
- data/config.yaml   统一配置: 备份路径 + 云盘 provider 列表 (框架 ensure_config 自动生成)
"""

from pathlib import Path
from typing import Any, Dict

import core.plugin.context as _ctx_mod

# ⚠️ 模块顶层获取 ctx 的快照引用 — 必须在模块导入时 (此时 _ctx_mod.ctx 仍有效) 保存
# 框架加载顺序: 设 ctx → 导入模块 → 置空 ctx → 调 on_load
# 因此任何运行时 (on_load 之后) 再去读 _ctx_mod.ctx 拿到的都是 None!
# 所有后续函数都必须使用本模块级的 _ctx 快照变量。
_ctx = _ctx_mod.ctx

# ==================== 插件元数据 ====================

__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb',
    'description': '选择性备份和迁移 Bot 配置、框架配置、插件数据，支持上传至云盘',
    'version': '1.7.0',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'license': 'MIT',
}


# ==================== 上下文与路径 ====================


def _get_ctx():
    """获取框架注入的插件上下文 (模块级快照)。

    框架在模块导入前设置、导入后 (on_load 前) 立即清空 _ctx_mod.ctx,
    因此必须使用本模块顶层捕获的 _ctx 快照, 不能再动态读取 _ctx_mod.ctx。
    """
    return _ctx


def _resolve_paths():
    """初始化路径常量。允许在框架 ctx 未就绪时 (例如单测) 用本地推断兜底。

    注意: data/ 目录由框架在加载插件时自动创建, 此处不再 mkdir。
    """
    global PLUGIN_DIR, PROJECT_ROOT, CONFIG_DIR, DATA_DIR

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

    # 项目根目录 = 插件目录上两级 (plugins/备份工具 -> 项目根)
    PROJECT_ROOT = PLUGIN_DIR.parent.parent
    # 框架核心配置目录 (用于读取/恢复 bot.yaml 等, 不在此写入)
    CONFIG_DIR = PROJECT_ROOT / 'config'


# 默认占位, 真实值在模块导入末尾通过 _resolve_paths() 填充
PLUGIN_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_ROOT: Path = PLUGIN_DIR.parent.parent
CONFIG_DIR: Path = PROJECT_ROOT / 'config'
DATA_DIR: Path = PLUGIN_DIR / 'data'


# ==================== 默认配置 ====================

# 统一配置文件 data/config.yaml 的默认值, 由 ctx.ensure_config('config.yaml') 写入
# - backup_dir: 自定义备份路径; 留空表示直接放在框架自动创建的 data/ 目录下
# - providers:  云盘 provider 字典, 由 Web 面板管理
# - last_used:  最近使用的 provider id
DEFAULT_CONFIG: Dict[str, Any] = {
    'backup_dir': '',          # 留空 = 直接放在 data/ 目录下; 也可填绝对路径如 /www/backups
    'include_config': True,   # 默认备份框架 config/ 目录
    'include_data': True,     # 默认备份框架 data/ 目录
    'max_upload_mb': 500,     # Web 面板上传备份文件的大小上限 (MB)
    'providers': {},          # 云盘 provider 列表, 由 Web 面板管理
    'last_used': None,        # 最近使用的 provider id
}

# 配置文件字段注释, 由 ctx.ensure_config(comments=...) 渲染
CONFIG_COMMENTS: Dict[str, Any] = {
    '__desc__': '备份工具配置 - 由框架自动生成, 修改后无需重启, 下次操作即生效',
    'backup_dir': '备份文件存储目录; 留空则直接放在框架自动创建的 data/ 目录下; 也可填绝对路径',
    'include_config': '是否默认备份框架 config/ 目录',
    'include_data': '是否默认备份框架 data/ 目录',
    'max_upload_mb': 'Web 面板上传备份文件的大小上限 (MB)',
    'providers': '云盘 provider 字典, key 为 provider id, value 为各云盘配置 (由 Web 面板管理)',
    'last_used': '最近一次使用的 provider id',
}


def get_backup_dir() -> Path:
    """读取当前配置的备份输出目录。

    - 配置 backup_dir 留空: 直接返回框架自动创建的 data/ 目录
    - 配置 backup_dir 填了路径: 返回该路径, 目录不存在时自动创建 (仅对自定义路径 mkdir)
    """
    try:
        # 使用模块级 _ctx 快照 (框架加载后 _ctx_mod.ctx 已被置为 None)
        cfg = _ctx.read_config('config.yaml') if _ctx else {}
    except Exception:
        cfg = {}
    custom = (cfg.get('backup_dir') or '').strip()
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)  # 自定义路径才需要 mkdir
        return p
    # 留空: 直接用框架自动创建的 data/ 目录, 不需要再 mkdir
    return DATA_DIR


_resolve_paths()
