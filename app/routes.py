# plugins/备份工具/app/routes.py
"""Web 路由

⚠️ 框架路由是精确匹配 (METHOD, path)，不支持路径参数 {param}
   所有需要传文件名的操作都用 query 参数 ?fn=xxx / ?pid=xxx
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote

from aiohttp import web

from core.plugin.web_pages import register_route

import core.plugin.context as _ctx_mod

# ⚠️ 模块顶层获取 ctx 快照 — 框架在模块导入后立即清空 _ctx_mod.ctx
# 任何运行时 (Web 请求 / on_load 之后) 再读 _ctx_mod.ctx 都是 None!
_ctx = _ctx_mod.ctx

from .constants import get_backup_dir
from .utils import log, format_size, get_disk_usage, get_config_files, get_config_size, get_data_files, get_data_size
from .backup import create_backup
from .restore import restore_backup, parse_backup_info
from .backup_list import get_backups_list, delete_backup_file
from .plugins_scan import (
    get_plugin_inventory, get_plugin_summary, get_plugin_source_summary,
)
from .modules_scan import (
    get_module_inventory, get_module_summary, get_module_source_summary,
)
from . import cloud


# ==================== 路径常量 ====================

PAGE_PATH = '/api/ext/backup_manager'
STATS_PATH = '/api/ext/backup_manager/stats'
BACKUP_CREATE_PATH = '/api/ext/backup_manager/backup'
UPLOAD_PATH = '/api/ext/backup_manager/upload'
RESTORE_PATH = '/api/ext/backup_manager/restore'
BACKUPS_LIST_PATH = '/api/ext/backup_manager/backups'
DELETE_PATH = '/api/ext/backup_manager/delete'
DOWNLOAD_PATH = '/api/ext/backup_manager/download'
DISK_USAGE_PATH = '/api/ext/backup_manager/disk_usage'

# 云盘相关路由
CLOUD_SCHEMA_PATH = '/api/ext/backup_manager/cloud/schema'
CLOUD_LIST_PATH = '/api/ext/backup_manager/cloud/list'
CLOUD_GET_PATH = '/api/ext/backup_manager/cloud/get'
CLOUD_SAVE_PATH = '/api/ext/backup_manager/cloud/save'
CLOUD_DELETE_PATH = '/api/ext/backup_manager/cloud/delete'
CLOUD_TEST_PATH = '/api/ext/backup_manager/cloud/test'
CLOUD_FILES_PATH = '/api/ext/backup_manager/cloud/files'
CLOUD_UPLOAD_PATH = '/api/ext/backup_manager/cloud/upload'
CLOUD_DOWNLOAD_PATH = '/api/ext/backup_manager/cloud/download'
CLOUD_DELETE_FILE_PATH = '/api/ext/backup_manager/cloud/delete_file'
CLOUD_SYNC_STATE_PATH = '/api/ext/backup_manager/cloud/sync_state'


# ==================== 页面 ====================


@register_route('GET', PAGE_PATH, auth=False)
async def serve_page(request):
    # panel.html 与 routes.py 同处 app/ 目录, 直接用本文件位置定位, 最可靠
    # (框架的 get_resource_path 在不同版本可能返回 str 或路径解析不一致, 故不再依赖它)
    html_path = Path(__file__).resolve().parent / 'panel.html'
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except Exception as e:
        log.error(f'读取面板失败: {e}')
        return web.Response(text='<p>页面文件不存在</p>', content_type='text/html')


# ==================== 本地备份 ====================


@register_route('GET', STATS_PATH, auth=False)
async def api_stats(request):
    config_files = get_config_files()
    config_size = get_config_size()
    data_files = get_data_files()
    data_size = get_data_size()
    backup_dir = get_backup_dir()
    backup_count = len(list(backup_dir.glob('backup_*.zip')))
    # 插件 / 模块各自只扫一遍, 数据与源码统计共用同一份 inventory
    plugin_inventory = get_plugin_inventory()
    plugin_summary = get_plugin_summary(plugin_inventory)
    plugin_src_summary = get_plugin_source_summary(plugin_inventory)
    module_inventory = get_module_inventory()
    module_summary = get_module_summary(module_inventory)
    module_src_summary = get_module_source_summary(module_inventory)
    disk_usage = get_disk_usage()
    # 前端直接展示用的格式化字段 + 修正字段名 (used_pct -> usage_percent 对齐 panel.html 读取)
    disk_usage['used_readable'] = format_size(disk_usage.get('used', 0))
    disk_usage['free_readable'] = format_size(disk_usage.get('free', 0))
    disk_usage['total_readable'] = format_size(disk_usage.get('total', 0))
    disk_usage['usage_percent'] = disk_usage.get('used_pct', 0.0)

    return web.json_response({
        'backup_location': str(backup_dir),
        'config_count': len(config_files),
        'config_files': config_files,
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_files),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'plugin_count': plugin_summary.get('plugin_count', 0),
        'plugin_with_data_count': plugin_summary.get('plugin_with_data_count', 0),
        'plugin_file_count': plugin_summary.get('file_count', 0),
        'plugin_size': plugin_summary.get('size', 0),
        'plugin_size_readable': plugin_summary.get('size_readable', '0 B'),
        'plugins': plugin_summary.get('plugins', []),
        'plugin_src_count': plugin_src_summary.get('plugin_with_src_count', 0),
        'plugin_src_file_count': plugin_src_summary.get('file_count', 0),
        'plugin_src_size': plugin_src_summary.get('size', 0),
        'plugin_src_size_readable': plugin_src_summary.get('size_readable', '0 B'),
        'module_count': module_summary.get('module_count', 0),
        'module_with_data_count': module_summary.get('module_with_data_count', 0),
        'module_file_count': module_summary.get('file_count', 0),
        'module_size': module_summary.get('size', 0),
        'module_size_readable': module_summary.get('size_readable', '0 B'),
        'modules': module_summary.get('modules', []),
        'module_src_count': module_src_summary.get('module_with_src_count', 0),
        'module_src_file_count': module_src_summary.get('file_count', 0),
        'module_src_size': module_src_summary.get('size', 0),
        'module_src_size_readable': module_src_summary.get('size_readable', '0 B'),
        'backup_count': backup_count,
        'disk_usage': disk_usage,
    })


def _parse_selection(payload: dict, field: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """解析面板提交的插件 / 模块选择, 返回 (选择列表, 错误信息)。

    - 字段缺省或为 null → (None, None), 表示该分类全选
    - 数组 → (去重后的名称列表, None), 空数组表示该分类一个都不备份
    - 其它类型 → (None, 错误信息)
    """
    if field not in payload:
        return None, None
    raw = payload[field]
    if raw is None:
        return None, None
    if not isinstance(raw, list):
        return None, f'参数 {field} 必须为数组'
    names: List[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None, f'参数 {field} 只能包含字符串'
        name = item.strip()
        if name and name not in names:
            names.append(name)
    return names, None


def _parse_flag(payload: dict, field: str, default: bool = True) -> Tuple[bool, Optional[str]]:
    """解析面板提交的内容类型开关 (数据文件 / 配置文件), 返回 (布尔值, 错误信息)。

    字段缺省时用 ``default``; 也接受 0/1 字符串等常见 JSON 变体。
    """
    if field not in payload or payload[field] is None:
        return default, None
    raw = payload[field]
    if isinstance(raw, bool):
        return raw, None
    if isinstance(raw, (int, float)):
        return bool(raw), None
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ('true', '1', 'yes', 'on'):
            return True, None
        if low in ('false', '0', 'no', 'off', ''):
            return False, None
    return default, f'参数 {field} 必须为布尔值'


@register_route('POST', BACKUP_CREATE_PATH, auth=False)
async def api_create_backup(request):
    try:
        # v2.6 起面板可以勾选要备份的插件 / 模块;
        # v2.7 起「数据文件」与「配置文件(源码与自带配置)」也可各自开关:
        #   data=true/false    → 插件 / 模块的 data 运行数据
        #   config=true/false  → 插件 / 模块除 data/ 外的全部文件
        # 选择字段缺省或为 null 表示全选, 空数组表示该分类不备份。
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        plugins, err = _parse_selection(payload, 'plugins')
        if err:
            return web.json_response({'success': False, 'error': err})
        modules, err = _parse_selection(payload, 'modules')
        if err:
            return web.json_response({'success': False, 'error': err})
        if plugins == [] and modules == []:
            return web.json_response({'success': False, 'error': '请至少选择一个插件或模块'})

        include_data_files, err = _parse_flag(payload, 'data')
        if err:
            return web.json_response({'success': False, 'error': err})
        include_config_files, err = _parse_flag(payload, 'config')
        if err:
            return web.json_response({'success': False, 'error': err})
        if not include_data_files and not include_config_files:
            return web.json_response({'success': False, 'error': '请至少勾选「数据文件」或「配置文件」'})

        # 备份是同步 IO (打包几百 MB), 放到线程里避免阻塞 aiohttp 事件循环。
        filename = await asyncio.to_thread(
            create_backup,
            plugins=plugins,
            modules=modules,
            include_data_files=include_data_files,
            include_config_files=include_config_files,
        )
        if filename:
            return web.json_response({
                'success': True,
                'filename': filename,
                'scope': {
                    'plugins': plugins,
                    'modules': modules,
                    'data': include_data_files,
                    'config': include_config_files,
                },
            })
        return web.json_response({'success': False, 'error': '备份创建失败'})
    except Exception as e:
        log.error(f'备份失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('POST', UPLOAD_PATH, auth=False)
async def api_upload_backup(request):
    try:
        reader = await request.multipart()
        file_data = None
        filename = 'unknown.zip'
        async for field in reader:
            if field.name == 'file' and field.filename:
                file_data = await field.read(decode=False)
                filename = field.filename
                break

        if not file_data:
            return web.json_response({'success': False, 'error': '未找到上传文件'})
        if not filename.lower().endswith('.zip'):
            return web.json_response({'success': False, 'error': '仅支持 ZIP 文件'})
        if len(file_data) == 0:
            return web.json_response({'success': False, 'error': '文件为空'})
        if len(file_data) > 500 * 1024 * 1024:
            return web.json_response({'success': False, 'error': '文件过大，请上传小于 500MB 的文件'})

        tmp_dir = get_backup_dir() / 'temp'
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        tmp_path.write_bytes(file_data)

        try:
            info = parse_backup_info(tmp_path)
            info['file_size'] = format_size(tmp_path.stat().st_size)
            info['original_filename'] = filename
            return web.json_response({
                'success': True,
                'filename': filename,
                'size': info['file_size'],
                'info': info,
                'temp_path': str(tmp_path),
            })
        except Exception as e:
            log.error(f'解析上传文件失败: {e}')
            return web.json_response({'success': False, 'error': f'解析失败: {str(e)}'})

    except Exception as e:
        log.error(f'上传失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('POST', RESTORE_PATH, auth=False)
async def api_restore_backup(request):
    try:
        reader = await request.multipart()
        file_data = None
        async for field in reader:
            if field.name == 'file' and field.filename:
                file_data = await field.read(decode=False)
                break

        if not file_data:
            return web.json_response({'success': False, 'error': '未找到上传文件'})
        if len(file_data) == 0:
            return web.json_response({'success': False, 'error': '文件为空'})

        reader = await request.multipart()
        temp_path_str = None
        async for field in reader:
            if field.name == 'temp_path':
                val = await field.read(decode=False)
                if val:
                    temp_path_str = val.decode('utf-8').strip()
                break

        if temp_path_str and Path(temp_path_str).exists():
            zip_path = Path(temp_path_str)
        else:
            tmp_dir = get_backup_dir() / 'temp'
            tmp_dir.mkdir(exist_ok=True)
            zip_path = tmp_dir / f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            zip_path.write_bytes(file_data)

        try:
            result = restore_backup(zip_path)
            if result['success']:
                return web.json_response({
                    'success': True, 'message': '恢复成功！', 'result': result,
                })
            else:
                return web.json_response({
                    'success': False, 'error': '恢复失败', 'errors': result.get('errors', []),
                })
        finally:
            if not temp_path_str or not Path(temp_path_str).exists():
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass

    except Exception as e:
        log.error(f'恢复失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('GET', BACKUPS_LIST_PATH, auth=False)
async def api_backups(request):
    backups = get_backups_list()
    return web.json_response({'success': True, 'backups': backups, 'count': len(backups)})


@register_route('DELETE', DELETE_PATH, auth=False)
async def api_delete_backup(request):
    filename = unquote(request.query.get('fn', ''))
    if not filename:
        return web.json_response({'success': False, 'error': '缺少文件名'})
    result = delete_backup_file(filename)
    if result['success']:
        return web.json_response({'success': True, 'message': result.get('message', '已删除')})
    else:
        return web.json_response({'success': False, 'error': result.get('error', '删除失败')})


@register_route('GET', DOWNLOAD_PATH, auth=False)
async def api_download_backup(request):
    filename = unquote(request.query.get('fn', ''))
    if not filename:
        return web.json_response({'success': False, 'error': '缺少文件名'})
    if '..' in filename or filename.endswith('/'):
        return web.json_response({'success': False, 'error': '非法文件名'})
    if not filename.endswith('.zip'):
        return web.json_response({'success': False, 'error': '仅支持 ZIP 文件'})

    file_path = get_backup_dir() / filename
    if not file_path.exists() or not file_path.is_file():
        return web.json_response({'success': False, 'error': f'文件不存在: {filename}'})

    file_size = file_path.stat().st_size
    response = web.StreamResponse(
        headers={
            'Content-Type': 'application/zip',
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(file_size),
            'Cache-Control': 'no-cache',
        }
    )
    await response.prepare(request)
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            await response.write(chunk)
    log.info(f'⬇️ 下载完成: {filename} ({format_size(file_size)})')
    return response


@register_route('GET', DISK_USAGE_PATH, auth=False)
async def api_disk_usage(request):
    usage = get_disk_usage()
    usage['used_readable'] = format_size(usage.get('used', 0))
    usage['free_readable'] = format_size(usage.get('free', 0))
    usage['total_readable'] = format_size(usage.get('total', 0))
    usage['usage_percent'] = usage.get('used_pct', 0.0)
    return web.json_response({'success': True, 'disk_usage': usage})


# ==================== 云盘备份 ====================


@register_route('GET', CLOUD_SCHEMA_PATH, auth=False)
async def api_cloud_schema(request):
    """返回云盘类型表单 schema, 供前端动态渲染"""
    return web.json_response({'success': True, 'schema': cloud.provider_schema()})


@register_route('GET', CLOUD_LIST_PATH, auth=False)
async def api_cloud_list(request):
    return web.json_response({'success': True, 'providers': cloud.list_providers_masked()})


@register_route('GET', CLOUD_GET_PATH, auth=False)
async def api_cloud_get(request):
    pid = request.query.get('pid', '')
    if not pid:
        return web.json_response({'success': False, 'error': '缺少 pid'})
    cfg = cloud.get_provider_raw(pid)
    if not cfg:
        return web.json_response({'success': False, 'error': '配置不存在'})
    return web.json_response({'success': True, 'provider': cloud._mask_secrets(cfg)})


@register_route('POST', CLOUD_SAVE_PATH, auth=False)
async def api_cloud_save(request):
    try:
        data = await request.json()
        pid = data.pop('id', None) or None
        ptype = (data.get('type') or '').lower()
        if ptype not in cloud._PROVIDER_CLASSES:
            return web.json_response({'success': False, 'error': f'不支持的类型: {ptype}'})
        # 基本校验
        name = (data.get('name') or '').strip()
        if not name:
            return web.json_response({'success': False, 'error': '名称不能为空'})
        # remote_path 允许留空 (默认上传到根)
        data.setdefault('remote_path', '')
        saved = cloud.upsert_provider(pid, data)
        log.info(f'☁️ 云盘配置已保存: {saved.get("id")} ({saved.get("type")})')
        return web.json_response({'success': True, 'provider': saved})
    except Exception as e:
        log.error(f'保存云盘配置失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('DELETE', CLOUD_DELETE_PATH, auth=False)
async def api_cloud_delete(request):
    pid = request.query.get('pid', '')
    if not pid:
        return web.json_response({'success': False, 'error': '缺少 pid'})
    ok = cloud.delete_provider(pid)
    if ok:
        return web.json_response({'success': True, 'message': '已删除'})
    return web.json_response({'success': False, 'error': '配置不存在'})


@register_route('POST', CLOUD_TEST_PATH, auth=False)
async def api_cloud_test(request):
    """测试连接 - 支持临时配置 (不保存) 或 已保存配置"""
    try:
        data = await request.json()
        pid = data.get('pid')
        if pid:
            provider = cloud.build_provider(pid)
            if not provider:
                return web.json_response({'success': False, 'error': '云盘配置不存在或类型不支持'})
        else:
            # 用临时配置测试
            ptype = (data.get('type') or '').lower()
            cls = cloud._PROVIDER_CLASSES.get(ptype)
            if not cls:
                return web.json_response({'success': False, 'error': f'不支持的类型: {ptype}'})
            provider = cls(data)
        result = await provider.test()
        return web.json_response(result)
    except Exception as e:
        log.error(f'云盘测试失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('GET', CLOUD_FILES_PATH, auth=False)
async def api_cloud_files(request):
    pid = request.query.get('pid', '')
    remote_path = request.query.get('path', '')
    if not pid:
        return web.json_response({'success': False, 'error': '缺少 pid'})
    result = await cloud.list_cloud_backups(pid, remote_path)
    return web.json_response(result)


@register_route('POST', CLOUD_UPLOAD_PATH, auth=False)
async def api_cloud_upload(request):
    """上传指定本地备份到云盘"""
    try:
        data = await request.json()
        pid = data.get('pid', '')
        filename = data.get('filename', '')
        if not pid or not filename:
            return web.json_response({'success': False, 'error': '缺少 pid 或 filename'})
        result = await cloud.upload_backup_to_cloud(pid, filename)
        return web.json_response(result)
    except Exception as e:
        log.error(f'上传到云盘失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})


@register_route('GET', CLOUD_DOWNLOAD_PATH, auth=False)
async def api_cloud_download(request):
    """从云盘下载备份到本地"""
    pid = request.query.get('pid', '')
    remote_path = request.query.get('path', '')
    if not pid or not remote_path:
        return web.json_response({'success': False, 'error': '缺少 pid 或 path'})
    result = await cloud.download_cloud_backup(pid, remote_path)
    return web.json_response(result)


@register_route('DELETE', CLOUD_DELETE_FILE_PATH, auth=False)
async def api_cloud_delete_file(request):
    pid = request.query.get('pid', '')
    remote_path = request.query.get('path', '')
    if not pid or not remote_path:
        return web.json_response({'success': False, 'error': '缺少 pid 或 path'})
    result = await cloud.delete_cloud_backup(pid, remote_path)
    return web.json_response(result)


@register_route('GET', CLOUD_SYNC_STATE_PATH, auth=False)
async def api_cloud_sync_state(request):
    return web.json_response({'success': True, 'syncs': cloud.get_sync_state()})
