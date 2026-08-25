# plugins/备份工具/app/lifecycle.py
"""插件生命周期

框架注册时机:
- register_page: 模块导入时立刻调用 (与 @register_route 同阶段), 不放在 on_load 内
- on_load: 加载完毕后生成统一配置文件 data/config.yaml
- on_unload: 卸载前注销页面 (框架不会按插件所有者自动清理页面)

注意:
- data/ 目录由框架在加载插件时自动创建, 代码无需 mkdir
- 所有配置 (备份路径 + 云盘 provider) 统一放在一个 data/config.yaml 里
- ctx 引用必须在模块顶层通过 `import core.plugin.context as _ctx_mod` 获取,
  然后访问 `_ctx_mod.ctx`; 不能用 `from ... import ctx`, 否则绑定的可能是
  import 时的 None 快照, 导致 on_load 里 ctx.ensure_config() 报错
"""

from pathlib import Path

import core.plugin.context as _ctx_mod
from core.plugin.decorators import on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page

from .constants import (
    __plugin_meta__,
    DEFAULT_CONFIG, CONFIG_COMMENTS,
)
from .utils import log


# ==================== Web 面板注册 (模块导入时执行) ====================
# 与 @register_route 同阶段注册, 才能被框架正确记录插件归属
_ctx = _ctx_mod.ctx
if _ctx is not None and getattr(_ctx, 'get_resource_path', None):
    _html_path = Path(_ctx.get_resource_path('app/panel.html'))
else:
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
    # ⚠️ 必须使用模块顶层的 _ctx 快照, 不能再去取 _ctx_mod.ctx!
    # 框架的加载顺序:
    #   1) 设置 _ctx_mod.ctx = plugin_ctx  →  模块导入时快照有效
    #   2) 导入插件模块 (含 on_load 装饰器收集)
    #   3) _finalize_plugin 中先把 _ctx_mod.ctx = None   ← 先置空!
    #   4) 最后才调用 on_load hooks                      ← 后执行!
    # 所以 on_load 期间动态取 _ctx_mod.ctx 一定是 None, 必须用模块级快照
    if _ctx is None:
        log.warning('ctx 快照为空, 跳过配置文件生成 (非致命)')
    else:
        # 自动生成 data/config.yaml (首次加载时)
        # 统一配置: 备份路径 backup_dir + 云盘 providers + 其他选项
        # ensure_config 只补齐缺失的顶层键, 不会覆盖用户已有配置
        try:
            _ctx.ensure_config(
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
