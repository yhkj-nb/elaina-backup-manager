# plugins/备份工具/main.py
"""
重要信息备份与迁移工具 - v1.6

功能:
- 备份 config/ 目录下的配置文件
- 备份 data/ 目录下的插件数据
- 上传/下载/删除备份文件
- 恢复备份
- 云盘备份 (WebDAV / S3 兼容 / FTP, 覆盖坚果云 / NextCloud / R2 / B2 / MinIO / NAS 等)

代码组织 (本文件仅为入口, 实现拆分到 app/ 目录):
  app/__init__.py       包入口
  app/constants.py      路径常量与插件元数据
  app/utils.py          通用工具函数
  app/backup.py         本地备份创建
  app/restore.py        备份恢复
  app/backup_list.py    本地备份列表管理
  app/cloud.py          云盘备份 (WebDAV / S3 / FTP)
  app/routes.py         Web 路由 (含云盘路由)
  app/lifecycle.py      插件生命周期
  app/panel.html        Web 面板

作者: yhkj-nb
版本: 1.6.0
仓库: https://github.com/yhkj-nb/elaina-backup-manager
许可证: MIT
"""

# 兼容两种插件加载方式:
# 1. 作为包内模块加载 (plugins.备份工具.main) -> 使用相对导入 from . import app
# 2. 作为顶层模块加载 (把插件目录加入 sys.path 后 import main) -> 把当前目录加入 sys.path 后 import app
try:
    from . import app  # noqa: F401
except ImportError:
    import os
    import sys
    _PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
    if _PLUGIN_DIR not in sys.path:
        sys.path.insert(0, _PLUGIN_DIR)
    import app  # noqa: F401

# 导入 app 包会自动完成:
# 1. 注册所有 Web 路由 (routes.py 中的 register_route 装饰器在导入时执行)
# 2. 注册插件生命周期钩子 (lifecycle.py 中的 on_load/on_unload 装饰器在导入时执行)

__all__ = ['app']
