# plugins/备份工具/app/backup.py
"""备份创建

统一条目模型 (v2.4 重构):
    所有备份内容都被归一成 ``(源文件 Path, ZIP 内路径 str)``, 因此
    扫描一次 → 去重排序 → 统一统计 → 单次写入, 不再为「生成元数据」和「写 ZIP」各扫一遍。

备份内容:
- ``config/*.yaml|yml``            框架配置
- ``data/**``                      项目数据 (排除备份输出目录自身)
- ``plugins/<名>/data/**``         插件运行数据 (含备份工具自身 data/, 跳过其备份包)
- ``plugins/<名>/**`` (除 data/)   插件源码与自带配置/资源 (*.py + panel.html/json/yaml 等)
- ``modules/<名>/data/**``         模块运行数据 + ``modules/modules_enabled.json``
- ``modules/<名>/**`` (除 data/)   模块源码与自带配置/资源

相对旧版的优化:
- 配置 / 数据 / 插件 / 模块共用同一套 Entry 结构, 删掉 _plugin_stats / _module_stats 两份重复聚合,
  统一由 _group_stats / _entries_size 处理
- 同一份扫描结果同时供 backup_info.json、README 与 ZIP 写入使用
- 写入前按 ZIP 内路径去重并排序, 既避免重复成员, 也让备份内容稳定可 diff
- 遍历时直接剪掉备份输出目录 (里面可能有几百 MB 历史备份), 不再逐个文件 stat 后再过滤
- 单个文件写入失败只跳过该文件并记日志, 不再让整次备份失败
"""

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import CONFIG_DIR, PROJECT_ROOT, get_backup_dir
from .modules_scan import iter_module_backup_entries, iter_module_source_entries
from .plugins_scan import iter_plugin_backup_entries, iter_plugin_source_entries
from .scan_utils import is_inside, total_size
from .utils import format_size, log

# (源文件, ZIP 内相对路径)
Entry = Tuple[Path, str]

BACKUP_VERSION = '2.7'
INFO_FILENAME = 'backup_info.json'
README_FILENAME = 'README.md'


# ==================== 扫描 ====================


def _exclude_dir() -> Optional[Path]:
    """备份输出目录 (写入新备份前必须排除, 否则会递归打包历史备份)。"""
    try:
        return get_backup_dir()
    except Exception:
        return None


def _scan_config_entries(include_config: bool = True) -> List[Entry]:
    """config/ 下的 YAML 配置条目。"""
    if not include_config or not CONFIG_DIR.is_dir():
        return []
    entries: List[Entry] = []
    for pattern in ('*.yaml', '*.yml'):
        for f in sorted(CONFIG_DIR.glob(pattern)):
            if f.is_file():
                entries.append((f, f'config/{f.name}'))
    return entries


def _scan_data_entries(include_data: bool = True) -> List[Entry]:
    """项目 data/ 条目 (排除备份输出目录, 其余文件原样备份)。"""
    if not include_data:
        return []
    data_root = PROJECT_ROOT / 'data'
    if not data_root.is_dir():
        return []

    exclude_dir = _exclude_dir()
    entries: List[Entry] = []
    for dirpath, dirnames, filenames in os.walk(data_root):
        current = Path(dirpath)
        if exclude_dir is not None:
            # 剪枝: 备份输出目录整棵子树都不进入 (可能存着几百 MB 历史备份)
            dirnames[:] = [
                name for name in dirnames
                if not is_inside(current / name, exclude_dir)
            ]
        for name in sorted(filenames):
            f = current / name
            if exclude_dir is not None and is_inside(f, exclude_dir):
                continue
            try:
                arcname = f'data/{f.relative_to(data_root).as_posix()}'
            except ValueError:
                continue
            entries.append((f, arcname))
    return entries


def _safe_scan(name: str, func, *args) -> List[Entry]:
    """扫描失败时只记录日志并跳过该类内容, 不影响整次备份。"""
    try:
        return func(*args)
    except Exception as e:
        log.warning(f'{name}扫描失败, 跳过: {e}')
        return []


def _scan_plugin_entries(
    include_plugins: bool = True,
    plugins: Optional[List[str]] = None,
) -> List[Entry]:
    """插件运行数据条目。``plugins`` 为 None 表示全部, [] 表示一个都不备份。"""
    if not include_plugins:
        return []
    return _safe_scan('插件数据', iter_plugin_backup_entries, plugins)


