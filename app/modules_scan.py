# plugins/备份工具/app/modules_scan.py
"""框架模块扫描 (运行数据 + 源码与配置)

备份范围:
- 运行数据: ``modules/<模块名>/data`` 下的文件 → ZIP 内 ``modules/<模块名>/data/...``
- 启用状态: ``modules/modules_enabled.json`` → ZIP 内 ``modules/modules_enabled.json``
- 源码配置: ``modules/<模块名>`` 下除 data/ 以外的全部文件
            (``*.py`` 源码 + ``*.json`` / ``*.yaml`` / ``*.html`` 等自带配置与资源)
            → ZIP 内 ``modules/<模块名>/...``

恢复时按同一路径映射回项目 modules 目录。

安全与排除策略 (统一由 scan_utils 提供):
- 排除缓存 / 构建产物 / 临时文件 / 隐藏文件 / 日志
- 排除自定义备份输出目录 (backup_dir 落在模块目录内时)
- 扫描源码时不进入 data/ 子树

源码与运行数据使用独立开关: 只迁移数据时可关闭源码,
避免用备份覆盖目标机器上已更新的模块代码。
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import PROJECT_ROOT, get_backup_dir
from .scan_utils import EXCLUDE_DIR_NAMES, iter_payload_files, total_size
from .utils import format_size, log

# 备份 ZIP 内模块数据的顶层目录名
MODULES_DIR_NAME = 'modules'
DATA_DIR_NAME = 'data'

# 模块根目录下的启用状态文件 (小体积, 但决定模块开关, 值得迁移)
ENABLED_FILE_NAME = 'modules_enabled.json'

# 源码与配置备份: 收模块目录下除 data/ 以外的全部文件 (None = 不限后缀),
# pyc / 日志 / 缓存 / 隐藏文件等排除规则统一由 scan_utils 处理。
SOURCE_SUFFIXES: Optional[set] = None


# ==================== 基础工具 ====================


def get_modules_root() -> Path:
    """项目 modules/ 根目录。"""
    return PROJECT_ROOT / MODULES_DIR_NAME


def _exclude_dir() -> Optional[Path]:
    """当前配置的备份输出目录 (可能落在模块目录内, 必须排除)。"""
    try:
        return get_backup_dir()
    except Exception:
        return None


# ==================== 扫描 ====================


def discover_modules() -> List[Path]:
    """列出可参与备份的模块目录 (已排除隐藏目录与缓存目录)。"""
    root = get_modules_root()
    if not root.is_dir():
        return []
    modules: List[Path] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith('.') or child.name in EXCLUDE_DIR_NAMES:
            continue
        modules.append(child)
    return modules


def _module_data_files(module_dir: Path) -> List[Path]:
    """收集单个模块 data/ 下待备份的运行数据。"""
    return iter_payload_files(
        module_dir / DATA_DIR_NAME,
        exclude_dir=_exclude_dir(),
    )


def _module_source_files(module_dir: Path) -> List[Path]:
    """收集单个模块待备份的源码与配置文件 (跳过 data/ 子树与缓存目录)。"""
    return iter_payload_files(
        module_dir,
        skip_top_dirs=(DATA_DIR_NAME,),
        exclude_dir=_exclude_dir(),
        suffixes=SOURCE_SUFFIXES,
    )


def get_module_inventory() -> List[Dict[str, Any]]:
    """返回所有模块的统计数据 (数据文件 + 源码文件)。"""
    inventory: List[Dict[str, Any]] = []
    for module_dir in discover_modules():
        files = _module_data_files(module_dir)
        src_files = _module_source_files(module_dir)
        size = total_size(files)
        src_size = total_size(src_files)
        inventory.append({
            'name': module_dir.name,
            'path': str(module_dir),
            'has_data': bool(files),
            'file_count': len(files),
            'size': size,
            'size_readable': format_size(size),
            'has_src': bool(src_files),
            'src_file_count': len(src_files),
            'src_size': src_size,
            'src_size_readable': format_size(src_size),
        })
    return inventory


def _enabled_file() -> Optional[Path]:
    """模块启用状态文件 (不存在则不参与备份)。"""
    path = get_modules_root() / ENABLED_FILE_NAME
    return path if path.is_file() else None


def get_module_summary(inventory: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """模块数据汇总, 供 Web 统计与命令回复使用。"""
    inventory = get_module_inventory() if inventory is None else inventory
    total_files = sum(item['file_count'] for item in inventory)
    total_size_bytes = sum(item['size'] for item in inventory)
    enabled = _enabled_file()
    if enabled is not None:
        total_files += 1
        total_size_bytes += enabled.stat().st_size
    return {
        'module_count': len(inventory),
        'module_with_data_count': sum(1 for item in inventory if item['has_data']),
        'modules': inventory,
        'file_count': total_files,
        'size': total_size_bytes,
        'size_readable': format_size(total_size_bytes),
        'has_enabled_file': enabled is not None,
    }


def get_module_source_summary(inventory: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """模块源码与配置汇总, 供 Web 统计与命令回复使用。"""
    inventory = get_module_inventory() if inventory is None else inventory
    src_files = sum(item['src_file_count'] for item in inventory)
    src_size = sum(item['src_size'] for item in inventory)
    return {
        'module_count': len(inventory),
        'module_with_src_count': sum(1 for item in inventory if item['has_src']),
        'file_count': src_files,
        'size': src_size,
        'size_readable': format_size(src_size),
    }


# ==================== 构建备份条目 ====================


def resolve_selected_modules(selected: Optional[Iterable[str]]) -> List[Path]:
    """把前端/命令传入的模块名解析为目录列表。

    ``selected`` 为 None 表示全选; 传入未知模块名会被跳过并记录日志。
    """
    available = {p.name: p for p in discover_modules()}
    if selected is None:
        return list(available.values())

    result: List[Path] = []
    for name in selected:
        if not isinstance(name, str):
            continue
        name = name.strip()
        module_dir = available.get(name)
        if module_dir is None:
            log.warning(f'跳过未知或不可备份的模块: {name}')
            continue
        result.append(module_dir)
    return result


def _build_entries(
    selected: Optional[Iterable[str]],
    collector,
) -> List[Tuple[Path, str]]:
    """按模块把 collector 收集到的文件映射为 (源文件, ZIP 内路径)。"""
    entries: List[Tuple[Path, str]] = []
    for module_dir in resolve_selected_modules(selected):
        for f in collector(module_dir):
            try:
                rel = f.relative_to(module_dir)
            except ValueError:
                continue
            arcname = (Path(MODULES_DIR_NAME) / module_dir.name / rel).as_posix()
            entries.append((f, arcname))
    return entries


def iter_module_backup_entries(
    selected: Optional[Iterable[str]] = None,
) -> List[Tuple[Path, str]]:
    """模块运行数据条目 (含 modules_enabled.json 启用状态)。"""
    entries = _build_entries(selected, _module_data_files)

    # 启用状态文件只在「全选」或明确勾选了任一模块时随备份一起迁移
    enabled = _enabled_file()
    if enabled is not None and (selected is None or entries):
        entries.append((enabled, f'{MODULES_DIR_NAME}/{ENABLED_FILE_NAME}'))
    return entries


def iter_module_source_entries(
    selected: Optional[Iterable[str]] = None,
) -> List[Tuple[Path, str]]:
    """模块源码与配置条目: ``modules/<模块名>/main.py`` 等 (含非 .py 配置/资源)。"""
    return _build_entries(selected, _module_source_files)
