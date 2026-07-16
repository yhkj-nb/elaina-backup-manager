# plugins/备份工具/main.py
"""
重要信息备份与迁移工具 - v1.5

功能：
- 备份 config/ 目录下的配置文件
- 备份 data/ 目录下的插件数据
- 上传/下载/删除备份文件
- 恢复备份

作者: yhkj-nb
版本: 1.5
仓库: https://github.com/yhkj-nb/elaina-backup-manager
许可证: MIT
"""

import json
import zipfile
import re
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import unquote

from aiohttp import web

from core.plugin.decorators import on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page, register_route
from core.base.logger import get_logger, PLUGIN

# ==================== 插件元数据 ====================

__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb',
    'description': '选择性备份和迁移 Bot 配置、框架配置、插件数据',
    'version': '1.5',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'license': 'MIT',
}

log = get_logger(PLUGIN, '备份工具')

# ==================== 路径常量 ====================

PLUGIN_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = PLUGIN_DIR.parent.parent
CONFIG_DIR = PROJECT_ROOT / 'config'
DATA_DIR = PLUGIN_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 工具函数 ====================


def format_size(size_bytes: int) -> str:
    if size_bytes < 0:
        return "0 B"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def get_config_files() -> List[str]:
    files = []
    if CONFIG_DIR.exists():
        for f in CONFIG_DIR.glob('*.yaml'):
            files.append(f.name)
        for f in CONFIG_DIR.glob('*.yml'):
            files.append(f.name)
    return sorted(files)


def get_data_files() -> List[Path]:
    files = []
    data_root = PROJECT_ROOT / 'data'
    if data_root.exists():
        for f in data_root.rglob('*'):
            if f.is_file() and '备份工具' not in str(f):
                files.append(f)
    return files


def get_config_size() -> int:
    total = 0
    if CONFIG_DIR.exists():
        for f in CONFIG_DIR.glob('*.yaml'):
            total += f.stat().st_size
        for f in CONFIG_DIR.glob('*.yml'):
            total += f.stat().st_size
    return total


def get_data_size() -> int:
    total = 0
    data_root = PROJECT_ROOT / 'data'
    if data_root.exists():
        for f in data_root.rglob('*'):
            if f.is_file() and '备份工具' not in str(f):
                total += f.stat().st_size
    return total


def get_disk_usage() -> Dict[str, Any]:
    try:
        st = os.statvfs(str(DATA_DIR.parent))
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        return {
            'total': format_size(total),
            'used': format_size(used),
            'free': format_size(free),
            'usage_percent': round((used / total) * 100, 1) if total > 0 else 0,
        }
    except Exception:
        return {'total': '未知', 'used': '未知', 'free': '未知', 'usage_percent': 0}


# ==================== 备份功能 ====================


def generate_backup_info(include_config: bool = True, include_data: bool = True) -> Dict[str, Any]:
    bot_config = {}
    bot_yaml = CONFIG_DIR / 'bot.yaml'
    if bot_yaml.exists() and include_config:
        try:
            import yaml
            with open(bot_yaml, 'r', encoding='utf-8') as f:
                bot_config = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning(f"读取 bot.yaml 失败: {e}")

    config_files = get_config_files() if include_config else []
    config_size = get_config_size() if include_config else 0
    data_files = get_data_files() if include_data else []
    data_size = get_data_size() if include_data else 0

    return {
        'version': '1.5',
        'created_at': datetime.now().isoformat(),
        'created_at_readable': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bot_config': {
            'appid': bot_config.get('appid', ''),
            'platform': bot_config.get('platform', ''),
        } if include_config and bot_config else {},
        'include_config': include_config,
        'include_data': include_data,
        'config_files': config_files,
        'config_count': len(config_files),
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_files),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'total_size_readable': format_size(config_size + data_size),
        'backup_location': str(DATA_DIR),
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
    }


def generate_readme(info: Dict[str, Any]) -> str:
    lines = [
        '# 备份说明', '',
        f'**生成时间**: {info.get("created_at_readable", "未知")}',
        f'**备份版本**: v{info.get("version", "unknown")}',
        f'**主机名**: {info.get("hostname", "未知")}', '', '---', '',
        '## 备份内容', '',
    ]
    if info.get('include_config'):
        lines.append(f'- **配置文件**: {info.get("config_count", 0)} 个 ({info.get("config_size_readable", "0 B")})')
        for f in info.get('config_files', []):
            lines.append(f'  - `{f}`')
    else:
        lines.append('- **配置文件**: 未备份')
    if info.get('include_data'):
        lines.append(f'- **数据文件**: {info.get("data_count", 0)} 个 ({info.get("data_size_readable", "0 B")})')
    else:
        lines.append('- **数据文件**: 未备份')
    bot = info.get('bot_config', {})
    if bot.get('appid'):
        lines.extend(['', '## Bot 配置', f'- AppID: `{bot.get("appid", "")}`', f'- 平台: `{bot.get("platform", "未知")}`'])
    lines.extend(['', '---', '', '## 恢复方法', '',
        '1. 安装本插件到新框架', '2. 在 Web 面板进入「备份迁移」页面',
        '3. 上传此 ZIP 文件', '4. 点击「恢复备份」按钮', '', '---', '',
        f'*备份工具版本: v{info.get("version", "1.5")}*',
        f'*生成于 {info.get("created_at_readable", "未知")}*',
    ])
    return '\n'.join(lines)


