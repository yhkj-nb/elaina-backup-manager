# plugins/备份工具/app/cloud.py
"""云盘备份模块

支持三类常见云盘协议:
- WebDAV     坚果云 / NextCloud / ownCloud / Koofr / Box / 群晖 Drive
- S3 兼容    AWS S3 / Cloudflare R2 / Backblaze B2 / MinIO / 阿里云 OSS / 腾讯云 COS
- FTP/SFTP   传统文件传输协议 (支持大量 NAS、虚拟主机)
"""

import asyncio
import copy
import ftplib
import hashlib
import hmac
import io
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp

from .constants import DATA_DIR, CLOUD_CONFIG_PATH
from .utils import log, format_size


# ==================== 配置管理 ====================


# 敏感字段在返回给前端时会被脱敏
SENSITIVE_FIELDS = {'password', 'secret_key', 'access_key_secret', 'token'}


def _mask_secrets(provider: Dict[str, Any]) -> Dict[str, Any]:
    """返回脱敏后的 provider 副本, 便于前端展示"""
    masked = copy.deepcopy(provider)
    for key, val in list(masked.items()):
        if key in SENSITIVE_FIELDS and isinstance(val, str) and val:
            masked[key] = '******' if len(val) <= 8 else val[:2] + '*' * (len(val) - 4) + val[-2:]
    return masked


