# plugins/备份工具/app/restore.py
"""备份恢复"""

import json
import zipfile
import re
from pathlib import Path
from typing import Dict, Any

from .constants import CONFIG_DIR, PROJECT_ROOT
from .utils import log


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
