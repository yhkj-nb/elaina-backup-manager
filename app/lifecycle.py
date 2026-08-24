# plugins/备份工具/app/lifecycle.py
"""插件生命周期"""

from core.plugin.decorators import on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page
from core.base.logger import get_logger, PLUGIN

from .constants import PLUGIN_DIR, DATA_DIR, __plugin_meta__
from .utils import log


@on_load
async def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f'🔧 重要信息备份与迁移工具 v{__plugin_meta__["version"]} 已加载')
    html_path = PLUGIN_DIR / 'app' / 'panel.html'
    html_content = ''
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    register_page(
        key='backup_manager',
        label='🔧 备份迁移',
        source='plugin',
        source_name='备份工具',
        html=html_content,
        icon='settings',
    )
    log.info('✅ 备份工具面板已注册 (含云盘备份)')


@on_unload
def cleanup():
    unregister_page('backup_manager')
    log.info('🔧 重要信息备份与迁移工具已卸载')
