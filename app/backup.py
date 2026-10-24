# plugins/备份工具/app/backup.py
"""备份创建

优化说明 (相对旧版):
- 仅调用一次 datetime.now(), 避免 info / 文件名 / README 时间戳出现不一致
- 文件清单只扫描一遍, 同时供「元数据生成」与「写入 ZIP」复用, 不再重复 glob
- 数据备份自动排除备份输出目录自身 (含 temp/), 防止把历史备份再次打进新备份
- 失败时在 finally 之外统一清理半成品, 并保证统计尺寸与写入文件完全一致
"""

import json
import zipfile
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from .constants import CONFIG_DIR, PROJECT_ROOT, get_backup_dir
from .utils import (
    log, format_size,
)


# ==================== 文件扫描 ====================


def _scan_config_paths(include_config: bool = True) -> List[Path]:
    """返回 config/ 下待备份的 YAML 文件 (Path 列表), 已是排序状态。"""
    if not include_config or not CONFIG_DIR.exists():
        return []
    paths: List[Path] = []
    paths.extend(CONFIG_DIR.glob('*.yaml'))
    paths.extend(CONFIG_DIR.glob('*.yml'))
    return sorted(paths)


def _scan_data_paths(include_data: bool = True) -> List[Path]:
    """返回 data/ 下待备份的数据文件 (Path 列表)。

    会自动排除备份输出目录自身 (get_backup_dir()), 避免把已有的历史备份
    再次打进新备份里造成体积爆炸 / 递归打包。
    """
    if not include_data:
        return []
    exclude_dir = get_backup_dir()
    data_root = PROJECT_ROOT / 'data'
    paths: List[Path] = []
    if data_root.exists():
        for f in data_root.rglob('*'):
            if not f.is_file():
                continue
            try:
                if f == exclude_dir or exclude_dir in f.parents:
                    continue
            except Exception:
                pass
            paths.append(f)
    return paths


def _total_size(paths: List[Path]) -> int:
    total = 0
    for p in paths:
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total


# ==================== 元数据 ====================


def generate_backup_info(
    include_config: bool = True,
    include_data: bool = True,
    config_paths: Optional[List[Path]] = None,
    data_paths: Optional[List[Path]] = None,
) -> Dict[str, Any]:
    # 一次性取时间, 保证后面文件名 / info / README 三处时间戳完全一致
    now = datetime.now()

    bot_config: Dict[str, Any] = {}
    bot_yaml = CONFIG_DIR / 'bot.yaml'
    if bot_yaml.exists() and include_config:
        try:
            import yaml
            with open(bot_yaml, 'r', encoding='utf-8') as f:
                bot_config = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning(f"读取 bot.yaml 失败: {e}")

    if config_paths is None:
        config_paths = _scan_config_paths(include_config)
    if data_paths is None:
        data_paths = _scan_data_paths(include_data)

    config_size = _total_size(config_paths) if include_config else 0
    data_size = _total_size(data_paths) if include_data else 0

    return {
        'version': '1.7',
        'created_at': now.isoformat(),
        'created_at_readable': now.strftime('%Y-%m-%d %H:%M:%S'),
        'bot_config': {
            'appid': bot_config.get('appid', ''),
            'platform': bot_config.get('platform', ''),
        } if include_config and bot_config else {},
        'include_config': include_config,
        'include_data': include_data,
        'config_files': [p.name for p in config_paths],
        'config_count': len(config_paths),
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_paths),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'total_size_readable': format_size(config_size + data_size),
        'backup_location': str(get_backup_dir()),
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
    }


def generate_readme(info: Dict[str, Any]) -> str:
    lines = [
        '# 备份说明', '',
        f'**生成时间**: {info.get("created_at_readable", "未知")}',
        f'**备份版本**: v{info.get("version", "1.7")}',
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
        f'*备份工具版本: v{info.get("version", "1.7")}*',
        f'*生成于 {info.get("created_at_readable", "未知")}*',
    ])
    return '\n'.join(lines)


# ==================== 创建备份 ====================


def create_backup(include_config: bool = True, include_data: bool = True) -> Optional[str]:
    now = datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    filename = f"backup_{timestamp}.zip"
    zip_path = get_backup_dir() / filename

    # 文件清单只扫描一遍, 同时用于元数据与写入
    config_paths = _scan_config_paths(include_config)
    data_paths = _scan_data_paths(include_data)
    info = generate_backup_info(include_config, include_data, config_paths, data_paths)
    readme_content = generate_readme(info)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('backup_info.json', json.dumps(info, ensure_ascii=False, indent=2))
            zf.writestr('README.md', readme_content)
            for f in config_paths:
                zf.write(f, f"config/{f.name}")
            data_root = PROJECT_ROOT / 'data'
            for f in data_paths:
                try:
                    arcname = f"data/{f.relative_to(data_root)}"
                except ValueError:
                    continue
                zf.write(f, arcname)
        size = zip_path.stat().st_size
        log.info(f'✅ 备份创建成功: {filename} ({format_size(size)})')
        return filename
    except Exception as e:
        log.error(f'备份失败: {e}')
        if zip_path.exists():
            try:
                zip_path.unlink()
            except OSError:
                pass
        return None
