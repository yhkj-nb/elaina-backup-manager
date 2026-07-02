# plugins/backup_manager/main.py
"""
重要信息备份与迁移工具

功能：
- 一键备份：备份 Bot 配置、框架配置、插件数据
- 完整恢复：上传ZIP后自动恢复所有配置和数据
- 配置迁移：QQ机器人配置自动填充，无需手动填写
- 下载备份文件到本地
- 删除旧备份

仓库地址: https://github.com/yhkj-nb/elaina-backup-manager

作者: yhkj-nb (云痕科技)
版本: 1.0.0
"""

import json
import zipfile
import yaml
import shutil
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from aiohttp import web
from aiohttp.web_fileresponse import FileResponse
from aiohttp.web_request import Request

from core.plugin.decorators import handler, on_load, on_unload
from core.plugin.web_pages import register_page, unregister_page, register_route
from core.base.logger import get_logger, PLUGIN
from core.base.config import cfg

# ==================== 插件元数据 ====================

__plugin_meta__ = {
    'name': '重要信息备份与迁移工具',
    'author': 'yhkj-nb (云痕科技)',
    'description': '一键备份和迁移 Bot 配置、框架配置、插件数据',
    'version': '1.0.0',
    'license': 'MIT',
    'github': 'https://github.com/yhkj-nb/elaina-backup-manager',
    'homepage': 'https://github.com/yhkj-nb/elaina-backup-manager',
}

# ==================== 日志 ====================

log = get_logger(PLUGIN, '备份工具')

# ==================== 路径常量 ====================

PLUGIN_DIR = Path(__file__).parent
PROJECT_ROOT = PLUGIN_DIR.parent.parent
CONFIG_DIR = PROJECT_ROOT / 'config'
DATA_DIR = PROJECT_ROOT / 'data'
BACKUP_DIR = PLUGIN_DIR / 'data' / 'backups'
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 读取 HTML ====================

def get_html_content() -> str:
    """读取同目录下的 plane.html"""
    html_path = PLUGIN_DIR / 'plane.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    return _get_fallback_html()

def _get_fallback_html() -> str:
    """备用HTML"""
    return """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>备份工具</title></head>
<body>
<h1>重要信息备份与迁移工具</h1>
<p>请确保 plane.html 文件存在</p>
<p>备份文件存放在: data/backups/</p>
</body>
</html>"""

# ==================== 核心功能 ====================

