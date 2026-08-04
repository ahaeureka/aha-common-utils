"""Tests for HttpProxyServer and MitmCertificateAuthority.

覆盖：普通 HTTP 经 HttpFetchPort 转发、hop-by-hop 头过滤、CONNECT 透传隧道、
MITM HTTPS 拦截、代理统计与生命周期。
"""

from __future__ import annotations

import asyncio
import ssl
from pathlib import Path

from aha_common_utils.http_fetch.mitm_ca import MitmCertificateAuthority
from aha_common_utils.http_fetch.proxy_server import CertificateAuthority, HttpProxyServer
from aha_common_utils.ports.http_fetch import HttpFetchRequest
from aha_common_utils.testing.fakes.http_fetch import FakeHttpFetchProvider, make_fetch_response


async def _echo_server() -> tuple[asyncio.Server, int]:
    """启动一个回显 TCP 服务，返回 (server, port)。"""

    async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    return server, port


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ── 普通 HTTP 转发 ─────────────────────────────────────────────────


async def test_proxy_forward_plain_http_through_port() -> None:
    provider = FakeHttpFetchProvider()
    provider.set_response(
        "http://example.com/data",
        make_fetch_response(status_code=200, body="hello-proxy"),
    )
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(b"GET http://example.com/data HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        body = await reader.read(128)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.stop()

    assert b"200 OK" in head
    assert b"hello-proxy" in body
    assert len(provider.calls) == 1
    request: HttpFetchRequest = provider.calls[0]
    assert request.url == "http://example.com/data"
    assert request.method == "GET"
    assert request.domain == "example.com"


async def test_proxy_strips_hop_by_hop_headers() -> None:
    provider = FakeHttpFetchProvider()
    provider.set_response(
        "http://example.com/",
        make_fetch_response(status_code=200, body="ok"),
    )
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(
            b"GET http://example.com/ HTTP/1.1\r\n"
            b"Host: example.com\r\n"
            b"Proxy-Authorization: Basic xyz\r\n"
            b"Connection: keep-alive\r\n"
            b"X-Custom: keep-me\r\n"
            b"\r\n"
        )
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.stop()

    headers = provider.calls[0].headers
    assert "proxy-authorization" not in headers
    assert "connection" not in headers
    assert headers.get("x-custom") == "keep-me"


async def test_proxy_forward_origin_form_uses_host_header() -> None:
    provider = FakeHttpFetchProvider()
    provider.set_response(
        "http://example.com/path",
        make_fetch_response(status_code=200, body="ok"),
    )
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(b"GET /path HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.stop()

    assert provider.calls[0].url == "http://example.com/path"


async def test_proxy_upstream_error_returns_502() -> None:
    provider = FakeHttpFetchProvider()

    async def _boom(request: HttpFetchRequest) -> object:
        raise ConnectionError("upstream down")

    provider.fetch = _boom  # type: ignore[method-assign]
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.stop()

    assert b"502 Bad Gateway" in head


# ── CONNECT 透传隧道 ───────────────────────────────────────────────


async def test_proxy_connect_tunnel_passes_bytes_through() -> None:
    echo_server, echo_port = await _echo_server()
    provider = FakeHttpFetchProvider()
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)
    await proxy.start()
    try:
        target = f"127.0.0.1:{echo_port}"
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        assert b"200 Connection established" in head

        writer.write(b"ping-over-tunnel")
        await writer.drain()
        echoed = await reader.read(128)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.stop()
        echo_server.close()
        await echo_server.wait_closed()

    assert echoed == b"ping-over-tunnel"
    assert proxy.stats()["tunnels"] == 1
    assert provider.calls == []


# ── MITM HTTPS 拦截 ────────────────────────────────────────────────


async def _tls_client_write(proxy_port: int, ca_cert_path: Path, host: str, payload: bytes) -> bytes:
    """经代理 CONNECT + start_tls 发送一个内层 HTTPS 请求，返回响应字节。"""
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy_port)
    writer.write(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    assert b"200 Connection established" in head

    client_ctx = ssl.create_default_context(cafile=str(ca_cert_path))
    loop = asyncio.get_event_loop()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport = await loop.start_tls(
        writer.transport,
        protocol,
        sslcontext=client_ctx,
        server_hostname=host,
        server_side=False,
    )
    setattr(reader, "_transport", transport)  # noqa: B010
    tls_writer = asyncio.StreamWriter(transport, protocol, reader, loop)  # type: ignore[arg-type]

    tls_writer.write(payload)
    await tls_writer.drain()
    data = await reader.read(4096)
    tls_writer.close()
    await tls_writer.wait_closed()
    return data


async def test_proxy_mitm_intercepts_https_and_dispatches_through_port(tmp_path: Path) -> None:
    ca = MitmCertificateAuthority(ca_dir=str(tmp_path / "ca"))
    provider = FakeHttpFetchProvider()
    provider.set_response(
        "https://example.com:443/secure",
        make_fetch_response(status_code=200, body="mitm-ok"),
    )
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0, ca=ca)
    await proxy.start()
    try:
        response = await _tls_client_write(
            proxy.bound_port,
            ca.ca_cert_path,
            "example.com",
            b"GET /secure HTTP/1.1\r\nHost: example.com\r\n\r\n",
        )
    finally:
        await proxy.stop()

    assert b"200 OK" in response
    assert b"mitm-ok" in response
    assert len(provider.calls) == 1
    assert provider.calls[0].url == "https://example.com:443/secure"
    assert proxy.stats()["mitm_intercepts"] == 1


