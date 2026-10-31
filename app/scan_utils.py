# plugins/备份工具/app/scan_utils.py
"""扫描通用工具 (插件 / 模块共用)

这里只放纯粹的目录遍历、排除规则与体积统计, 不含任何备份策略,
让 plugins_scan.py 与 modules_scan.py 只保留"备份什么"的业务判断。

相比旧版在每个扫描函数里 rglob('*') 再逐个过滤, 这里用 os.walk 并**在遍历阶段剪枝**:
- 遇到缓存 / 隐藏 / 排除目录直接不进入, 不再产生无用的 stat 与 relative_to
- 扫描插件 / 模块的 Python 源码时, data/ 整个子树被跳过 (可能是几百 MB 的运行数据)

排除规则:
- 目录: 缓存 / 构建产物 / 虚拟环境 / 临时目录 / 隐藏目录
- 文件: 字节码 / 临时文件 / 日志 / 系统垃圾文件 / 隐藏文件
- 自定义备份输出目录 (backup_dir 落在被扫描目录内时), 防止历史备份被递归打包
"""

import os
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Set

# 目录级排除
EXCLUDE_DIR_NAMES = {
    '__pycache__', '.git', '.idea', '.vscode', '.pytest_cache',
    'node_modules', 'venv', '.venv', 'env', '.env',
    'temp', 'tmp', 'cache', '.cache',
}

# 文件级排除 (后缀)
EXCLUDE_SUFFIXES = {
    '.pyc', '.pyo', '.pyd', '.tmp', '.temp', '.swp', '.swo', '.log',
}

# 文件级排除 (完整文件名)
EXCLUDE_FILE_NAMES = {'.DS_Store', 'Thumbs.db'}


# ==================== 路径判断 ====================


def is_inside(path: Path, parent: Path) -> bool:
    """path 是否位于 parent 目录内 (含 parent 自身), 解析符号链接后判断。"""
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def is_hidden(rel_path: Path) -> bool:
    """相对路径中是否有任意一段以 . 开头 (隐藏文件 / 目录)。"""
    return any(part.startswith('.') for part in rel_path.parts)


def is_excluded_file(path: Path) -> bool:
    """文件名 / 后缀是否在排除清单中。"""
    if path.name in EXCLUDE_FILE_NAMES or path.name.startswith('.'):
        return True
    return path.suffix.lower() in EXCLUDE_SUFFIXES


def total_size(paths: Iterable[Path]) -> int:
    """累计文件体积, 单个文件 stat 失败时忽略。"""
    size = 0
    for p in paths:
        try:
            size += p.stat().st_size
        except OSError:
            pass
    return size


# ==================== 目录遍历 ====================


def iter_payload_files(
    directory: Path,
    *,
    skip_top_dirs: Sequence[str] = (),
    exclude_dir: Optional[Path] = None,
    suffixes: Optional[Set[str]] = None,
    skip_files: Optional[Callable[[Path], bool]] = None,
) -> List[Path]:
    """递归收集 directory 下待备份的文件 (已按排除规则剪枝)。

    Args:
        directory:      待扫描目录, 不存在时返回空列表
        skip_top_dirs:  仅跳过第一层的这些子目录 (如扫源码时跳过 data/)
        exclude_dir:    需要整体排除的目录 (通常是用户自定义的备份输出目录)
        suffixes:       只保留这些后缀 (小写带点); None 表示不限后缀
        skip_files:     额外的文件级过滤 (返回 True 表示跳过),
                        用于插件自身 data/ 下的历史备份包等个案排除
    """
    if not directory.is_dir():
        return []

    skip_top = {name for name in skip_top_dirs if name}
    exclude_target: Optional[Path] = None
    if exclude_dir is not None:
        try:
            exclude_target = Path(exclude_dir)
            if not exclude_target.exists():
                exclude_target = None
        except OSError:
            exclude_target = None

    results: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(directory):
        current = Path(dirpath)
        try:
            rel_dir = current.relative_to(directory)
        except ValueError:
            rel_dir = Path('.')
        at_root = not rel_dir.parts or rel_dir == Path('.')

        # 剪枝: 排除的目录不再进入
        kept_dirs: List[str] = []
        for name in dirnames:
            if name.startswith('.') or name in EXCLUDE_DIR_NAMES:
                continue
            if at_root and name in skip_top:
                continue
            if exclude_target is not None and is_inside(current / name, exclude_target):
                continue
            kept_dirs.append(name)
        dirnames[:] = sorted(kept_dirs)

        for name in sorted(filenames):
            path = current / name
            if name.startswith('.') or is_excluded_file(path):
                continue
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            if skip_files is not None and skip_files(path):
                continue
            if exclude_target is not None and is_inside(path, exclude_target):
                continue
            results.append(path)

    return results