def get_backups_list() -> List[Dict[str, Any]]:
    """获取所有备份文件列表"""
    backups = []
    if not BACKUP_DIR.exists():
        return backups
    
    for f in sorted(BACKUP_DIR.glob('*.zip'), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        info = get_backup_info(f)
        backups.append({
            'filename': f.name,
            'size': format_size(stat.st_size),
            'size_bytes': stat.st_size,
            'created_at': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            'info': info,
            'path': str(f.absolute())
        })
    return backups

def get_backup_info(zip_path: Path) -> Dict[str, Any]:
    """读取备份中的 info.json"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'backup_info.json' in zf.namelist():
                with zf.open('backup_info.json') as f:
                    return json.load(f)
    except:
        pass
    return {}

def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def generate_backup_info() -> Dict[str, Any]:
    """生成备份信息"""
    # 读取 bot.yaml 配置
    bot_config = {}
    bot_yaml = CONFIG_DIR / 'bot.yaml'
    if bot_yaml.exists():
        try:
            with open(bot_yaml, 'r', encoding='utf-8') as f:
                bot_config = yaml.safe_load(f) or {}
        except:
            pass
    
    # 获取配置文件列表
    config_files = get_config_files()
    
    # 获取数据目录大小
    data_size = 0
    if DATA_DIR.exists():
        for f in DATA_DIR.rglob('*'):
            if f.is_file():
                data_size += f.stat().st_size
    
    return {
        'version': '1.0.0',
        'created_at': datetime.now().isoformat(),
        'created_at_readable': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bot_config': {
            'appid': bot_config.get('appid', ''),
            'secret': bot_config.get('secret', ''),
            'token': bot_config.get('token', ''),
            'platform': bot_config.get('platform', ''),
            'sandbox': bot_config.get('sandbox', True),
        },
        'has_config': bot_yaml.exists(),
        'config_files': config_files,
        'data_count': get_data_file_count(),
        'data_size': format_size(data_size),
        'backup_location': str(BACKUP_DIR.absolute())
    }

def get_config_files() -> List[str]:
    """获取配置文件列表"""
    files = []
    if CONFIG_DIR.exists():
        for f in CONFIG_DIR.glob('*.yaml'):
            files.append(f.name)
        for f in CONFIG_DIR.glob('*.yml'):
            files.append(f.name)
    return files

def get_data_file_count() -> int:
    """获取数据文件数量"""
    count = 0
    if DATA_DIR.exists():
        for f in DATA_DIR.rglob('*'):
            if f.is_file() and 'backup_manager' not in str(f):
                count += 1
    return count

def generate_readme(info: Dict[str, Any]) -> str:
    """生成 README.md 说明文件"""
    lines = [
        '# ElainaBot 重要信息备份说明',
        '',
        f'**生成时间**: {info.get("created_at_readable", "未知")}',
        '',
        '---',
        '',
        '## 📦 备份内容',
        '',
        f'- **配置文件**: {len(info.get("config_files", []))} 个',
        f'- **数据文件**: {info.get("data_count", 0)} 个',
        f'- **数据大小**: {info.get("data_size", "0 B")}',
        '',
        '### 配置文件',
        '',
    ]
    
    config_files = info.get('config_files', [])
    if config_files:
        for f in config_files:
            lines.append(f'- `{f}`')
    else:
        lines.append('> 暂无配置文件')
    
    bot = info.get('bot_config', {})
    if bot.get('appid'):
        lines.extend([
            '',
            '### 🤖 Bot 配置',
            '',
            f'- **AppID**: `{bot.get("appid", "")}`',
            f'- **平台**: `{bot.get("platform", "未知")}`',
            f'- **沙盒模式**: `{"是" if bot.get("sandbox") else "否"}`',
        ])
    
    lines.extend([
        '',
        '---',
        '',
        '## 📥 恢复方法',
        '',
        '1. 安装 `backup_manager` 插件到新框架',
        '2. 在 Web 面板进入「备份迁移」页面',
        '3. 上传此 ZIP 文件',
        '4. 点击「恢复备份」按钮',
        '5. 框架将自动恢复所有配置和数据',
        '',
        '---',
        '',
        f'*备份工具: [elaina-backup-manager](https://github.com/yhkj-nb/elaina-backup-manager)*',
        f'*生成于 {info.get("created_at_readable", "未知")}*',
    ])
    
    return '\n'.join(lines)

def create_backup() -> Optional[str]:
    """创建备份ZIP文件（包含 README.md 和 info.json）"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"elaina_backup_{timestamp}.zip"
    zip_path = BACKUP_DIR / filename
    
    # 生成备份信息
    info = generate_backup_info()
    readme_content = generate_readme(info)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 写入备份信息
        zf.writestr('backup_info.json', json.dumps(info, ensure_ascii=False, indent=2))
        zf.writestr('README.md', readme_content.encode('utf-8'))
        
        # 备份配置文件
        if CONFIG_DIR.exists():
            for f in CONFIG_DIR.glob('*.yaml'):
                arcname = f"config/{f.name}"
                zf.write(f, arcname)
            for f in CONFIG_DIR.glob('*.yml'):
                arcname = f"config/{f.name}"
                zf.write(f, arcname)
        
        # 备份 data 目录（排除 backup_manager 自身）
        if DATA_DIR.exists():
            for f in DATA_DIR.rglob('*'):
                if f.is_file():
                    if 'backup_manager' in str(f):
                        continue
                    arcname = f"data/{f.relative_to(DATA_DIR)}"
                    zf.write(f, arcname)
    
    log.info(f'✅ 备份创建成功: {filename} (存放于 {BACKUP_DIR})')
    return filename

def restore_backup(zip_path: Path) -> Dict[str, Any]:
    """恢复备份"""
    result = {
        'success': True,
        'restored_configs': [],
        'restored_data': [],
        'errors': [],
        'bot_config': {},
    }
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # 读取备份信息
            if 'backup_info.json' in zf.namelist():
                with zf.open('backup_info.json') as f:
                    info = json.load(f)
                    result['bot_config'] = info.get('bot_config', {})
            
            # 恢复 config
            for item in zf.namelist():
                if item.startswith('config/') and not item.endswith('/'):
                    rel_path = Path(item).relative_to('config')
                    target_path = CONFIG_DIR / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(item) as src:
                        with open(target_path, 'wb') as dst:
                            dst.write(src.read())
                    result['restored_configs'].append(str(rel_path))
            
            # 恢复 data
            for item in zf.namelist():
                if item.startswith('data/') and not item.endswith('/'):
                    rel_path = Path(item).relative_to('data')
                    target_path = DATA_DIR / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(item) as src:
                        with open(target_path, 'wb') as dst:
                            dst.write(src.read())
                    result['restored_data'].append(str(rel_path))
    
    except Exception as e:
        result['success'] = False
        result['errors'].append(str(e))
    
    return result

def parse_backup_info(zip_path: Path) -> Dict[str, Any]:
    """解析备份信息（不恢复）"""
    info = {}
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if 'backup_info.json' in zf.namelist():
                with zf.open('backup_info.json') as f:
                    info = json.load(f)
            elif 'README.md' in zf.namelist():
                with zf.open('README.md') as f:
                    content = f.read().decode('utf-8')
                    import re
                    time_match = re.search(r'\*\*生成时间\*\*:\s*(.+)', content)
                    if time_match:
                        info['created_at_readable'] = time_match.group(1).strip()
                    config_match = re.search(r'-\s*\*\*配置文件\*\*:\s*(\d+)', content)
                    if config_match:
                        info['config_count'] = int(config_match.group(1))
                    data_match = re.search(r'-\s*\*\*数据文件\*\*:\s*(\d+)', content)
                    if data_match:
                        info['data_count'] = int(data_match.group(1))
            
            # 如果 info 为空，尝试从文件列表推断
            if not info:
                file_list = zf.namelist()
                config_files = []
                data_files = []
                for f in file_list:
                    if f.startswith('config/') and (f.endswith('.yaml') or f.endswith('.yml')):
                        config_files.append(f.split('/')[-1])
                    elif f.startswith('data/') and not f.endswith('/'):
                        data_files.append(f)
                
                info['config_files'] = config_files
                info['config_count'] = len(config_files)
                info['data_count'] = len(data_files)
                info['created_at_readable'] = datetime.fromtimestamp(
                    os.path.getmtime(zip_path)
                ).strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        log.error(f'解析备份信息失败: {e}')
        info['created_at_readable'] = '未知'
        info['error'] = str(e)
    
    return info

def delete_backup_file(filename: str) -> bool:
    """删除备份文件"""
    file_path = BACKUP_DIR / filename
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        log.info(f'🗑️ 已删除备份: {filename}')
        return True
    return False

# ==================== Web 路由 ====================

@register_route('GET', '/api/ext/backup_manager', auth=False)
async def serve_page(request):
    """提供 HTML 页面"""
    html = get_html_content()
    return web.Response(text=html, content_type='text/html; charset=utf-8')

@register_route('GET', '/api/ext/backup_manager/backups', auth=False)
async def api_backups(request):
    """获取备份列表"""
    return web.json_response({'backups': get_backups_list()})

@register_route('GET', '/api/ext/backup_manager/stats', auth=False)
async def api_stats(request):
    """获取统计信息"""
    backups = get_backups_list()
    total_size = sum(b.get('size_bytes', 0) for b in backups)
    config_files = get_config_files()
    data_count = get_data_file_count()
    return web.json_response({
        'backup_count': len(backups),
        'backup_size': format_size(total_size),
        'backup_location': str(BACKUP_DIR.absolute()),
        'config_count': len(config_files),
        'config_files': config_files,
        'data_count': data_count,
    })

@register_route('POST', '/api/ext/backup_manager/backup', auth=False)
async def api_backup(request):
    """执行备份"""
    try:
        filename = create_backup()
        if filename:
            return web.json_response({'success': True, 'filename': filename})
        return web.json_response({'success': False, 'error': '备份失败'})
    except Exception as e:
        log.error(f'备份失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})

@register_route('DELETE', '/api/ext/backup_manager/delete/{filename}', auth=False)
async def api_delete_backup(request):
    """删除备份文件"""
    filename = request.match_info.get('filename')
    if not filename:
        return web.json_response({'success': False, 'error': '缺少文件名'})
    if '..' in filename or '/' in filename:
        return web.json_response({'success': False, 'error': '非法文件名'})
    if delete_backup_file(filename):
        return web.json_response({'success': True})
    return web.json_response({'success': False, 'error': '文件不存在'})

@register_route('GET', '/api/ext/backup_manager/download/{filename}', auth=False)
async def api_download_backup(request):
    """下载备份文件"""
    filename = request.match_info.get('filename')
    if not filename:
        return web.json_response({'success': False, 'error': '缺少文件名'})
    
    if '..' in filename or '/' in filename:
        return web.json_response({'success': False, 'error': '非法文件名'})
    
    if not filename.endswith('.zip'):
        return web.json_response({'success': False, 'error': '仅支持 ZIP 文件'})
    
    file_path = BACKUP_DIR / filename
    if not file_path.exists():
        return web.json_response({'success': False, 'error': f'文件不存在: {filename}'})
    
    return web.FileResponse(
        path=str(file_path),
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': 'application/zip'
        }
    )

@register_route('POST', '/api/ext/backup_manager/upload', auth=False)
async def api_upload_backup(request: Request):
    """上传并解析备份文件"""
    try:
        content_length = request.headers.get('Content-Length')
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            if size_mb > 500:
                return web.json_response({
                    'success': False, 
                    'error': f'文件过大 ({size_mb:.1f}MB)，请上传小于 500MB 的文件'
                })
        
        data = await request.post()
        if 'file' not in data:
            return web.json_response({'success': False, 'error': '请选择文件'})
        
        file_data = data['file']
        if not file_data.filename.endswith('.zip'):
            return web.json_response({'success': False, 'error': '仅支持 ZIP 文件'})
        
        content = file_data.file.read()
        if len(content) == 0:
            return web.json_response({'success': False, 'error': '文件为空'})
        
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        
        try:
            info = parse_backup_info(tmp_path)
            size = tmp_path.stat().st_size
            info['file_size'] = format_size(size)
            info['file_size_bytes'] = size
            
            return web.json_response({
                'success': True,
                'filename': file_data.filename,
                'size': format_size(size),
                'info': info,
            })
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
                
    except Exception as e:
        log.error(f'上传失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})

@register_route('POST', '/api/ext/backup_manager/restore', auth=False)
async def api_restore_backup(request: Request):
    """恢复备份"""
    try:
        data = await request.post()
        if 'file' not in data:
            return web.json_response({'success': False, 'error': '请选择文件'})
        
        file_data = data['file']
        if not file_data.filename.endswith('.zip'):
            return web.json_response({'success': False, 'error': '仅支持 ZIP 文件'})
        
        content = file_data.file.read()
        if len(content) == 0:
            return web.json_response({'success': False, 'error': '文件为空'})
        
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        
        try:
            result = restore_backup(tmp_path)
            if result['success']:
                log.info(f'恢复成功: {result["restored_configs"]}')
                return web.json_response({
                    'success': True,
                    'message': '恢复成功！',
                    'result': result
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': '恢复失败',
                    'errors': result.get('errors', [])
                })
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
                
    except Exception as e:
        log.error(f'恢复失败: {e}')
        return web.json_response({'success': False, 'error': str(e)})

# ==================== 生命周期 ====================

@on_load
async def init():
    """插件加载时注册 Web 页面"""
    log.info('🔧 重要信息备份与迁移工具已加载')
    log.info('📦 仓库地址: https://github.com/yhkj-nb/elaina-backup-manager')
    log.info(f'📁 备份文件存放目录: {BACKUP_DIR}')
    
    html_content = get_html_content()
    register_page(
        key='backup_manager',
        label='🔧 备份迁移',
        source='plugin',
        source_name='backup_manager',
        html=html_content,
        icon='settings',
    )

@on_unload
def cleanup():
    """插件卸载时清理"""
    unregister_page('backup_manager')
    log.info('🔧 重要信息备份与迁移工具已卸载')