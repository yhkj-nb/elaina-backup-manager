# plugins/备份工具/app/plugins_scan.py
"""插件扫描 (运行数据 + 源码与配置)

备份范围:
- 运行数据: ``plugins/<插件名>/data`` 下的文件 → ZIP 内 ``plugins/<插件名>/data/...``
- 源码配置: ``plugins/<插件名>`` 下除 data/ 以外的全部文件
            (``*.py`` 源码 + ``app/panel.html``、``*.json`` / ``*.yaml`` / ``*.md`` 等自带配置与资源)
            → ZIP 内 ``plugins/<插件名>/...``

恢复时按同一路径映射回项目 plugins 目录。

安全与排除策略 (统一由 scan_utils 提供):
- 包含备份工具自身 (v2.7): 源码 + data/ 下的配置等文件都会打包, 但跳过它
  生成的 backup_*.zip / 临时文件, 避免历史备份被递归打包
- 排除缓存 / 构建产物 / 临时文件 / 隐藏文件 / 日志
- 排除自定义备份输出目录 (backup_dir 落在插件目录内时)
- 扫描源码时不进入 data/ 子树, 大体积运行数据不会被遍历

源码与运行数据使用独立开关: 只迁移数据时可关闭源码,
避免用备份覆盖目标机器上已更新的插件代码。
"""

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import PLUGIN_DIR, PROJECT_ROOT, get_backup_dir
from .scan_utils import EXCLUDE_DIR_NAMES, iter_payload_files, total_size
from .utils import format_size, log

# 备份 ZIP 内插件数据的顶层目录名
PLUGINS_DIR_NAME = 'plugins'
DATA_DIR_NAME = 'data'

# 源码与配置备份: 收插件目录下除 data/ 以外的全部文件;
# pyc / 日志 / 缓存 / 隐藏文件等排除规则统一由 scan_utils 处理。
# None = 不限后缀 —— 只收 *.py 会漏掉 app/panel.html 等插件自带配置与资源。
SOURCE_SUFFIXES: Optional[set] = None

# 备份工具自身 data/ 下由本插件生成的文件后缀 (备份包 / 上传临时文件)。
# 自身现在也参与备份, 必须跳过这些产物, 否则历史备份会被递归打进新备份。
SELF_ARTIFACT_SUFFIXES = {'.zip', '.part'}


# ==================== 基础工具 ====================


def get_plugins_root() -> Path:
    """项目 plugins/ 根目录。"""
    return PROJECT_ROOT / PLUGINS_DIR_NAME


def _is_self(plugin_dir: Path) -> bool:
    """是否为备份工具自身目录。"""
    try:
        return plugin_dir.resolve() == PLUGIN_DIR.resolve()
    except OSError:
        return plugin_dir.name == PLUGIN_DIR.name


def _exclude_dir() -> Optional[Path]:
    """当前配置的备份输出目录 (可能落在插件目录内, 必须排除)。"""
    try:
        return get_backup_dir()
    except Exception:
        return None


def _is_self_artifact(path: Path) -> bool:
    """备份工具自身 data/ 下由本插件生成的备份包 / 临时文件。"""
    return path.suffix.lower() in SELF_ARTIFACT_SUFFIXES


def _data_exclude_dir(plugin_dir: Path) -> Optional[Path]:
    """扫描运行数据时需要整体排除的目录。

    备份输出目录默认就是备份工具自己的 data/ —— 直接整目录排除会让插件自身的
    数据永远备份不到, 因此这种情况下改为按文件名跳过历史备份包 (_is_self_artifact)。
    """
    exclude = _exclude_dir()
    if exclude is None or not _is_self(plugin_dir):
        return exclude
    try:
        if exclude.resolve() == (plugin_dir / DATA_DIR_NAME).resolve():
            return None
    except OSError:
        pass
    return exclude


# ==================== 扫描 ====================


def discover_plugins() -> List[Path]:
    """列出可参与备份的插件目录 (含备份工具自身, 已排除隐藏目录与缓存目录)。"""
    root = get_plugins_root()
    if not root.is_dir():
        return []
    plugins: List[Path] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name.startswith('.') or child.name in EXCLUDE_DIR_NAMES:
            continue
        plugins.append(child)
    return plugins


