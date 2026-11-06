# plugins/备份工具/app/chunk_upload.py
"""分片上传会话管理 (v2.8)

背景:
    ElainaBot v2 框架的 aiohttp Application 使用 ``client_max_size=20MB`` 限制整个
    请求体, 而备份包 (含全部插件源码 + 运行数据) 很容易超过 20MB。旧版 ``/upload``
    一次性 POST 整个 ZIP, 超限会被 aiohttp 在解析阶段直接 413 拒绝, 根本进不到路由。

方案:
    前端把 ZIP 切成若干 << 20MB 的分片, 逐个 POST; 服务端按序落盘, 全部到位后
    流式合并成完整 ZIP 并做完整性校验。会话目录位于 ``data/temp/uploads/``,
    该目录已在 scan_utils 的排除清单里 (``temp``), 不会被打进备份包。

本模块只做纯逻辑 / 同步 IO (无 aiohttp 依赖), 由 routes.py 在线程池中调用,
因此可以在框架 ctx 未就绪时离线单测。

安全:
    - upload_id 为服务端生成的 32 位 hex, 严格校验格式, 杜绝路径穿越
    - filename 只取 basename, 白名单字符 + 必须 .zip
    - total_chunks / 单片大小 / 总大小均设上限
    - temp_path 恢复前必须 resolve 到 temp 目录内 (防任意文件恢复)
    - 合并后做 ZIP 完整性校验 (testzip) 与大小核对
"""

import json
import re
import shutil
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import get_backup_dir, get_upload_limits
from .utils import log, format_size
from .restore import parse_backup_info

# upload_id 必须严格匹配服务端生成的 hex, 防止 ../ 之类的路径穿越
UPLOAD_ID_RE = re.compile(r'^[0-9a-f]{32}$')
# 文件名白名单: 字母数字、中文、常见分隔符, 且必须以 .zip 结尾
SAFE_NAME_RE = re.compile(r'^[\w\u4e00-\u9fff.\- ()（）\[\]]+\.zip$', re.IGNORECASE)

# 单个分片允许的最小/最大体积 (前端遇 413 会自动减半, 故下限留到 64KB)
MIN_CHUNK_SIZE = 64 * 1024
MAX_CHUNK_SIZE = 8 * 1024 * 1024
# 单次上传最多允许的分片数 (500MB / 64KB ≈ 8000, 留余量)
MAX_TOTAL_CHUNKS = 20000
# 分片名固定宽度, 便于按序合并
PART_FMT = 'part_{:06d}.bin'
PART_RE = re.compile(r'^part_(\d{6})\.bin$')
META_NAME = 'meta.json'
TEMP_ZIP_PREFIX = 'upload_'


# ==================== 目录 ====================


def get_temp_dir() -> Path:
    """上传/恢复临时文件根目录 (位于备份输出目录下的 temp/, 已被扫描排除)。"""
    d = get_backup_dir() / 'temp'
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_uploads_dir() -> Path:
    """分片会话根目录。"""
    d = get_temp_dir() / 'uploads'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_dir(upload_id: str) -> Path:
    return get_uploads_dir() / upload_id


# ==================== 校验辅助 ====================


def _valid_upload_id(upload_id: Any) -> bool:
    return isinstance(upload_id, str) and bool(UPLOAD_ID_RE.match(upload_id))


def _sanitize_filename(name: Any) -> Optional[str]:
    """只保留 basename 并套白名单; 非法返回 None。"""
    if not isinstance(name, str):
        return None
    name = name.strip().replace('\\', '/')
    name = name.rsplit('/', 1)[-1]
    if not name or len(name) > 180 or not SAFE_NAME_RE.match(name):
        return None
    return name


def validate_temp_path(temp_path: Any) -> Optional[Path]:
    """校验恢复用的 temp_path: 必须存在、是文件、.zip, 且 resolve 后落在 temp 目录内。

    返回安全的 Path, 否则 None。防止客户端伪造任意路径让 restore 读取/覆盖系统文件。
    """
    if not isinstance(temp_path, str) or not temp_path:
        return None
    try:
        p = Path(temp_path).resolve()
        root = get_temp_dir().resolve()
        # relative_to 成功即代表 p 在 root 内 (含子目录)
        p.relative_to(root)
    except (ValueError, OSError, RuntimeError):
        return None
    if not p.is_file() or p.suffix.lower() != '.zip':
        return None
    return p


# ==================== 会话元数据 ====================


