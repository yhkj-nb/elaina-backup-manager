# plugins/备份工具/app/utils.py
"""通用工具函数"""

import os
from pathlib import Path
from typing import Dict, List, Any

from core.base.logger import get_logger, PLUGIN

from .constants import CONFIG_DIR, PROJECT_ROOT, DATA_DIR

log = get_logger(PLUGIN, '备份工具')


# ==================== 格式化 ====================


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


# ==================== 文件扫描 ====================


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