def _plugin_data_files(plugin_dir: Path) -> List[Path]:
    """收集单个插件 data/ 下待备份的运行数据。

    备份工具自身也参与备份 (含 data/config.yaml 等配置), 但会跳过它生成的
    备份包与上传临时文件, 避免历史备份被递归打包。
    """
    is_self = _is_self(plugin_dir)
    return iter_payload_files(
        plugin_dir / DATA_DIR_NAME,
        exclude_dir=_data_exclude_dir(plugin_dir),
        skip_files=_is_self_artifact if is_self else None,
    )


def _plugin_source_files(plugin_dir: Path) -> List[Path]:
    """收集单个插件待备份的源码与配置文件 (跳过 data/ 子树与缓存目录)。"""
    return iter_payload_files(
        plugin_dir,
        skip_top_dirs=(DATA_DIR_NAME,),
        exclude_dir=_exclude_dir(),
        suffixes=SOURCE_SUFFIXES,
    )


def get_plugin_inventory() -> List[Dict[str, Any]]:
    """返回所有插件的统计数据 (数据文件 + 源码文件)。"""
    inventory: List[Dict[str, Any]] = []
    for plugin_dir in discover_plugins():
        files = _plugin_data_files(plugin_dir)
        src_files = _plugin_source_files(plugin_dir)
        size = total_size(files)
        src_size = total_size(src_files)
        inventory.append({
            'name': plugin_dir.name,
            'path': str(plugin_dir),
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


def get_plugin_summary(inventory: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """插件汇总 (运行数据), 供 Web 统计与命令回复使用。

    可传入已扫描好的 inventory, 避免与 get_plugin_source_summary 重复扫盘。
    """
    inventory = get_plugin_inventory() if inventory is None else inventory
    total_files = sum(item['file_count'] for item in inventory)
    total_size_bytes = sum(item['size'] for item in inventory)
    return {
        'plugin_count': len(inventory),
        'plugin_with_data_count': sum(1 for item in inventory if item['has_data']),
        'plugins': inventory,
        'file_count': total_files,
        'size': total_size_bytes,
        'size_readable': format_size(total_size_bytes),
    }


def get_plugin_source_summary(inventory: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """插件源码与配置汇总, 供 Web 统计与命令回复使用。"""
    inventory = get_plugin_inventory() if inventory is None else inventory
    src_files = sum(item['src_file_count'] for item in inventory)
    src_size = sum(item['src_size'] for item in inventory)
    return {
        'plugin_count': len(inventory),
        'plugin_with_src_count': sum(1 for item in inventory if item['has_src']),
        'file_count': src_files,
        'size': src_size,
        'size_readable': format_size(src_size),
    }


# ==================== 构建备份条目 ====================


def resolve_selected_plugins(selected: Optional[Iterable[str]]) -> List[Path]:
    """把前端/命令传入的插件名解析为目录列表。

    ``selected`` 为 None 表示全选; 传入未知插件名会被跳过并记录日志。
    """
    available = {p.name: p for p in discover_plugins()}
    if selected is None:
        return list(available.values())

    result: List[Path] = []
    for name in selected:
        if not isinstance(name, str):
            continue
        name = name.strip()
        plugin_dir = available.get(name)
        if plugin_dir is None:
            log.warning(f'跳过未知或不可备份的插件: {name}')
            continue
        result.append(plugin_dir)
    return result


def _build_entries(
    selected: Optional[Iterable[str]],
    collector,
) -> List[Tuple[Path, str]]:
    """按插件把 collector 收集到的文件映射为 (源文件, ZIP 内路径)。"""
    entries: List[Tuple[Path, str]] = []
    for plugin_dir in resolve_selected_plugins(selected):
        for f in collector(plugin_dir):
            try:
                rel = f.relative_to(plugin_dir)
            except ValueError:
                continue
            arcname = (Path(PLUGINS_DIR_NAME) / plugin_dir.name / rel).as_posix()
            entries.append((f, arcname))
    return entries


def iter_plugin_backup_entries(
    selected: Optional[Iterable[str]] = None,
) -> List[Tuple[Path, str]]:
    """插件运行数据条目: ``plugins/<插件名>/data/xxx``。"""
    return _build_entries(selected, _plugin_data_files)


def iter_plugin_source_entries(
    selected: Optional[Iterable[str]] = None,
) -> List[Tuple[Path, str]]:
    """插件源码与配置条目: ``plugins/<插件名>/main.py``、``app/panel.html`` 等。"""
    return _build_entries(selected, _plugin_source_files)