def _ensure_config_dir():
    CLOUD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_cloud_config() -> Dict[str, Any]:
    """读取云盘配置文件; 不存在时返回默认结构"""
    if not CLOUD_CONFIG_PATH.exists():
        return {'providers': {}, 'last_used': None}
    try:
        import yaml
        with open(CLOUD_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {'providers': {}, 'last_used': None}
        data.setdefault('providers', {})
        data.setdefault('last_used', None)
        return data
    except Exception as e:
        log.error(f'读取云盘配置失败: {e}')
        return {'providers': {}, 'last_used': None}


def save_cloud_config(config: Dict[str, Any]) -> None:
    _ensure_config_dir()
    try:
        import yaml
        with open(CLOUD_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        log.error(f'保存云盘配置失败: {e}')


def list_providers_masked() -> List[Dict[str, Any]]:
    """返回所有 provider 的脱敏列表"""
    cfg = load_cloud_config()
    out = []
    for pid, p in (cfg.get('providers') or {}).items():
        item = _mask_secrets(p)
        item['id'] = pid
        out.append(item)
    return out


def get_provider_raw(pid: str) -> Optional[Dict[str, Any]]:
    cfg = load_cloud_config()
    return (cfg.get('providers') or {}).get(pid)


def gen_provider_id(name: str) -> str:
    base = ''.join(c.lower() if c.isalnum() else '_' for c in name)[:24] or 'cloud'
    suffix = datetime.now().strftime('%m%d%H%M%S')
    return f"{base}_{suffix}"


def upsert_provider(pid: Optional[str], data: Dict[str, Any]) -> Dict[str, Any]:
    """新增或更新 provider. 若 pid 为空则自动生成. 不传敏感字段时保留原值."""
    cfg = load_cloud_config()
    providers = cfg.setdefault('providers', {})

    if not pid:
        pid = gen_provider_id(data.get('name') or 'cloud')

    existing = providers.get(pid, {})
    merged = dict(existing)
    merged.update(data)
    merged['id'] = pid
    merged['updated_at'] = datetime.now().isoformat(timespec='seconds')

    # 空字符串敏感字段视为不修改, 保留原值
    for key in SENSITIVE_FIELDS:
        if key in merged and merged[key] in ('', '******'):
            merged[key] = existing.get(key, '')

    providers[pid] = merged
    cfg['last_used'] = pid
    save_cloud_config(cfg)
    return _mask_secrets(merged)


def delete_provider(pid: str) -> bool:
    cfg = load_cloud_config()
    providers = cfg.get('providers') or {}
    if pid not in providers:
        return False
    del providers[pid]
    if cfg.get('last_used') == pid:
        cfg['last_used'] = None
    save_cloud_config(cfg)
    return True


# ==================== Provider 抽象基类 ====================


class BaseCloudProvider:
    name = 'base'

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.label = config.get('name') or self.name

    async def test(self) -> Dict[str, Any]:
        raise NotImplementedError

    async def list_files(self, remote_path: str = '') -> List[Dict[str, Any]]:
        raise NotImplementedError

    async def upload_file(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def delete_file(self, remote_path: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def download_file(self, remote_path: str, local_path: Path) -> Dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _ok(message: str, **extra) -> Dict[str, Any]:
        return {'success': True, 'message': message, **extra}

    @staticmethod
    def _fail(message: str, **extra) -> Dict[str, Any]:
        return {'success': False, 'error': message, **extra}


# ==================== WebDAV Provider ====================


class WebDAVProvider(BaseCloudProvider):
    """WebDAV 协议: 坚果云 / NextCloud / ownCloud / Koofr / Box / 群晖 Drive"""

    name = 'webdav'

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        base_url = (config.get('url') or '').strip().rstrip('/')
        self.base_url = base_url
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        # 是否对整个 URL 用 Basic Auth (坚果云等支持, 部分服务对每个请求都校验)
        self.auth = aiohttp.BasicAuth(self.username, self.password) if self.username else None
        # 超时秒数
        self.timeout = aiohttp.ClientTimeout(total=int(config.get('timeout', 60)))

    def _full_url(self, remote_path: str) -> str:
        path = (remote_path or '').strip('/')
        return f"{self.base_url}/{quote(path)}" if path else f"{self.base_url}/"

    async def test(self) -> Dict[str, Any]:
        if not self.base_url:
            return self._fail('未配置 WebDAV URL')
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # 用 PROPFIND depth=0 探测, 既验证凭据又验证连通
                headers = {'Depth': '0', 'Content-Type': 'application/xml'}
                body = '<?xml version="1.0" encoding="utf-8"?>' \
                       '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
                async with session.request(
                    'PROPFIND', self.base_url, headers=headers, data=body, auth=self.auth, ssl=False
                ) as resp:
                    if resp.status in (200, 207):
                        return self._ok('连接成功', provider=self.name)
                    if resp.status == 401:
                        return self._fail('账号或密码错误 (401)')
                    if resp.status == 403:
                        return self._fail('无访问权限 (403)')
                    text = await resp.text()
                    return self._fail(f'连接失败: HTTP {resp.status}', status=resp.status, body=text[:200])
        except asyncio.TimeoutError:
            return self._fail('连接超时, 请检查网络或 URL')
        except aiohttp.ClientError as e:
            return self._fail(f'网络错误: {e}')
        except Exception as e:
            return self._fail(f'测试失败: {e}')

    async def _ensure_remote_dir(self, session: aiohttp.ClientSession, remote_path: str) -> None:
        """递归创建远端目录"""
        remote_path = (remote_path or '').strip('/')
        if not remote_path:
            return
        parts = remote_path.split('/')
        cur = ''
        for part in parts:
            if not part:
                continue
            cur = f"{cur}/{part}" if cur else part
            url = self._full_url(cur)
            async with session.request('MKCOL', url, auth=self.auth, ssl=False) as resp:
                # 201 创建成功, 405 已存在 - 均视为成功
                if resp.status not in (200, 201, 405):
                    log.debug(f'WebDAV MKCOL {cur} -> {resp.status}')

    async def list_files(self, remote_path: str = '') -> List[Dict[str, Any]]:
        if not self.base_url:
            return []
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                url = self._full_url(remote_path)
                headers = {'Depth': '1', 'Content-Type': 'application/xml'}
                body = '<?xml version="1.0" encoding="utf-8"?>' \
                       '<d:propfind xmlns:d="DAV:">' \
                       '<d:prop><d:resourcetype/><d:displayname/><d:getcontentlength/>' \
                       '<d:getlastmodified/></d:prop></d:propfind>'
                async with session.request(
                    'PROPFIND', url, headers=headers, data=body, auth=self.auth, ssl=False
                ) as resp:
                    if resp.status not in (200, 207):
                        log.warning(f'WebDAV 列表失败: HTTP {resp.status}')
                        return []
                    text = await resp.text()
                    return self._parse_propfind(text)
        except Exception as e:
            log.error(f'WebDAV 列表失败: {e}')
            return []

    @staticmethod
    def _parse_propfind(xml_text: str) -> List[Dict[str, Any]]:
        """解析 PROPFIND 多状态响应, 仅返回非当前目录的子项"""
        try:
            import xml.etree.ElementTree as ET
            ns = {'d': 'DAV:'}
            root = ET.fromstring(xml_text)
            items: List[Dict[str, Any]] = []
            for resp in root.findall('d:response', ns):
                href_el = resp.find('d:href', ns)
                if href_el is None or not href_el.text:
                    continue
                propstat = resp.find('d:propstat', ns)
                if propstat is None:
                    continue
                prop = propstat.find('d:prop', ns)
                if prop is None:
                    continue
                name_el = prop.find('d:displayname', ns)
                size_el = prop.find('d:getcontentlength', ns)
                mtime_el = prop.find('d:getlastmodified', ns)
                rtype = prop.find('d:resourcetype', ns)
                is_dir = rtype is not None and rtype.find('d:collection', ns) is not None
                # 跳过当前目录自身 (以 / 结尾且无 name)
                name = (name_el.text if name_el is not None and name_el.text else '').strip()
                if not name:
                    # 用 href 推断
                    href_path = href_el.text.rstrip('/')
                    name = href_path.rsplit('/', 1)[-1] if '/' in href_path else href_path
                    if not name:
                        continue
                size = int(size_el.text) if size_el is not None and size_el.text and size_el.text.isdigit() else 0
                mtime = mtime_el.text if mtime_el is not None and mtime_el.text else ''
                items.append({
                    'name': name, 'size': size, 'size_readable': format_size(size),
                    'is_dir': is_dir, 'modified': mtime,
                })
            return items
        except Exception as e:
            log.error(f'解析 WebDAV 响应失败: {e}')
            return []

    async def upload_file(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        if not self.base_url:
            return self._fail('未配置 WebDAV URL')
        if not local_path.exists() or not local_path.is_file():
            return self._fail(f'本地文件不存在: {local_path}')
        # 拆分远端目录与文件名
        remote_path = (remote_path or '').strip('/')
        if '/' in remote_path:
            remote_dir, remote_name = remote_path.rsplit('/', 1)
        else:
            remote_dir, remote_name = '', remote_path
        try:
            size = local_path.stat().st_size
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
                if remote_dir:
                    await self._ensure_remote_dir(session, remote_dir)
                url = self._full_url(remote_path)
                # 分块上传避免大文件 OOM
                async def file_sender():
                    with open(local_path, 'rb') as f:
                        while True:
                            chunk = f.read(64 * 1024)
                            if not chunk:
                                break
                            yield chunk
                headers = {'Content-Type': 'application/octet-stream'}
                async with session.put(
                    url, data=file_sender(), headers=headers, auth=self.auth, ssl=False
                ) as resp:
                    if resp.status in (200, 201, 204):
                        log.info(f'☁️ WebDAV 上传成功: {remote_name} ({format_size(size)})')
                        return self._ok('上传成功', remote_path=remote_path, size=size,
                                        size_readable=format_size(size))
                    text = await resp.text()
                    return self._fail(f'上传失败: HTTP {resp.status}', body=text[:200])
        except Exception as e:
            log.error(f'WebDAV 上传失败: {e}')
            return self._fail(f'上传异常: {e}')

    async def delete_file(self, remote_path: str) -> Dict[str, Any]:
        if not self.base_url:
            return self._fail('未配置 WebDAV URL')
        remote_path = (remote_path or '').strip('/')
        if not remote_path:
            return self._fail('远端路径为空, 拒绝删除')
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                url = self._full_url(remote_path)
                async with session.delete(url, auth=self.auth, ssl=False) as resp:
                    if resp.status in (200, 204):
                        return self._ok('已删除', remote_path=remote_path)
                    if resp.status == 404:
                        return self._fail('远端文件不存在', status=404)
                    text = await resp.text()
                    return self._fail(f'删除失败: HTTP {resp.status}', body=text[:200])
        except Exception as e:
            log.error(f'WebDAV 删除失败: {e}')
            return self._fail(f'删除异常: {e}')

    async def download_file(self, remote_path: str, local_path: Path) -> Dict[str, Any]:
        if not self.base_url:
            return self._fail('未配置 WebDAV URL')
        remote_path = (remote_path or '').strip('/')
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
                url = self._full_url(remote_path)
                async with session.get(url, auth=self.auth, ssl=False) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return self._fail(f'下载失败: HTTP {resp.status}', body=text[:200])
                    size = 0
                    with open(local_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            f.write(chunk)
                            size += len(chunk)
                    return self._ok('下载成功', local_path=str(local_path),
                                    size=size, size_readable=format_size(size))
        except Exception as e:
            log.error(f'WebDAV 下载失败: {e}')
            return self._fail(f'下载异常: {e}')


# ==================== S3 兼容 Provider ====================


class S3Provider(BaseCloudProvider):
    """S3 兼容协议: AWS S3 / Cloudflare R2 / Backblaze B2 / MinIO / 阿里云 OSS / 腾讯云 COS

    使用 AWS Signature V4 直接通过 HTTP 调用, 不依赖 boto3.
    """

    name = 's3'
    SERVICE = 's3'  # 阿里云 OSS 也用 s3, 腾讯云 COS 用 cos, 通过 config.service 覆盖

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.endpoint = (config.get('endpoint') or '').strip().rstrip('/')
        self.region = config.get('region', 'us-east-1')
        self.bucket = (config.get('bucket') or '').strip()
        self.access_key = config.get('access_key', '')
        self.secret_key = config.get('secret_key', '')
        # service 名: 默认 s3, 腾讯云 COS 用 cos, 阿里云 OSS 用 oss
        self.service = config.get('service') or 's3'
        # 是否使用 path-style (MinIO / 阿里云 / 自建 必须为 true)
        self.path_style = bool(config.get('path_style', True))
        self.timeout = aiohttp.ClientTimeout(total=int(config.get('timeout', 60)))

    # ---------- SigV4 签名 ----------

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    def _sign_key(self, date_stamp: str, region: str, service: str, secret: str) -> bytes:
        k_date = self._hmac(('AWS4' + secret).encode('latin-1'), date_stamp)
        k_region = self._hmac(k_date, region)
        k_service = self._hmac(k_region, service)
        return self._hmac(k_service, 'aws4_request')

    def _build_request(self, method: str, key: str, payload: bytes = b'',
                       extra_headers: Optional[Dict[str, str]] = None,
                       query: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """构造一个已签名的请求参数字典 (供 aiohttp 使用)"""
        now = datetime.now(timezone.utc)
        amz_date = now.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = now.strftime('%Y%m%d')
        region = self.region
        service = self.service

        host = urlsplit(self.endpoint).netloc
        scheme = urlsplit(self.endpoint).scheme or 'https'

        # canonical uri: path-style 时为 /bucket/key, virtual-host 时为 /key
        canonical_uri = f"/{self.bucket}/{key.lstrip('/')}" if self.path_style else f"/{key.lstrip('/')}"
        canonical_uri = quote(canonical_uri, safe='/')

        # canonical query
        q = dict(query or {})
        canonical_query = '&'.join(f"{quote(k, safe='')}={quote(str(v), safe='')}" for k, v in sorted(q.items()))

        # headers
        headers = {
            'host': host,
            'x-amz-date': amz_date,
            'x-amz-content-sha256': self._sha256(payload),
            **(extra_headers or {}),
        }
        signed_header_keys = ';'.join(sorted(headers.keys()))
        canonical_headers = ''.join(f"{k.lower()}:{v.strip()}\n" for k, v in sorted(headers.items()))

        payload_hash = self._sha256(payload)
        canonical_request = '\n'.join([
            method.upper(), canonical_uri, canonical_query,
            canonical_headers, signed_header_keys, payload_hash,
        ])

        scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = '\n'.join([
            'AWS4-HMAC-SHA256', amz_date, scope, self._sha256(canonical_request.encode('utf-8')),
        ])
        signing_key = self._sign_key(date_stamp, region, service, self.secret_key)
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

        auth = (
            f"AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_header_keys}, "
            f"Signature={signature}"
        )
        # 实际请求头 (host 由 aiohttp 自动管理, 不发送)
        req_headers = {k: v for k, v in headers.items() if k.lower() != 'host'}
        req_headers['Authorization'] = auth

        # 完整 URL
        path = canonical_uri
        url = f"{scheme}://{host}{path}"
        if canonical_query:
            url += f"?{canonical_query}"
        return {'url': url, 'headers': req_headers, 'data': payload if payload else None}

    async def _do_request(self, method: str, key: str, payload: bytes = b'',
                          extra_headers: Optional[Dict[str, str]] = None,
                          query: Optional[Dict[str, str]] = None,
                          timeout: Optional[aiohttp.ClientTimeout] = None) -> Dict[str, Any]:
        req = self._build_request(method, key, payload, extra_headers, query)
        try:
            async with aiohttp.ClientSession(timeout=timeout or self.timeout) as session:
                async with session.request(
                    method, req['url'], headers=req['headers'], data=req['data'], ssl=False
                ) as resp:
                    body = await resp.read()
                    return {
                        'status': resp.status,
                        'body': body,
                        'headers': dict(resp.headers),
                    }
        except Exception as e:
            return {'status': 0, 'body': str(e).encode('utf-8'), 'headers': {}}

    # ---------- 公共方法 ----------

    async def test(self) -> Dict[str, Any]:
        if not self.endpoint or not self.bucket:
            return self._fail('未配置 endpoint 或 bucket')
        try:
            # ListObjectsV2 限制 1 条, 既验证凭据又验证 bucket
            r = await self._do_request('GET', '', query={'list-type': '2', 'max-keys': '1'})
            if r['status'] == 200:
                return self._ok('连接成功', provider=self.name)
            if r['status'] in (403, 401):
                return self._fail('Access Key 或 Secret 错误', status=r['status'])
            if r['status'] == 404:
                return self._fail('Bucket 不存在或路径错误', status=404)
            text = r['body'][:200].decode('utf-8', errors='replace')
            return self._fail(f'连接失败: HTTP {r["status"]}', body=text)
        except Exception as e:
            return self._fail(f'测试失败: {e}')

    @staticmethod
    def _parse_list_xml(xml_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            import xml.etree.ElementTree as ET
            ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}
            root = ET.fromstring(xml_bytes.decode('utf-8', errors='replace'))
            items = []
            for c in root.findall('s3:Contents', ns):
                key_el = c.find('s3:Key', ns)
                size_el = c.find('s3:Size', ns)
                mtime_el = c.find('s3:LastModified', ns)
                if key_el is None:
                    continue
                key = key_el.text or ''
                size = int(size_el.text) if size_el is not None and size_el.text and size_el.text.isdigit() else 0
                mtime = mtime_el.text if mtime_el is not None and mtime_el.text else ''
                items.append({
                    'name': key.rsplit('/', 1)[-1] if '/' in key else key,
                    'key': key, 'size': size, 'size_readable': format_size(size),
                    'is_dir': key.endswith('/'), 'modified': mtime,
                })
            return items
        except Exception as e:
            log.error(f'解析 S3 列表失败: {e}')
            return []

    async def list_files(self, remote_path: str = '') -> List[Dict[str, Any]]:
        prefix = (remote_path or '').strip('/')
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        query = {'list-type': '2'}
        if prefix:
            query['prefix'] = prefix
        r = await self._do_request('GET', '', query=query)
        if r['status'] != 200:
            log.warning(f'S3 列表失败: HTTP {r["status"]}')
            return []
        return self._parse_list_xml(r['body'])

    async def upload_file(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        if not self.endpoint or not self.bucket:
            return self._fail('未配置 endpoint 或 bucket')
        if not local_path.exists() or not local_path.is_file():
            return self._fail(f'本地文件不存在: {local_path}')
        try:
            size = local_path.stat().st_size
            with open(local_path, 'rb') as f:
                payload = f.read()
            key = (remote_path or '').lstrip('/')
            extra_headers = {'Content-Type': 'application/zip'}
            r = await self._do_request(
                'PUT', key, payload=payload, extra_headers=extra_headers,
                timeout=aiohttp.ClientTimeout(total=600)
            )
            if r['status'] in (200, 201):
                log.info(f'☁️ S3 上传成功: {key} ({format_size(size)})')
                return self._ok('上传成功', remote_path=key, size=size,
                                size_readable=format_size(size))
            text = r['body'][:200].decode('utf-8', errors='replace')
            return self._fail(f'上传失败: HTTP {r["status"]}', body=text)
        except Exception as e:
            log.error(f'S3 上传失败: {e}')
            return self._fail(f'上传异常: {e}')

    async def delete_file(self, remote_path: str) -> Dict[str, Any]:
        if not self.endpoint or not self.bucket:
            return self._fail('未配置 endpoint 或 bucket')
        key = (remote_path or '').lstrip('/')
        if not key:
            return self._fail('远端路径为空, 拒绝删除')
        try:
            r = await self._do_request('DELETE', key)
            if r['status'] in (200, 204):
                return self._ok('已删除', remote_path=key)
            if r['status'] == 404:
                return self._fail('远端文件不存在', status=404)
            text = r['body'][:200].decode('utf-8', errors='replace')
            return self._fail(f'删除失败: HTTP {r["status"]}', body=text)
        except Exception as e:
            log.error(f'S3 删除失败: {e}')
            return self._fail(f'删除异常: {e}')

    async def download_file(self, remote_path: str, local_path: Path) -> Dict[str, Any]:
        if not self.endpoint or not self.bucket:
            return self._fail('未配置 endpoint 或 bucket')
        key = (remote_path or '').lstrip('/')
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            r = await self._do_request('GET', key, timeout=aiohttp.ClientTimeout(total=600))
            if r['status'] != 200:
                text = r['body'][:200].decode('utf-8', errors='replace')
                return self._fail(f'下载失败: HTTP {r["status"]}', body=text)
            with open(local_path, 'wb') as f:
                f.write(r['body'])
            return self._ok('下载成功', local_path=str(local_path),
                            size=len(r['body']), size_readable=format_size(len(r['body'])))
        except Exception as e:
            log.error(f'S3 下载失败: {e}')
            return self._fail(f'下载异常: {e}')


# ==================== FTP Provider ====================


class FTPProvider(BaseCloudProvider):
    """FTP 协议: 支持 NAS、虚拟主机、传统 FTP 服务器"""

    name = 'ftp'

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.host = (config.get('host') or '').strip()
        self.port = int(config.get('port', 21))
        self.username = config.get('username', '')
        self.password = config.get('password', '')
        # 是否使用 SFTP (需要 pysftp/paramiko; 此处仅 FTP, sftp 字段保留以兼容)
        self.use_tls = bool(config.get('use_tls', False))
        self.timeout = int(config.get('timeout', 30))

    def _connect(self) -> ftplib.FTP:
        if self.use_tls:
            ftp = ftplib.FTP_TLS(timeout=self.timeout)
        else:
            ftp = ftplib.FTP(timeout=self.timeout)
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.username, self.password)
        if self.use_tls:
            try:
                ftp.prot_p()
            except Exception:
                pass
        return ftp

    @staticmethod
    async def _run(coro_or_func, *args, **kwargs):
        """把同步 FTP 操作放到线程池执行"""
        loop = asyncio.get_event_loop()
        if callable(coro_or_func):
            return await loop.run_in_executor(None, lambda: coro_or_func(*args, **kwargs))
        return await coro_or_func

    def _test_sync(self) -> Dict[str, Any]:
        if not self.host:
            return self._fail('未配置 FTP 主机')
        try:
            ftp = self._connect()
            welcome = ftp.getwelcome()
            ftp.quit()
            return self._ok('连接成功', provider=self.name, banner=welcome[:120])
        except ftplib.error_perm as e:
            return self._fail(f'认证失败: {e}')
        except ftplib.all_errors as e:
            return self._fail(f'FTP 错误: {e}')
        except socket.timeout:
            return self._fail('连接超时')
        except Exception as e:
            return self._fail(f'测试失败: {e}')

    async def test(self) -> Dict[str, Any]:
        return await self._run(self._test_sync)

    def _list_sync(self, remote_path: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        try:
            ftp = self._connect()
            try:
                remote_path = (remote_path or '').strip() or '/'
                lines: List[str] = []
                ftp.cwd(remote_path)
                ftp.retrlines('LIST', lines.append)
                for line in lines:
                    parts = line.split(None, 8)
                    if len(parts) < 9:
                        continue
                    perms, size, name = parts[0], parts[4], parts[8]
                    is_dir = perms.startswith('d')
                    sz = int(size) if size.isdigit() else 0
                    items.append({
                        'name': name, 'size': sz, 'size_readable': format_size(sz),
                        'is_dir': is_dir, 'modified': ' '.join(parts[5:8]),
                    })
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass
        except Exception as e:
            log.error(f'FTP 列表失败: {e}')
        return items

    async def list_files(self, remote_path: str = '') -> List[Dict[str, Any]]:
        return await self._run(self._list_sync, remote_path)

    def _ensure_dir_sync(self, ftp: ftplib.FTP, remote_path: str) -> None:
        remote_path = (remote_path or '').strip('/')
        if not remote_path:
            return
        cur = ''
        for part in remote_path.split('/'):
            if not part:
                continue
            cur = f"{cur}/{part}" if cur else part
            try:
                ftp.mkd(cur)
            except ftplib.error_perm:
                # 目录已存在
                pass

    def _upload_sync(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        if not local_path.exists() or not local_path.is_file():
            return self._fail(f'本地文件不存在: {local_path}')
        try:
            size = local_path.stat().st_size
            ftp = self._connect()
            try:
                remote_path = (remote_path or '').strip('/')
                if '/' in remote_path:
                    remote_dir, remote_name = remote_path.rsplit('/', 1)
                    self._ensure_dir_sync(ftp, remote_dir)
                    if remote_dir:
                        ftp.cwd(f"/{remote_dir}")
                else:
                    remote_name = remote_path
                with open(local_path, 'rb') as f:
                    ftp.storbinary(f'STOR {remote_name}', f)
                log.info(f'☁️ FTP 上传成功: {remote_name} ({format_size(size)})')
                return self._ok('上传成功', remote_path=remote_path,
                                size=size, size_readable=format_size(size))
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass
        except ftplib.all_errors as e:
            return self._fail(f'FTP 上传失败: {e}')
        except Exception as e:
            return self._fail(f'上传异常: {e}')

    async def upload_file(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        return await self._run(self._upload_sync, local_path, remote_path)

    def _delete_sync(self, remote_path: str) -> Dict[str, Any]:
        remote_path = (remote_path or '').strip('/')
        if not remote_path:
            return self._fail('远端路径为空, 拒绝删除')
        try:
            ftp = self._connect()
            try:
                ftp.delete(remote_path)
                return self._ok('已删除', remote_path=remote_path)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass
        except ftplib.error_perm as e:
            if '550' in str(e):
                return self._fail('远端文件不存在', status=404)
            return self._fail(f'删除失败: {e}')
        except Exception as e:
            return self._fail(f'删除异常: {e}')

    async def delete_file(self, remote_path: str) -> Dict[str, Any]:
        return await self._run(self._delete_sync, remote_path)

    def _download_sync(self, remote_path: str, local_path: Path) -> Dict[str, Any]:
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            ftp = self._connect()
            size = 0
            try:
                with open(local_path, 'wb') as f:
                    def _cb(chunk: bytes) -> None:
                        nonlocal size
                        f.write(chunk)
                        size += len(chunk)
                    ftp.retrbinary(f'RETR {remote_path.lstrip("/")}', _cb)
                return self._ok('下载成功', local_path=str(local_path),
                                size=size, size_readable=format_size(size))
            finally:
                try:
                    ftp.quit()
                except Exception:
                    pass
        except ftplib.error_perm as e:
            if '550' in str(e):
                return self._fail('远端文件不存在', status=404)
            return self._fail(f'下载失败: {e}')
        except Exception as e:
            return self._fail(f'下载异常: {e}')

    async def download_file(self, remote_path: str, local_path: Path) -> Dict[str, Any]:
        return await self._run(self._download_sync, remote_path, local_path)


# ==================== 工厂与管理器 ====================


_PROVIDER_CLASSES = {
    'webdav': WebDAVProvider,
    's3': S3Provider,
    'ftp': FTPProvider,
}


def build_provider(pid: str) -> Optional[BaseCloudProvider]:
    cfg = get_provider_raw(pid)
    if not cfg:
        return None
    ptype = (cfg.get('type') or '').lower()
    cls = _PROVIDER_CLASSES.get(ptype)
    if not cls:
        log.error(f'不支持的云盘类型: {ptype}')
        return None
    return cls(cfg)


def provider_schema() -> Dict[str, Any]:
    """返回前端用于渲染表单的 schema (按类型列出字段)"""
    return {
        'webdav': {
            'label': 'WebDAV (坚果云 / NextCloud / ownCloud / Koofr / 群晖)',
            'fields': [
                {'name': 'name', 'label': '显示名称', 'type': 'text', 'required': True, 'placeholder': '我的坚果云'},
                {'name': 'url', 'label': 'WebDAV URL', 'type': 'text', 'required': True,
                 'placeholder': 'https://dav.jianguoyun.com/dav/'},
                {'name': 'username', 'label': '账号', 'type': 'text', 'required': True,
                 'placeholder': 'user@example.com'},
                {'name': 'password', 'label': '密码 / 应用密码', 'type': 'password', 'required': True,
                 'placeholder': '坚果云请使用应用密码'},
                {'name': 'timeout', 'label': '超时 (秒)', 'type': 'number', 'default': 60},
            ],
        },
        's3': {
            'label': 'S3 兼容 (AWS S3 / R2 / B2 / MinIO / 阿里云 OSS / 腾讯云 COS)',
            'fields': [
                {'name': 'name', 'label': '显示名称', 'type': 'text', 'required': True, 'placeholder': '我的 R2'},
                {'name': 'endpoint', 'label': 'Endpoint', 'type': 'text', 'required': True,
                 'placeholder': 'https://s3.us-east-1.amazonaws.com'},
                {'name': 'region', 'label': 'Region', 'type': 'text', 'required': True,
                 'placeholder': 'us-east-1'},
                {'name': 'bucket', 'label': 'Bucket', 'type': 'text', 'required': True,
                 'placeholder': 'my-backup-bucket'},
                {'name': 'access_key', 'label': 'Access Key', 'type': 'text', 'required': True},
                {'name': 'secret_key', 'label': 'Secret Key', 'type': 'password', 'required': True},
                {'name': 'service', 'label': 'Service (s3 / oss / cos)', 'type': 'text', 'default': 's3'},
                {'name': 'path_style', 'label': 'Path-Style (MinIO / 自建建议开)', 'type': 'checkbox', 'default': True},
                {'name': 'timeout', 'label': '超时 (秒)', 'type': 'number', 'default': 60},
            ],
        },
        'ftp': {
            'label': 'FTP / FTPS (NAS / 虚拟主机 / 传统 FTP)',
            'fields': [
                {'name': 'name', 'label': '显示名称', 'type': 'text', 'required': True, 'placeholder': '我的 NAS'},
                {'name': 'host', 'label': '主机地址', 'type': 'text', 'required': True, 'placeholder': 'ftp.example.com'},
                {'name': 'port', 'label': '端口', 'type': 'number', 'default': 21},
                {'name': 'username', 'label': '用户名', 'type': 'text', 'required': True},
                {'name': 'password', 'label': '密码', 'type': 'password', 'required': True},
                {'name': 'use_tls', 'label': '启用 FTPS (TLS)', 'type': 'checkbox', 'default': False},
                {'name': 'timeout', 'label': '超时 (秒)', 'type': 'number', 'default': 30},
            ],
        },
    }


# ==================== 高层操作 ====================


def _build_remote_path(provider_cfg: Dict[str, Any], filename: str) -> str:
    """根据 provider 的 remote_path 设置拼出远端路径"""
    base = (provider_cfg.get('remote_path') or '').strip('/')
    if base:
        return f"{base}/{filename}" if base else filename
    return filename


async def upload_backup_to_cloud(pid: str, filename: str) -> Dict[str, Any]:
    """把本地 DATA_DIR 下的备份文件上传到指定云盘"""
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return {'success': False, 'error': '非法文件名'}
    local_path = DATA_DIR / filename
    if not local_path.exists() or not local_path.is_file():
        return {'success': False, 'error': '本地备份文件不存在'}
    provider_cfg = get_provider_raw(pid)
    if not provider_cfg:
        return {'success': False, 'error': '云盘配置不存在'}
    provider = build_provider(pid)
    if not provider:
        return {'success': False, 'error': '云盘类型不支持'}
    remote_path = _build_remote_path(provider_cfg, filename)
    result = await provider.upload_file(local_path, remote_path)
    if result.get('success'):
        # 记录同步状态
        _record_sync(pid, filename, remote_path, result.get('size', 0))
    return result


async def list_cloud_backups(pid: str, remote_path: str = '') -> Dict[str, Any]:
    """列出云盘上的备份文件"""
    provider_cfg = get_provider_raw(pid)
    if not provider_cfg:
        return {'success': False, 'error': '云盘配置不存在'}
    provider = build_provider(pid)
    if not provider:
        return {'success': False, 'error': '云盘类型不支持'}
    if not remote_path:
        remote_path = provider_cfg.get('remote_path', '') or ''
    files = await provider.list_files(remote_path)
    # 只展示 zip 文件
    zip_files = [f for f in files if (f.get('name') or '').lower().endswith('.zip')]
    return {'success': True, 'files': zip_files, 'count': len(zip_files), 'all_files': files}


async def download_cloud_backup(pid: str, remote_path: str) -> Dict[str, Any]:
    """从云盘下载备份到本地 DATA_DIR"""
    if not remote_path:
        return {'success': False, 'error': '远端路径为空'}
    provider = build_provider(pid)
    if not provider:
        return {'success': False, 'error': '云盘类型不支持'}
    name = remote_path.rsplit('/', 1)[-1]
    if not name.lower().endswith('.zip'):
        return {'success': False, 'error': '仅支持 ZIP 文件'}
    if '..' in name or '/' in name or '\\' in name:
        return {'success': False, 'error': '非法文件名'}
    local_path = DATA_DIR / f"cloud_{name}"
    return await provider.download_file(remote_path, local_path)


async def delete_cloud_backup(pid: str, remote_path: str) -> Dict[str, Any]:
    provider = build_provider(pid)
    if not provider:
        return {'success': False, 'error': '云盘类型不支持'}
    return await provider.delete_file(remote_path)


# ==================== 同步状态记录 ====================


def _state_path() -> Path:
    return DATA_DIR / 'cloud_sync_state.json'


def _load_state() -> Dict[str, Any]:
    p = _state_path()
    if not p.exists():
        return {'syncs': {}}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f) or {'syncs': {}}
    except Exception:
        return {'syncs': {}}


def _save_state(state: Dict[str, Any]) -> None:
    try:
        with open(_state_path(), 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f'保存云盘同步状态失败: {e}')


def _record_sync(pid: str, filename: str, remote_path: str, size: int) -> None:
    state = _load_state()
    syncs = state.setdefault('syncs', {})
    syncs[f"{pid}::{filename}"] = {
        'provider_id': pid,
        'filename': filename,
        'remote_path': remote_path,
        'size': size,
        'size_readable': format_size(size),
        'synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _save_state(state)


def get_sync_state() -> Dict[str, Any]:
    return _load_state().get('syncs', {})
