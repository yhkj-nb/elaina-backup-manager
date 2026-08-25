# plugins/备份工具/app/utils.py
"""通用工具函数

日志统一用框架的 ctx.log (ElainaBot v2 插件开发文档 §9),
但为了让 utils 在框架 ctx 未就绪时 (如单测 / 离线 import) 也能工作,
这里提供一个 lazy log: ctx 可用时代理到 ctx.log, 否则回退到标准 logging。
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Any

from .constants import CONFIG_DIR, PROJECT_ROOT, DATA_DIR


class _LogProxy:
    def _ctx(self):
        try:
            from core.plugin.context import ctx
            return ctx if getattr(ctx, 'log', None) else None
        except Exception:
            return None

    def _fallback(self) -> logging.Logger:
        return logging.getLogger('备份工具')

    def info(self, *a, **kw):
        c = self._ctx()
        if c:
            c.log.info(*a, **kw)
        else:
            self._fallback().info(*a, **kw)

    def warning(self, *a, **kw):
        c = self._ctx()
        if c:
            c.log.warning(*a, **kw)
        else:
            self._fallback().warning(*a, **kw)

    def error(self, *a, **kw):
        c = self._ctx()
        if c:
            c.log.error(*a, **kw)
        else:
            self._fallback().error(*a, **kw)

    def exception(self, *a, **kw):
        c = self._ctx()
        if c:
            c.log.exception(*a, **kw)
        else:
            self._fallback().exception(*a, **kw)

    def debug(self, *a, **kw):
        c = self._ctx()
        if c:
            c.log.debug(*a, **kw)
        else:
            self._fallback().debug(*a, **kw)


log = _LogProxy()


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
    for f in get_data_files():
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def get_disk_usage() -> Dict[str, Any]:
    """返回工作目录所在磁盘的总空间/可用空间 (字节)."""
    target = PROJECT_ROOT
    if not target.exists():
        target = Path.cwd()
    try:
        st = os.statvfs(str(target))
        total = st.f_frsize * st.f_blocks
        free = st.f_frsize * st.f_bavail
        used = total - free
        return {
            'total': total,
            'used': used,
            'free': free,
            'used_pct': round(used / total * 100, 1) if total else 0.0,
        }
    except Exception:
        return {'total': 0, 'used': 0, 'free': 0, 'used_pct': 0.0}