def create_backup(include_config: bool = True, include_data: bool = True) -> Optional[str]:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"backup_{timestamp}.zip"
    zip_path = DATA_DIR / filename
    info = generate_backup_info(include_config, include_data)
    readme_content = generate_readme(info)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('backup_info.json', json.dumps(info, ensure_ascii=False, indent=2))
            zf.writestr('README.md', readme_content)
            if include_config and CONFIG_DIR.exists():
                for f in CONFIG_DIR.glob('*.yaml'):
                    zf.write(f, f"config/{f.name}")
                for f in CONFIG_DIR.glob('*.yml'):
                    zf.write(f, f"config/{f.name}")
            if include_data:
                data_root = PROJECT_ROOT / 'data'
                if data_root.exists():
                    for f in data_root.rglob('*'):
                        if f.is_file() and '备份工具' not in str(f):
                            arcname = f"data/{f.relative_to(data_root)}"
                            zf.write(f, arcname)
        log.info(f'✅ 备份创建成功: {filename} ({format_size(zip_path.stat().st_size)})')
        return filename
    except Exception as e:
        log.error(f'备份失败: {e}')
        if zip_path.exists():
            zip_path.unlink()
        return None


# ==================== 恢复功能 ====================


def restore_backup(zip_path: Path) -> Dict[str, Any]:
    result = {
        'success': False, 'restored_configs': [], 'restored_data': [],
        'skipped_files': [], 'errors': [], 'backup_info': {},
    }
    if not zip_path.exists():
        result['errors'].append(f"备份文件不存在: {zip_path}")
        return result

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            bad_file = zf.testzip()
            if bad_file:
                result['errors'].append(f"ZIP 文件损坏: {bad_file}")
                return result
            try:
                with zf.open('backup_info.json') as f:
                    result['backup_info'] = json.load(f)
            except Exception:
                pass

            for item in zf.namelist():
                if item.endswith('/'):
                    continue
                parts = item.replace('\\', '/').split('/')
                unsafe = False
                for part in parts:
                    if not part or '..' in part or part.startswith('/'):
                        unsafe = True
                        break
                if unsafe:
                    result['skipped_files'].append(item)
                    result['errors'].append(f"跳过不安全的路径: {item}")
                    continue

                try:
                    if item.startswith('config/'):
                        rel_path = Path(item[len('config/'):])
                        target_path = CONFIG_DIR / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(item) as src:
                            with open(target_path, 'wb') as dst:
                                while True:
                                    chunk = src.read(8192)
                                    if not chunk:
                                        break
                                    dst.write(chunk)
                        result['restored_configs'].append(str(rel_path))
                    elif item.startswith('data/'):
                        rel_path = Path(item[len('data/'):])
                        target_path = PROJECT_ROOT / 'data' / rel_path
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(item) as src:
                            with open(target_path, 'wb') as dst:
                                while True:
                                    chunk = src.read(8192)
                                    if not chunk:
                                        break
                                    dst.write(chunk)
                        result['restored_data'].append(str(rel_path))
                except Exception as e:
                    result['errors'].append(f"恢复 {item} 失败: {str(e)}")
                    log.warning(f"恢复文件失败 {item}: {e}")

            if result['restored_configs'] or result['restored_data']:
                result['success'] = True
                log.info(f'恢复成功: 配置={len(result["restored_configs"])}, 数据={len(result["restored_data"])}')
            elif result['errors']:
                result['success'] = False

    except zipfile.BadZipFile:
        result['errors'].append("无效的 ZIP 文件")
        log.error("无效的 ZIP 文件")
    except Exception as e:
        result['errors'].append(f"恢复过程出错: {str(e)}")
        log.error(f"恢复失败: {e}")
    return result


