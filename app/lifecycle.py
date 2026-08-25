# plugins/备份工具/app/lifecycle.py
"""插件生命周期

框架注册时机:
- register_page: 模块导入时立刻调用 (与 @register_route 同阶段), 不放在 on_load 内
- on_load: 加载完毕后生成统一配置文件 data/config.yaml
- on_unload: 卸载前注销页面 (框架不会按插件所有者自动清理页面)

注意:
- data/ 目录由框架在加载插件时自动创建, 代码无需 mkdir
- 所有配置 (备份路径 + 云盘 provider) 统一放在一个 data/config.yaml 里
"""

from pathlib import Path

from core.plugin.decorators import on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page

from .constants import (
    __plugin_meta__,
    DEFAULT_CONFIG, CONFIG_COMMENTS,
)
from .utils import log


# ==================== Web 面板注册 (模块导入时执行) ====================
# 与 @register_route 同阶段注册, 才能被框架正确记录插件归属
try:
    from core.plugin.context import ctx
    _html_path = ctx.get_resource_path('app/panel.html')
except Exception:
    # 兜底: 本文件同级目录
    _html_path = Path(__file__).parent / 'panel.html'

register_page(
    key='backup_manager',
    label='🔧 备份迁移',
    source='plugin',
    source_name='备份工具',
    html_file=_html_path,
    icon='settings',
)
log.info('✅ 备份工具面板已注册 (含云盘备份)')


# ==================== on_load: 生成统一配置 ====================


@on_load
async def init():
    # 自动生成 data/config.yaml (首次加载时)
    # 统一配置: 备份路径 backup_dir + 云盘 providers + 其他选项
    # ensure_config 只补齐缺失的顶层键, 不会覆盖用户已有配置
    try:
        from core.plugin.context import ctx
        ctx.ensure_config(
            DEFAULT_CONFIG,
            filename='config.yaml',
            comments=CONFIG_COMMENTS,
        )
    except Exception as e:
        log.warning(f'生成配置文件失败 (非致命): {e}')

    log.info(f'🔧 重要信息备份与迁移工具 v{__plugin_meta__["version"]} 已加载')


@on_unload
def cleanup():
    unregister_page('backup_manager')
    log.info('🔧 重要信息备份与迁移工具已卸载')
