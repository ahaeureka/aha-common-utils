"""HttpProxyServer — 反爬感知的 HTTP 正向代理服务器。

客户端（如 SearXNG 的 ``outgoing.proxies``）指向本代理。普通 HTTP 请求直接
经 ``HttpFetchPort`` 转发；CONNECT 隧道在提供 ``CertificateAuthority`` 时做
MITM 拦截（终止 TLS 后用反检测策略链重新发起上游请求），否则透传字节隧道。

上游转发复用 http_fetch 全栈：AntiDetectionManager 策略链（curl-cffi →
httpx → 浏览器策略）、AntiCrawlDetector 反爬检测、ProxyManager 出口代理轮换
与 AutoPlanningEngine 自适应限流。本类只做 HTTP 前端，业务无关。
"""

from __future__ import annotations

import asyncio
import ssl
from abc import ABC, abstractmethod
from urllib.parse import urlsplit

from aha_common_utils.http_fetch.anti_detection import AntiDetectionManager
from aha_common_utils.logging import get_logger
from aha_common_utils.ports.http_fetch import HttpFetchPort, HttpFetchRequest

logger = get_logger(__name__)

_HOP_BY_HOP_HEADERS = {
    "connection",
    "proxy-connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
}

_DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024

_REASON_PHRASES = {
    200: "OK",
    301: "Moved Permanently",
    302: "Found",
    403: "Forbidden",
    404: "Not Found",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


class HttpProxyError(RuntimeError):
    """代理层错误（请求解析失败、体超限等）。"""


def _netloc_host(url: str) -> str:
    """从 URL 提取主机名。"""
    return urlsplit(url).hostname or ""


class CertificateAuthority(ABC):
    """签发 MITM 目标域名证书的抽象。"""

    @abstractmethod
    def get_leaf_cert(self, host: str) -> tuple[str, str]:
        """返回目标域名的 ``(cert_path, key_path)``。"""


class HttpProxyServer:
    """反爬感知的 HTTP 正向代理服务器。

    Args:
        http_fetch: 上游转发端口；默认使用 AntiDetectionManager 策略链。
        host: 监听地址（默认仅本机）。
        port: 监听端口；``0`` 表示随机端口（见 :attr:`bound_port`）。
        ca: 提供后 CONNECT 隧道做 MITM 拦截；为 ``None`` 时透传字节隧道。
        request_timeout_seconds: 上游请求超时。
        log_body: 是否在日志中记录请求体（默认关闭，避免敏感数据）。
        max_body_bytes: 单请求体上限，防内存耗尽。
        max_concurrency: 最大并发连接数。
    """

    def __init__(
        self,
        http_fetch: HttpFetchPort | None = None,
        *,
        host: str = "127.0.0.1",
        port: int = 8090,
        ca: CertificateAuthority | None = None,
        request_timeout_seconds: float = 30.0,
        log_body: bool = False,
        max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
        max_concurrency: int = 64,
    ) -> None:
        self._http_fetch = http_fetch or AntiDetectionManager()
        self._host = host
        self._port = port
        self._ca = ca
        self._request_timeout_seconds = request_timeout_seconds
        self._log_body = log_body
        self._max_body_bytes = max_body_bytes
        self._semaphore = asyncio.Semaphore(max(max_concurrency, 1))
        self._server: asyncio.Server | None = None
        self._stats: dict[str, int] = {
            "requests": 0,
            "tunnels": 0,
            "mitm_intercepts": 0,
            "errors": 0,
        }

    @property
    def bound_port(self) -> int:
        """实际监听的端口（``port=0`` 时随机分配）。"""
        if self._server is not None and self._server.sockets:
            return int(self._server.sockets[0].getsockname()[1])
        return self._port

    def stats(self) -> dict[str, int]:
        """代理运行统计（只读视图）。"""
        return dict(self._stats)

    # ── 生命周期 ────────────────────────────────────────────────────

    async def start(self) -> None:
        """启动代理服务。"""
        self._server = await asyncio.start_server(self._handle_client, self._host, self._port)
        logger.info("HttpProxyServer listening on %s:%s (mitm=%s)", self._host, self.bound_port, self._ca is not None)

    async def stop(self) -> None:
        """停止代理服务并等待连接关闭。"""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def close(self) -> None:
        """停止服务并关闭上游端口资源。"""
        await self.stop()
        close_fn = getattr(self._http_fetch, "close", None)
        if close_fn is not None:
            await close_fn()

    async def __aenter__(self) -> HttpProxyServer:
        await self.start()
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        await self.stop()

    # ── 客户端连接处理 ───────────────────────────────────────────────

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with self._semaphore:
            try:
                first_line = await self._read_line(reader)
                if not first_line:
                    return
                parts = first_line.split()
                if len(parts) < 3:
                    return
                method, target = parts[0].decode("latin-1"), parts[1].decode("latin-1")

                if method.upper() == "CONNECT":
                    await self._handle_connect(reader, writer, target, first_line)
                else:
                    await self._handle_plain_http(reader, writer, method, target, first_line)
            except (ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
                pass
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                logger.debug("proxy client error: %r", exc)
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

    # ── CONNECT 处理 ─────────────────────────────────────────────────

    async def _handle_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        target: str,
        first_line: bytes,
    ) -> None:
        """CONNECT host:port → 消费请求头 → MITM 或透传隧道。"""
        request = await self._read_request(reader, first_line)
        if request is None:
            return

        host, _, port_str = target.rpartition(":")
        port = int(port_str or 443)
        if self._ca is None:
            await self._tunnel_connect(reader, writer, host, port)
            return

        cert_path, key_path = self._ca.get_leaf_cert(host)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        context.set_alpn_protocols(["http/1.1"])

        try:
            writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            await writer.drain()
            loop = asyncio.get_event_loop()
            protocol = asyncio.StreamReaderProtocol(reader)
            tls_transport = await loop.start_tls(
                writer.transport,
                protocol,
                sslcontext=context,
                server_side=True,
            )
            setattr(reader, "_transport", tls_transport)  # noqa: B010  # asyncio 内部惯例
            tls_writer = asyncio.StreamWriter(tls_transport, protocol, reader, loop)  # type: ignore[arg-type]
        except (ConnectionError, ssl.SSLError, asyncio.IncompleteReadError):
            return
        except Exception as exc:  # noqa: BLE001
            self._stats["errors"] += 1
            logger.error("CONNECT/TLS setup failed for %s: %r", host, exc)
            return

        self._stats["mitm_intercepts"] += 1
        try:
            while True:
                line = await self._read_line(reader)
                if not line:
                    logger.debug("tunnel closed by client: %s", host)
                    break
                inner = await self._read_request(reader, line)
                if inner is None:
                    break
                method, path, headers, body = inner
                url = f"https://{host}:{port}{path}"
                await self._dispatch(tls_writer, url, method, headers, body, host)
        except (ConnectionError, asyncio.IncompleteReadError, ssl.SSLError):
            pass
        except Exception as exc:  # noqa: BLE001
            self._stats["errors"] += 1
            logger.error("tunnel loop error for %s: %r", host, exc)
        finally:
            try:
                tls_transport.close()  # type: ignore[union-attr]
            except Exception:
                pass

    async def _tunnel_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        """CONNECT 透传字节隧道（不做 MITM 拦截）。"""
        self._stats["tunnels"] += 1
        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        except Exception as exc:  # noqa: BLE001
            self._stats["errors"] += 1
            logger.error("tunnel target unreachable %s:%s: %r", host, port, exc)
            await self._write_response(writer, 502, b"")
            return

        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()

        async def _pump(source: asyncio.StreamReader, sink: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await source.read(64 * 1024)
                    if not data:
                        break
                    sink.write(data)
                    await sink.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                try:
                    sink.close()
                except Exception:
                    pass

        await asyncio.gather(_pump(reader, remote_writer), _pump(remote_reader, writer), return_exceptions=True)
        try:
            remote_writer.close()
        except Exception:
            pass

    # ── 普通 HTTP 处理 ──────────────────────────────────────────────

    async def _handle_plain_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        method: str,
        target: str,
        first_line: bytes,
    ) -> None:
        """处理绝对 URI 或 origin-form 的普通 HTTP 代理请求。"""
        request = await self._read_request(reader, first_line)
        if request is None:
            return
        _method, path, headers, body = request
        if target.startswith(("http://", "https://")):
            url = target
        else:
            host = headers.get("host", "")
            url = f"http://{host}{path}"
        await self._dispatch(writer, url, method, headers, body, _netloc_host(url))

    # ── 请求解析 ────────────────────────────────────────────────────

    async def _read_request(
        self,
        reader: asyncio.StreamReader,
        first_line: bytes | None,
    ) -> tuple[str, str, dict[str, str], bytes] | None:
        """读取一个 HTTP 请求：``(method, path, headers, body)``。"""
        if first_line is None:
            first_line = await self._read_line(reader)
            if not first_line:
                return None
        parts = first_line.split()
        if len(parts) < 3:
            logger.debug("bad request line: %r", first_line[:80])
            return None
        method, path = parts[0].decode("latin-1"), parts[1].decode("latin-1")
        headers: dict[str, str] = {}
        while True:
            line = await self._read_line(reader)
            if not line:
                break
            try:
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            except Exception:
                break
        body = b""
        length = int(headers.get("content-length", "0") or 0)
        if length > 0:
            if length > self._max_body_bytes:
                raise HttpProxyError(f"request body too large: {length}")
            body = await reader.readexactly(length)
        return method, path, headers, body

    # ── 上游转发 ────────────────────────────────────────────────────

    async def _dispatch(
        self,
        writer: asyncio.StreamWriter,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        domain: str,
    ) -> None:
        """经 HttpFetchPort 转发上游请求并回写响应。"""
        self._stats["requests"] += 1
        clean_headers = {key: value for key, value in headers.items() if key not in _HOP_BY_HOP_HEADERS}
        try:
            response = await self._http_fetch.fetch(
                HttpFetchRequest(
                    url=url,
                    method=method,
                    headers=clean_headers,
                    body=body or None,
                    timeout_seconds=self._request_timeout_seconds,
                    domain=domain,
                )
            )
            status = response.status_code
            text = response.body
            signal = response.anti_crawl_signal.value if response.anti_crawl_signal.value != "none" else ""
        except Exception as exc:  # noqa: BLE001
            self._stats["errors"] += 1
            logger.error("upstream fetch failed %s: %r", url, exc)
            status, text, signal = 502, "upstream fetch failed", ""

        extra_headers = {"X-Anti-Crawl-Signal": signal} if signal else {}
        await self._write_response(writer, status, text.encode("utf-8", errors="replace"), extra_headers)
        await writer.drain()

    async def _write_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """回写一个 HTTP/1.1 响应。"""
        reason = _REASON_PHRASES.get(status, "OK")
        lines = [
            f"HTTP/1.1 {status} {reason}",
            f"Content-Length: {len(body)}",
            "Connection: keep-alive",
            "Content-Type: text/html; charset=utf-8",
        ]
        if extra_headers:
            lines.extend(f"{key}: {value}" for key, value in extra_headers.items())
        writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)

    async def _read_line(self, reader: asyncio.StreamReader) -> bytes:
        """读取一行（去除 CRLF）。"""
        line = await reader.readline()
        return line.rstrip(b"\r\n")