async def test_proxy_mitm_requires_trusted_ca(tmp_path: Path) -> None:
    """不信任代理 CA 的客户端 TLS 握手应失败，且不产生上游请求。"""
    ca = MitmCertificateAuthority(ca_dir=str(tmp_path / "ca"))
    provider = FakeHttpFetchProvider()
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0, ca=ca)
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        head = await reader.readuntil(b"\r\n\r\n")
        assert b"200 Connection established" in head

        untrusted = ssl.create_default_context()  # 不信任代理 CA
        loop = asyncio.get_event_loop()
        protocol = asyncio.StreamReaderProtocol(reader)
        try:
            await asyncio.wait_for(
                loop.start_tls(
                    writer.transport,
                    protocol,
                    sslcontext=untrusted,
                    server_hostname="example.com",
                    server_side=False,
                ),
                timeout=5,
            )
            await writer.close()
        except (ssl.SSLError, TimeoutError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
            await asyncio.sleep(0)
    finally:
        await proxy.stop()

    assert provider.calls == []


# ── 生命周期与统计 ─────────────────────────────────────────────────


async def test_proxy_lifecycle_and_stats() -> None:
    provider = FakeHttpFetchProvider()
    proxy = HttpProxyServer(http_fetch=provider, host="127.0.0.1", port=0)

    async with proxy:
        assert proxy.bound_port != 0
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.bound_port)
        writer.write(b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n\r\n")
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        writer.close()
        await writer.wait_closed()

    assert proxy.stats()["requests"] == 1
    assert proxy._server is None


def test_proxy_default_fetch_is_anti_detection_manager() -> None:
    from aha_common_utils.http_fetch.anti_detection import AntiDetectionManager

    proxy = HttpProxyServer()
    assert isinstance(proxy._http_fetch, AntiDetectionManager)


# ── MitmCertificateAuthority ───────────────────────────────────────


def test_ca_creates_root_and_signs_leaf(tmp_path: Path) -> None:
    ca = MitmCertificateAuthority(ca_dir=str(tmp_path / "ca"))
    cert_path, key_path = ca.get_leaf_cert("example.com")
    assert Path(cert_path).exists()
    assert Path(key_path).exists()
    assert ca.ca_cert_path.exists()

    cached_cert_path, cached_key_path = ca.get_leaf_cert("example.com")
    assert cached_cert_path == cert_path


def test_ca_certificate_authority_abstraction_is_importable() -> None:
    assert CertificateAuthority.__module__ == "aha_common_utils.http_fetch.proxy_server"
