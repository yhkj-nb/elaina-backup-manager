# plugins/备份工具/main.py
"""重要信息备份与迁移工具 - v2.0

入口文件 - 按固定顺序加载 app/ 下的公开子模块, 触发路由、页面与生命周期注册。
功能实现均位于 app/ 各子模块, 本文件不包含业务逻辑。

作者: yhkj-nb
版本: 2.0.0
仓库: https://github.com/yhkj-nb/elaina-backup-manager
许可证: MIT
"""

import importlib
from pathlib import Path

from core.base.logger import PLUGIN, get_logger

# ==================== 插件元数据 ====================
# Web 面板会展示这些字段
__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb',
    'description': '选择性备份和迁移 Bot 配置、插件数据, 支持上传至云盘',
    'version': '2.0.0',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'license': 'MIT',
}

log = get_logger(PLUGIN, '备份工具')

# 按固定顺序加载 app/ 下的公开子模块 (跳过 _ 开头的内部模块),
# 导入过程会触发各模块顶层的 @register_route 装饰器,
# lifecycle.py 中的 @on_load / @on_unload 也会被收集。
_APP_DIR = Path(__file__).parent / 'app'
for _path in sorted(_APP_DIR.glob('[!_]*.py')):
    importlib.import_module(f'plugins.备份工具.app.{_path.stem}')

log.info('🔧 重要信息备份与迁移工具 v%s 已加载', __plugin_meta__['version'])