def _read_meta(upload_id: str) -> Optional[Dict[str, Any]]:
    p = _session_dir(upload_id) / META_NAME
    if not p.is_file():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_meta(upload_id: str, meta: Dict[str, Any]) -> None:
    p = _session_dir(upload_id) / META_NAME
    tmp = p.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def _received_indices(upload_id: str) -> List[int]:
    """返回已成功落盘的分片索引 (升序)。"""
    d = _session_dir(upload_id)
    out: List[int] = []
    if not d.is_dir():
        return out
    for f in d.iterdir():
        m = PART_RE.match(f.name)
        if m and f.is_file() and f.stat().st_size >= 0:
            out.append(int(m.group(1)))
    return sorted(out)


# ==================== 对外操作 ====================


def init_upload(filename: Any, size: Any, client_chunk_size: Any = None) -> Dict[str, Any]:
    """初始化一次分片上传会话。

    size 为文件总字节数, client_chunk_size 为前端期望的单片大小 (遇 413 减半后传入)。
    返回 {success, upload_id, chunk_size, total_chunks, received, ...} 或 {success:False, error}。
    """
    limits = get_upload_limits()
    max_size = int(limits['max_size_bytes'])
    cfg_chunk = int(limits['chunk_size_bytes'])

    name = _sanitize_filename(filename)
    if not name:
        return {'success': False, 'error': '文件名非法 (仅支持 .zip 备份包)'}
    try:
        size = int(size)
    except (TypeError, ValueError):
        return {'success': False, 'error': '文件大小参数非法'}
    if size <= 0:
        return {'success': False, 'error': '文件为空'}
    if size > max_size:
        return {
            'success': False,
            'error': f'文件超过上限 ({format_size(size)} > {format_size(max_size)})',
            'max_size': max_size,
        }

    # 单片大小: 取 (前端期望, 配置值) 的较小者, 再夹到合法区间
    chunk_size = cfg_chunk
    if client_chunk_size is not None:
        try:
            chunk_size = min(chunk_size, int(client_chunk_size))
        except (TypeError, ValueError):
            pass
    chunk_size = max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, chunk_size))
    total_chunks = (size + chunk_size - 1) // chunk_size
    if total_chunks > MAX_TOTAL_CHUNKS:
        return {'success': False, 'error': '分片数过多, 请调大单片大小或检查文件'}

    # init 时顺带清理过期的孤儿会话与残留临时包
    cleanup_stale(int(limits.get('temp_ttl_hours', 6)))

    upload_id = uuid.uuid4().hex
    d = _session_dir(upload_id)
    d.mkdir(parents=True, exist_ok=True)
    _write_meta(upload_id, {
        'upload_id': upload_id,
        'filename': name,
        'size': size,
        'chunk_size': chunk_size,
        'total_chunks': total_chunks,
        'created_at': datetime.now().isoformat(timespec='seconds'),
        'ts': time.time(),
    })
    log.info(f'分片上传 init: {name} {format_size(size)} -> {total_chunks} 片 × {format_size(chunk_size)} (id={upload_id[:8]})')
    return {
        'success': True,
        'upload_id': upload_id,
        'filename': name,
        'size': size,
        'chunk_size': chunk_size,
        'total_chunks': total_chunks,
        'received': [],
        'max_size': max_size,
    }


def write_chunk(upload_id: Any, index: Any, data: bytes) -> Dict[str, Any]:
    """写入单个分片 (原子落盘)。data 为该分片的原始字节。"""
    if not _valid_upload_id(upload_id):
        return {'success': False, 'error': '非法的 upload_id'}
    meta = _read_meta(upload_id)
    if not meta:
        return {'success': False, 'error': '上传会话不存在或已过期, 请重新上传'}
    try:
        index = int(index)
    except (TypeError, ValueError):
        return {'success': False, 'error': '非法的分片序号'}
    total = int(meta['total_chunks'])
    if index < 0 or index >= total:
        return {'success': False, 'error': '分片序号越界'}
    if not isinstance(data, (bytes, bytearray)):
        return {'success': False, 'error': '分片数据为空'}
    # 单片允许略带余量 (multipart 头部不计入 data), 但不能超过 2 倍配置值
    if len(data) > int(meta['chunk_size']) * 2:
        return {'success': False, 'error': '分片体积异常'}

    d = _session_dir(upload_id)
    part = d / PART_FMT.format(index)
    tmp = part.with_suffix('.part.tmp')
    with open(tmp, 'wb') as f:
        f.write(data)
    tmp.replace(part)
    received = _received_indices(upload_id)
    return {'success': True, 'index': index, 'received_count': len(received), 'total_chunks': total}