def _scan_plugin_source_entries(
    include_plugin_src: bool = True,
    plugins: Optional[List[str]] = None,
) -> List[Entry]:
    """插件源码与配置条目 (除 data/ 外的全部文件)。"""
    if not include_plugin_src:
        return []
    return _safe_scan('插件源码与配置', iter_plugin_source_entries, plugins)


def _scan_module_entries(
    include_modules: bool = True,
    modules: Optional[List[str]] = None,
) -> List[Entry]:
    """模块运行数据条目 (含 modules_enabled.json)。"""
    if not include_modules:
        return []
    return _safe_scan('模块数据', iter_module_backup_entries, modules)


def _scan_module_source_entries(
    include_module_src: bool = True,
    modules: Optional[List[str]] = None,
) -> List[Entry]:
    """模块源码与配置条目 (除 data/ 外的全部文件)。"""
    if not include_module_src:
        return []
    return _safe_scan('模块源码与配置', iter_module_source_entries, modules)


# ==================== 条目工具 ====================


def _merge_entries(*groups: Iterable[Entry]) -> List[Entry]:
    """合并多组条目: 去掉空路径与 ZIP 内重名项, 并按 ZIP 内路径排序。"""
    merged: List[Entry] = []
    seen = set()
    for group in groups:
        for src, arcname in group:
            arcname = str(arcname).strip('/')
            if not arcname or arcname in seen:
                continue
            seen.add(arcname)
            merged.append((src, arcname))
    merged.sort(key=lambda item: item[1])
    return merged


def _entries_size(entries: Iterable[Entry]) -> int:
    """条目总体积。"""
    return total_size(src for src, _ in entries)


def _group_stats(entries: Iterable[Entry], level: int = 1) -> List[Dict[str, Any]]:
    """按 ZIP 内第 ``level`` 段名字聚合文件数与体积。

    例如 ``plugins/云痕/data/a.json`` 在 level=1 时归到 ``云痕``;
    ``modules/modules_enabled.json`` 这类根级文件不归入任何模块, 直接跳过。
    """
    stats: Dict[str, Dict[str, Any]] = {}
    for src, arcname in entries:
        parts = Path(arcname).parts
        if len(parts) <= level + 1:
            continue
        name = parts[level]
        item = stats.setdefault(name, {'name': name, 'file_count': 0, 'size': 0})
        item['file_count'] += 1
        try:
            item['size'] += src.stat().st_size
        except OSError:
            pass
    result = sorted(stats.values(), key=lambda x: x['name'])
    for item in result:
        item['size_readable'] = format_size(item['size'])
    return result


# ==================== 元数据 ====================


