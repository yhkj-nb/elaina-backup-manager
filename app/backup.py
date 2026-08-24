# plugins/备份工具/app/backup.py
"""备份创建"""

import json
import zipfile
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .constants import CONFIG_DIR, DATA_DIR, PROJECT_ROOT
from .utils import (
    log, format_size,
    get_config_files, get_data_files,
    get_config_size, get_data_size,
)


def generate_backup_info(include_config: bool = True, include_data: bool = True) -> Dict[str, Any]:
    bot_config = {}
    bot_yaml = CONFIG_DIR / 'bot.yaml'
    if bot_yaml.exists() and include_config:
        try:
            import yaml
            with open(bot_yaml, 'r', encoding='utf-8') as f:
                bot_config = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning(f"读取 bot.yaml 失败: {e}")

    config_files = get_config_files() if include_config else []
    config_size = get_config_size() if include_config else 0
    data_files = get_data_files() if include_data else []
    data_size = get_data_size() if include_data else 0

    return {
        'version': '1.6',
        'created_at': datetime.now().isoformat(),
        'created_at_readable': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'bot_config': {
            'appid': bot_config.get('appid', ''),
            'platform': bot_config.get('platform', ''),
        } if include_config and bot_config else {},
        'include_config': include_config,
        'include_data': include_data,
        'config_files': config_files,
        'config_count': len(config_files),
        'config_size': config_size,
        'config_size_readable': format_size(config_size),
        'data_count': len(data_files),
        'data_size': data_size,
        'data_size_readable': format_size(data_size),
        'total_size_readable': format_size(config_size + data_size),
        'backup_location': str(DATA_DIR),
        'hostname': os.uname().nodename if hasattr(os, 'uname') else 'unknown'
    }


def generate_readme(info: Dict[str, Any]) -> str:
    lines = [
        '# 备份说明', '',
        f'**生成时间**: {info.get("created_at_readable", "未知")}',
        f'**备份版本**: v{info.get("version", "unknown")}',
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
        f'*备份工具版本: v{info.get("version", "1.6")}*',
        f'*生成于 {info.get("created_at_readable", "未知")}*',
    ])
    return '\n'.join(lines)


def create_backup(include_config: bool = True, include_data: bool = True) -> Optional[str]:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"backup_{timestamp}.zip"
    zip_path = DATA_DIR / filename
    info = generate_backup_info(include_config, include_data)
    readme_content = generate_readme(info)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('backup_info.json', json.dumps(info, ensure_ascii=False, indent=2))
            zf.writestr('README.md', readme_content)
            if include_config and CONFIG_DIR.exists():
                for f in CONFIG_DIR.glob('*.yaml'):
                    zf.write(f, f"config/{f.name}")
                for f in CONFIG_DIR.glob('*.yml'):
                    zf.write(f, f"config/{f.name}")
            if include_data:
                data_root = PROJECT_ROOT / 'data'
                if data_root.exists():
                    for f in data_root.rglob('*'):
                        if f.is_file() and '备份工具' not in str(f):
                            arcname = f"data/{f.relative_to(data_root)}"
                            zf.write(f, arcname)
        log.info(f'✅ 备份创建成功: {filename} ({format_size(zip_path.stat().st_size)})')
        return filename
    except Exception as e:
        log.error(f'备份失败: {e}')
        if zip_path.exists():
            zip_path.unlink()
        return None