def complete_upload(upload_id: Any) -> Dict[str, Any]:
    """所有分片到位后合并成完整 ZIP, 校验并返回与旧 /upload 一致的结构。"""
    if not _valid_upload_id(upload_id):
        return {'success': False, 'error': '非法的 upload_id'}
    meta = _read_meta(upload_id)
    if not meta:
        return {'success': False, 'error': '上传会话不存在或已过期, 请重新上传'}

    d = _session_dir(upload_id)
    total = int(meta['total_chunks'])
    expected_size = int(meta['size'])
    missing = [i for i in range(total) if not (d / PART_FMT.format(i)).is_file()]
    if missing:
        return {
            'success': False,
            'error': f'还有 {len(missing)} 个分片未上传',
            'missing': missing[:20],
            'received_count': total - len(missing),
        }

    # 流式合并: 逐片按序读出写入目标文件, 不把整个 ZIP 读进内存
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = get_temp_dir() / f"{TEMP_ZIP_PREFIX}{ts}_{upload_id[:8]}.zip"
    written = 0
    try:
        with open(dest, 'wb') as out:
            for i in range(total):
                with open(d / PART_FMT.format(i), 'rb') as src:
                    while True:
                        buf = src.read(1024 * 1024)
                        if not buf:
                            break
                        out.write(buf)
                        written += len(buf)
    except Exception as e:
        dest.unlink(missing_ok=True)
        log.error(f'分片合并失败: {e}')
        return {'success': False, 'error': f'合并失败: {e}'}

    # 大小核对
    if written != expected_size:
        dest.unlink(missing_ok=True)
        return {
            'success': False,
            'error': f'合并大小不符 ({format_size(written)} ≠ 声明 {format_size(expected_size)})',
        }

    # ZIP 完整性校验 (损坏 / 非 ZIP 直接拒绝)
    try:
        with zipfile.ZipFile(dest, 'r') as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f'损坏的成员: {bad}')
            if not zf.namelist():
                raise zipfile.BadZipFile('空 ZIP')
    except (zipfile.BadZipFile, OSError) as e:
        dest.unlink(missing_ok=True)
        return {'success': False, 'error': f'无效的 ZIP 备份文件: {e}'}

    info = parse_backup_info(dest) or {}
    info['file_size'] = format_size(written)
    info['size_bytes'] = written
    info['original_filename'] = meta['filename']

    # 合并成功, 清掉分片会话目录
    shutil.rmtree(d, ignore_errors=True)
    log.info(f'分片上传完成: {meta["filename"]} {format_size(written)} -> {dest.name}')
    return {
        'success': True,
        'filename': meta['filename'],
        'size': format_size(written),
        'size_bytes': written,
        'info': info,
        'temp_path': str(dest),
        'total_chunks': total,
    }


def abort_upload(upload_id: Any) -> Dict[str, Any]:
    """中止/取消上传, 删除会话目录。"""
    if not _valid_upload_id(upload_id):
        return {'success': False, 'error': '非法的 upload_id'}
    d = _session_dir(upload_id)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)
    return {'success': True, 'message': '已取消'}


def remove_temp_file(temp_path: Any) -> None:
    """恢复完成后删除临时 ZIP (仅限 temp 目录内的安全路径)。"""
    p = validate_temp_path(temp_path)
    if p:
        try:
            p.unlink(missing_ok=True)
        except OSError as e:
            log.warning(f'清理临时文件失败: {e}')


def cleanup_stale(max_age_hours: int = 6) -> int:
    """清理过期 (默认 >6h) 的孤儿上传会话、残留临时 ZIP; 返回删除项数量。

    在每次 init 时调用, 避免异常中断的分片/临时包长期占用磁盘。
    """
    removed = 0
    cutoff = time.time() - max(1, max_age_hours) * 3600
    try:
        uploads = get_uploads_dir()
        for d in list(uploads.iterdir()):
            try:
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        temp = get_temp_dir()
        for f in list(temp.glob(f'{TEMP_ZIP_PREFIX}*.zip')) + list(temp.glob('restore_*.zip')):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
    except Exception as e:
        log.warning(f'清理上传临时文件失败: {e}')
    if removed:
        log.info(f'已清理 {removed} 个过期上传临时项')
    return removed