def generate_backup_info(
    *,
    created_at: datetime,
    include_config: bool = True,
    include_data: bool = True,
    include_plugins: bool = True,
    include_plugin_src: bool = True,
    include_modules: bool = True,
    include_module_src: bool = True,
    config_entries: Optional[List[Entry]] = None,
    data_entries: Optional[List[Entry]] = None,
    plugin_entries: Optional[List[Entry]] = None,
    plugin_src_entries: Optional[List[Entry]] = None,
    module_entries: Optional[List[Entry]] = None,
    module_src_entries: Optional[List[Entry]] = None,
) -> Dict[str, Any]:
    """生成 backup_info.json 内容 (全部统计都基于已扫描好的条目, 不再重复扫盘)。"""
    config_entries = config_entries or []
    data_entries = data_entries or []
    plugin_entries = plugin_entries or []
    plugin_src_entries = plugin_src_entries or []
    module_entries = module_entries or []
    module_src_entries = module_src_entries or []

    bot_config: Dict[str, Any] = {}
    bot_yaml = CONFIG_DIR / 'bot.yaml'
    if bot_yaml.exists() and include_config:
        try:
            import yaml
            with open(bot_yaml, 'r', encoding='utf-8') as f:
                bot_config = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning(f"读取 bot.yaml 失败: {e}")

    config_size = _entries_size(config_entries)
    data_size = _entries_size(data_entries)
    plugin_items = _group_stats(plugin_entries)
    plugin_size = _entries_size(plugin_entries)
    plugin_src_items = _group_stats(plugin_src_entries)
    plugin_src_size = _entries_size(plugin_src_entries)
    module_items = _group_stats(module_entries)
    module_size = _entries_size(module_entries)
    module_src_items = _group_stats(module_src_entries)
    module_src_size = _entries_size(module_src_entries)

    total_size = config_size + data_size + plugin_size + plugin_src_size + module_size + module_src_size

    return {
        'version': BACKUP_VERSION,
        'created_at': created_at.isoformat(),
        'created_at_readable': created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'bot_config': {
            'appid': bot_config.get('appid', ''),
            'platform': bot_config.get('platform', ''),
        } if include_config and bot_config else {},
        'include_config': include_config,
        'include_data': include_data,
        'include_plugins': bool(include_plugins),
        'include_plugin_src': bool(include_plugin_src),
        'include_modules': bool(include_modules),
        'include_module_src': bool(include_module_src),
        'config_files': [Path(arc).name for _, arc in config_entries],
        'config_count': len(config_entries),
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_entries),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'plugin_count': len(plugin_items),
        'plugin_file_count': len(plugin_entries),
        'plugin_size': plugin_size,
        'plugin_size_readable': format_size(plugin_size),
        'plugins': plugin_items,
        'plugin_src_count': len(plugin_src_items),
        'plugin_src_file_count': len(plugin_src_entries),
        'plugin_src_size': plugin_src_size,
        'plugin_src_size_readable': format_size(plugin_src_size),
        'plugin_src': plugin_src_items,
        'module_count': len(module_items),
        'module_file_count': len(module_entries),
        'module_size': module_size,
        'module_size_readable': format_size(module_size),
        'modules': module_items,
        'module_src_count': len(module_src_items),
        'module_src_file_count': len(module_src_entries),
        'module_src_size': module_src_size,
        'module_src_size_readable': format_size(module_src_size),
        'module_src': module_src_items,
        'total_size_readable': format_size(total_size),
        'backup_location': str(get_backup_dir()),
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown',
    }


def _append_stat_lines(lines: List[str], info: Dict[str, Any], prefix: str, title: str, key: str) -> None:
    """按统一格式追加「N 个 / M 个文件 (体积)」的说明行。"""
    if not info.get(f'include_{key}'):
        lines.append(f'- **{title}**: 未备份')
        return
    lines.append(
        f'- **{title}**: {info.get(f"{prefix}_count", 0)} 个 / '
        f'{info.get(f"{prefix}_file_count", 0)} 个文件 '
        f'({info.get(f"{prefix}_size_readable", "0 B")})'
    )


