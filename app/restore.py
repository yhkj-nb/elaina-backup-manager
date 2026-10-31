# plugins/备份工具/app/restore.py
"""备份恢复

支持五类 ZIP 内路径 (白名单):
- ``config/...``            → 项目 config/
- ``data/...``              → 项目 data/
- ``plugins/<插件名>/data/...``   → 项目 plugins/<插件名>/data  (v2.2 新增)
- ``plugins/<插件名>/*``          → 插件源码与配置 (v2.4 新增源码; v2.7 起含 panel.html 等非 .py 文件,
                                   *.py 会额外记录在 restored_plugin_src)
- ``modules/<模块名>/...``        → 项目 modules/<模块名>/..., 含 modules_enabled.json 与模块源码/配置
                                   (v2.3 新增数据 / v2.4 新增源码 / v2.7 起含配置文件)

所有写入都会做路径穿越校验, 目标必须落在对应根目录内;
备份工具自身目录不会被恢复覆盖 (避免旧备份破坏运行中的插件与云盘凭据)。
含源码/配置的备份会覆盖同名文件, 仅在迁移 / 回滚时使用。
"""

import json
import zipfile
import re
from pathlib import Path
from typing import Dict, Any, Optional

from .constants import CONFIG_DIR, PLUGIN_DIR, PROJECT_ROOT
from .utils import log


def _safe_member_parts(item: str) -> Optional[list]:
    """拆分并校验 ZIP 成员路径, 不安全时返回 None。"""
    parts = item.replace('\\', '/').split('/')
    for part in parts:
        if not part or part in ('.', '..') or '..' in part or part.startswith('/'):
            return None
    return parts


def _is_inside(path: Path, parent: Path) -> bool:
    """解析后路径必须位于 parent 内 (防止符号链接 / 路径穿越)。"""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _extract_member(zf: zipfile.ZipFile, item: str, target_path: Path) -> None:
    """流式写出单个 ZIP 成员。"""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(item) as src:
        with open(target_path, 'wb') as dst:
            while True:
                chunk = src.read(8192)
                if not chunk:
                    break
                dst.write(chunk)


def restore_backup(zip_path: Path) -> Dict[str, Any]:
    result = {
        'success': False, 'restored_configs': [], 'restored_data': [],
        'restored_plugins': [], 'restored_modules': [],
        'restored_plugin_src': [], 'restored_module_src': [],
        'skipped_files': [], 'errors': [], 'backup_info': {},
    }
    if not zip_path.exists():
        result['errors'].append(f"备份文件不存在: {zip_path}")
        return result

    plugins_root = PROJECT_ROOT / 'plugins'
    modules_root = PROJECT_ROOT / 'modules'

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
                parts = _safe_member_parts(item)
                if parts is None:
                    result['skipped_files'].append(item)
                    result['errors'].append(f"跳过不安全的路径: {item}")
                    continue

                try:
                    if parts[0] == 'config' and len(parts) >= 2:
                        rel_path = Path(*parts[1:])
                        target_path = CONFIG_DIR / rel_path
                        if not _is_inside(target_path, CONFIG_DIR):
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过越界路径: {item}")
                            continue
                        _extract_member(zf, item, target_path)
                        result['restored_configs'].append(rel_path.as_posix())
                    elif parts[0] == 'data' and len(parts) >= 2:
                        rel_path = Path(*parts[1:])
                        target_path = PROJECT_ROOT / 'data' / rel_path
                        if not _is_inside(target_path, PROJECT_ROOT / 'data'):
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过越界路径: {item}")
                            continue
                        _extract_member(zf, item, target_path)
                        result['restored_data'].append(rel_path.as_posix())
                    elif parts[0] == 'plugins':
                        if len(parts) < 3:
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过无效的插件数据路径: {item}")
                            continue
                        plugin_name = parts[1]
                        rel_path = Path(*parts[2:])
                        if plugin_name == PLUGIN_DIR.name:
                            # 备份工具 v2.7 起会把自身打进备份, 但恢复时仍跳过自身:
                            # 避免用旧备份覆盖正在运行的插件代码与云盘凭据
                            result['skipped_files'].append(item)
                            continue
                        target_path = plugins_root / plugin_name / rel_path
                        if not _is_inside(target_path, plugins_root):
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过越界路径: {item}")
                            continue
                        _extract_member(zf, item, target_path)
                        result['restored_plugins'].append(f"{plugin_name}/{rel_path.as_posix()}")
                        if rel_path.suffix == '.py':
                            # 源码单独统计, 便于前端提示"覆盖了运行中的代码"
                            result['restored_plugin_src'].append(f"{plugin_name}/{rel_path.as_posix()}")
                    elif parts[0] == 'modules':
                        if len(parts) < 2:
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过无效的模块数据路径: {item}")
                            continue
                        rel_path = Path(*parts[1:])
                        target_path = modules_root / rel_path
                        if not _is_inside(target_path, modules_root):
                            result['skipped_files'].append(item)
                            result['errors'].append(f"跳过越界路径: {item}")
                            continue
                        _extract_member(zf, item, target_path)
                        result['restored_modules'].append(rel_path.as_posix())
                        if rel_path.suffix == '.py':
                            result['restored_module_src'].append(rel_path.as_posix())
                    else:
                        result['skipped_files'].append(item)
                except Exception as e:
                    result['errors'].append(f"恢复 {item} 失败: {str(e)}")
                    log.warning(f"恢复文件失败 {item}: {e}")

            if (result['restored_configs'] or result['restored_data']
                    or result['restored_plugins'] or result['restored_modules']):
                result['success'] = True
                log.info(
                    f'恢复成功: 配置={len(result["restored_configs"])}, '
                    f'数据={len(result["restored_data"])}, '
                    f'插件文件={len(result["restored_plugins"])} '
                    f'(源码 {len(result["restored_plugin_src"])}), '
                    f'模块文件={len(result["restored_modules"])} '
                    f'(源码 {len(result["restored_module_src"])})'
                )
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
                    m = re.search(r'-\s*\*\*插件数据\*\*:\s*(\d+)\s*个插件\s*/\s*(\d+)', content)
                    if m:
                        info['plugin_count'] = int(m.group(1))
                        info['plugin_file_count'] = int(m.group(2))
                    m = re.search(r'-\s*\*\*模块数据\*\*:\s*(\d+)\s*个模块\s*/\s*(\d+)', content)
                    if m:
                        info['module_count'] = int(m.group(1))
                        info['module_file_count'] = int(m.group(2))
            else:
                info['warning'] = '无法识别的备份文件格式'
    except Exception as e:
        log.error(f'解析备份信息失败: {e}')
        info['error'] = str(e)
    return info