def parse_backup_info(zip_path: Path) -> Dict[str, Any]:
    info = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'backup_info.json' in zf.namelist():
                with zf.open('backup_info.json') as f:
                    info = json.load(f)
            elif 'README.md' in zf.namelist():
                with zf.open('README.md') as f:
                    content = f.read().decode('utf-8')
                    m = re.search(r'\*\*生成时间\*\*:\s*(.+)', content)
                    if m:
                        info['created_at_readable'] = m.group(1).strip()
                    m = re.search(r'-\s*\*\*配置文件\*\*:\s*(\d+)', content)
                    if m:
                        info['config_count'] = int(m.group(1))
                    m = re.search(r'-\s*\*\*数据文件\*\*:\s*(\d+)', content)
                    if m:
                        info['data_count'] = int(m.group(1))
            else:
                info['warning'] = '无法识别的备份文件格式'
    except Exception as e:
        log.error(f'解析备份信息失败: {e}')
        info['error'] = str(e)
    return info


# ==================== 备份列表管理 ====================


def get_backups_list() -> List[Dict[str, Any]]:
    backups = []
    if not DATA_DIR.exists():
        return backups
    for f in sorted(DATA_DIR.glob('backup_*.zip'), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            stat = f.stat()
            info = parse_backup_info(f)
            backups.append({
                'filename': f.name,
                'size': format_size(stat.st_size),
                'size_bytes': stat.st_size,
                'created_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'modified_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'info': info,
            })
        except Exception:
            continue
    return backups


def delete_backup_file(filename: str) -> Dict[str, Any]:
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return {'success': False, 'error': '非法文件名'}
    file_path = DATA_DIR / filename
    if not file_path.exists():
        return {'success': False, 'error': '文件不存在'}
    if not file_path.is_file():
        return {'success': False, 'error': '不是有效文件'}
    try:
        file_path.unlink()
        log.info(f'已删除备份: {filename}')
        return {'success': True, 'message': f'已删除 {filename}'}
    except PermissionError:
        log.error(f'权限不足，无法删除: {filename}')
        return {'success': False, 'error': '权限不足'}
    except Exception as e:
        log.error(f'删除失败: {e}')
        return {'success': False, 'error': str(e)}


# ==================== Web 路由 ====================
# ⚠️ 框架路由是精确匹配 (METHOD, path)，不支持路径参数 {param}
# 所有需要传文件名的操作都用 query 参数 ?fn=xxx

PAGE_PATH = '/api/ext/backup_manager'
STATS_PATH = '/api/ext/backup_manager/stats'
BACKUP_CREATE_PATH = '/api/ext/backup_manager/backup'
UPLOAD_PATH = '/api/ext/backup_manager/upload'
RESTORE_PATH = '/api/ext/backup_manager/restore'
BACKUPS_LIST_PATH = '/api/ext/backup_manager/backups'
DELETE_PATH = '/api/ext/backup_manager/delete'
DOWNLOAD_PATH = '/api/ext/backup_manager/download'
DISK_USAGE_PATH = '/api/ext/backup_manager/disk_usage'


@register_route('GET', PAGE_PATH, auth=False)
async def serve_page(request):
    html_path = PLUGIN_DIR / 'panel.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html; charset=utf-8')
    return web.Response(text='<p>页面文件不存在</p>', content_type='text/html; charset=utf-8')


@register_route('GET', STATS_PATH, auth=False)
async def api_stats(request):
    config_files = get_config_files()
    config_size = get_config_size()
    data_files = get_data_files()
    data_size = get_data_size()
    backup_count = len(list(DATA_DIR.glob('backup_*.zip')))
    disk_usage = get_disk_usage()

    return web.json_response({
        'backup_location': str(DATA_DIR),
        'config_count': len(config_files),
        'config_files': config_files,
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_files),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'backup_count': backup_count,
        'disk_usage': disk_usage,
    })


@register_route('POST', BACKUP_CREATE_PATH, auth=False)
async def api_create_backup(request):
    try:
        data = await request.json() if request.can_read_body else {}
        include_config = data.get('include_config', True)
        include_data = data.get('include_data', True)
        filename = create_backup(include_config, include_data)
        if filename:
            return web.json_response({'success': True, 'filename': filename})
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

        tmp_dir = DATA_DIR / 'temp'
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
            tmp_dir = DATA_DIR / 'temp'
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

    file_path = DATA_DIR / filename
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
    return web.json_response({'success': True, 'disk_usage': usage})


# ==================== 生命周期 ====================


@on_load
async def init():
    log.info('🔧 重要信息备份与迁移工具 v1.5 已加载')
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    html_path = PLUGIN_DIR / 'panel.html'
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
    log.info('✅ 备份工具面板已注册')


@on_unload
def cleanup():
    unregister_page('backup_manager')
    log.info('🔧 重要信息备份与迁移工具已卸载')