def generate_readme(info: Dict[str, Any]) -> str:
    lines = [
        '# 备份说明', '',
        f'**生成时间**: {info.get("created_at_readable", "未知")}',
        f'**备份版本**: v{info.get("version", BACKUP_VERSION)}',
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

    _append_stat_lines(lines, info, 'plugin', '插件数据', 'plugins')
    if info.get('include_plugins'):
        for item in info.get('plugins', []):
            lines.append(f'  - `{item.get("name", "")}`: {item.get("file_count", 0)} 个文件 ({item.get("size_readable", "0 B")})')
        lines.append('  - 注: 只含 data/ 运行数据 (含备份工具自身 data/, 已跳过其生成的备份包)')

    _append_stat_lines(lines, info, 'plugin_src', '插件源码与配置', 'plugin_src')
    if info.get('include_plugin_src') and info.get('plugin_src'):
        for item in info.get('plugin_src', []):
            lines.append(f'  - `{item.get("name", "")}`: {item.get("file_count", 0)} 个文件 ({item.get("size_readable", "0 B")})')
    elif info.get('include_plugin_src'):
        lines.append('  - 注: 含 data/ 外的全部文件 (*.py + 面板 html / json / yaml 等), 未收集到任何文件')

    _append_stat_lines(lines, info, 'module', '模块数据', 'modules')
    if info.get('include_modules'):
        for item in info.get('modules', []):
            lines.append(f'  - `{item.get("name", "")}`: {item.get("file_count", 0)} 个文件 ({item.get("size_readable", "0 B")})')
        lines.append('  - 注: 含 modules_enabled.json 模块启用状态')

    _append_stat_lines(lines, info, 'module_src', '模块源码与配置', 'module_src')
    if info.get('include_module_src') and info.get('module_src'):
        for item in info.get('module_src', []):
            lines.append(f'  - `{item.get("name", "")}`: {item.get("file_count", 0)} 个文件 ({item.get("size_readable", "0 B")})')

    bot = info.get('bot_config', {})
    if bot.get('appid'):
        lines.extend(['', '## Bot 配置', f'- AppID: `{bot.get("appid", "")}`', f'- 平台: `{bot.get("platform", "未知")}`'])
    lines.extend(['', '---', '', '## 恢复方法', '',
        '1. 安装本插件到新框架', '2. 在 Web 面板进入「备份迁移」页面',
        '3. 上传此 ZIP 文件', '4. 点击「恢复备份」按钮', '',
        '> 含源码/配置的备份会覆盖目标机器上同名文件 (.py / html / json 等), 仅建议在迁移 / 回滚时使用。', '',
        '---', '',
        f'*备份工具版本: v{info.get("version", BACKUP_VERSION)}*',
        f'*生成于 {info.get("created_at_readable", "未知")}*',
    ])
    return '\n'.join(lines)


# ==================== 创建备份 ====================


def create_backup(
    plugins: Optional[List[str]] = None,
    modules: Optional[List[str]] = None,
    include_data_files: bool = True,
    include_config_files: bool = True,
    include_config: bool = False,
    include_data: bool = False,
) -> Optional[str]:
    """创建备份 ZIP, 返回文件名; 失败返回 None。

    备份范围 = 所选插件 / 模块的「数据文件」+「配置文件(源码与自带配置/资源)」,
    两类内容都可通过开关独立选择 (v2.7 起):

    - ``include_data_files``   : 是否打包 ``plugins/<名>/data/**`` 与 ``modules/<名>/data/**``
    - ``include_config_files`` : 是否打包插件 / 模块除 data/ 外的全部文件
                                 (*.py + panel.html / json / yaml / 资源等)
    - ``include_config`` / ``include_data`` : 框架 ``config/*.yaml`` 与项目根 ``data/``,
      默认都不打包 (项目根 data/ 可能上百 MB, 且与插件备份重复)

    ``plugins`` / ``modules`` 为 None 表示全部, 空列表表示一个都不备份。
    """
    now = datetime.now()
    filename = f"backup_{now.strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = get_backup_dir() / filename

    # 各分类只扫描一次, 结果同时用于元数据、README 与写 ZIP
    config_entries = _scan_config_entries(include_config)
    data_entries = _scan_data_entries(include_data)
    plugin_entries = _scan_plugin_entries(include_data_files, plugins)
    plugin_src_entries = _scan_plugin_source_entries(include_config_files, plugins)
    module_entries = _scan_module_entries(include_data_files, modules)
    module_src_entries = _scan_module_source_entries(include_config_files, modules)

    info = generate_backup_info(
        created_at=now,
        include_config=include_config,
        include_data=include_data,
        include_plugins=include_data_files,
        include_plugin_src=include_config_files,
        include_modules=include_data_files,
        include_module_src=include_config_files,
        config_entries=config_entries,
        data_entries=data_entries,
        plugin_entries=plugin_entries,
        plugin_src_entries=plugin_src_entries,
        module_entries=module_entries,
        module_src_entries=module_src_entries,
    )

    all_entries = _merge_entries(
        config_entries, data_entries,
        plugin_entries, plugin_src_entries,
        module_entries, module_src_entries,
    )

    try:
        written = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(INFO_FILENAME, json.dumps(info, ensure_ascii=False, indent=2))
            zf.writestr(README_FILENAME, generate_readme(info))
            for src, arcname in all_entries:
                try:
                    zf.write(src, arcname)
                    written += 1
                except OSError as e:
                    # 单个文件损坏 / 被占用时跳过, 不让整次备份失败
                    log.warning(f'写入备份条目失败 (已跳过) {arcname}: {e}')
        size = zip_path.stat().st_size
        log.info(
            f'备份完成: {filename} ({format_size(size)}), 共 {written} 个文件 | '
            f"配置={len(config_entries)}, 数据={len(data_entries)}, "
            f"插件数据={len(plugin_entries)}, 插件源码/配置={len(plugin_src_entries)}, "
            f"模块数据={len(module_entries)}, 模块源码/配置={len(module_src_entries)}"
        )
        return filename
    except Exception as e:
        log.error(f'备份失败: {e}')
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                pass
        return None
