# plugins/备份工具/app/backup_list.py
"""本地备份列表管理"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from .constants import DATA_DIR
from .utils import log, format_size
from .restore import parse_backup_info


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
