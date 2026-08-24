# plugins/备份工具/app/constants.py
"""路径常量与插件元数据"""

from pathlib import Path

# ==================== 插件元数据 ====================

__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb',
    'description': '选择性备份和迁移 Bot 配置、框架配置、插件数据，支持上传至云盘',
    'version': '1.6.0',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'license': 'MIT',
}

# ==================== 路径常量 ====================

PLUGIN_DIR = Path(__file__).parent.parent.resolve()  # app/ 的父目录即插件根
PROJECT_ROOT = PLUGIN_DIR.parent.parent
CONFIG_DIR = PROJECT_ROOT / 'config'
DATA_DIR = PLUGIN_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 云盘配置文件路径(框架 config/ 目录下)
CLOUD_CONFIG_PATH = CONFIG_DIR / 'cloud_backup.yaml'
