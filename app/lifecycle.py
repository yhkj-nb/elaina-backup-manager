# plugins/备份工具/app/lifecycle.py
"""插件生命周期

框架在导入插件并收集注册项后调用 @on_load, 卸载或热重载前调用 @on_unload。
- on_load 期间: 读取/生成配置、注册 Web 页面、创建备份目录
- on_unload 期间: 注销页面, 释放资源
"""

from core.plugin.decorators import on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page

from .constants import (
    __plugin_meta__, get_backup_dir,
    DEFAULT_BACKUP_CONFIG, CONFIG_COMMENTS,
    DEFAULT_CLOUD_CONFIG, CLOUD_CONFIG_COMMENTS,
)
from .utils import log


@on_load
async def init():
    # 1) 确保备份输出目录存在 (从配置读取, 不存在则用 data/backups/)
    #    get_backup_dir() 内部已 mkdir
    get_backup_dir()

    # 2) 自动生成 data/config.yaml (备份路径与默认选项)
    #    ctx.ensure_config 只补齐第一层键, 不会破坏已有配置
    try:
        from core.plugin.context import ctx
        ctx.ensure_config(
            DEFAULT_BACKUP_CONFIG,
            filename='config.yaml',
            comments=CONFIG_COMMENTS,
        )
        # 3) 自动生成 data/cloud_backup.yaml (云盘配置骨架)
        ctx.ensure_config(
            DEFAULT_CLOUD_CONFIG,
            filename='cloud_backup.yaml',
            comments=CLOUD_CONFIG_COMMENTS,
        )
    except Exception as e:
        log.warning(f'生成配置文件失败 (非致命): {e}')

    log.info(f'🔧 重要信息备份与迁移工具 v{__plugin_meta__["version"]} 已加载')

    # 3) 注册 Web 面板, 通过 ctx.get_resource_path 定位 panel.html
    try:
        from core.plugin.context import ctx
        html_path = ctx.get_resource_path('app/panel.html')
    except Exception:
        # 兜底: 本文件同级目录
        from pathlib import Path
        html_path = Path(__file__).parent / 'panel.html'

    register_page(
        key='backup_manager',
        label='🔧 备份迁移',
        source='plugin',
        source_name='备份工具',
        html_file=html_path,
        icon='settings',
    )
    log.info('✅ 备份工具面板已注册 (含云盘备份)')


@on_unload
def cleanup():
    unregister_page('backup_manager')
    log.info('🔧 重要信息备份与迁移工具已卸载')
