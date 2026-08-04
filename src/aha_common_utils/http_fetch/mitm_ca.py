"""MitmCertificateAuthority — MITM 代理自签根 CA 与目标域名证书签发。

- 首次运行生成根 CA（持久化到 ``ca_dir``：ca.key / ca.crt）；
- 按目标域名签发短期证书（默认 30 天，SAN=host），内存缓存；
- 消费方（如 SearXNG）通过 ``outgoing.verify`` 信任根 CA 后即可使用本代理。
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.x509.oid import NameOID

from aha_common_utils.http_fetch.proxy_server import CertificateAuthority
from aha_common_utils.logging import get_logger

logger = get_logger(__name__)

_CA_NAME = "aha-common-utils MITM Proxy CA"
_CERT_DAYS = 30
_CA_DAYS = 3650


class MitmCertificateAuthority(CertificateAuthority):
    """自签根 CA + 按域名签发短期叶证书。"""

    def __init__(self, ca_dir: str = "tmp/mitm-ca") -> None:
        self._ca_dir = Path(ca_dir)
        self._ca_key_path = self._ca_dir / "ca.key"
        self._ca_cert_path = self._ca_dir / "ca.crt"
        self._ca_key: EllipticCurvePrivateKey | None = None
        self._ca_cert: x509.Certificate | None = None
        self._leaf_cache: dict[str, tuple[Path, Path]] = {}
        self._load_or_create()

    @property
    def ca_cert_path(self) -> Path:
        """根 CA 证书路径。"""
        return self._ca_cert_path

    def ca_cert_pem(self) -> bytes:
        """根 CA 证书 PEM 内容。"""
        return self._ca_cert_path.read_bytes()

    def get_leaf_cert(self, host: str) -> tuple[str, str]:
        """签发（或返回缓存的）目标域名证书，返回 ``(cert_path, key_path)``。"""
        if host in self._leaf_cache:
            cert_path, key_path = self._leaf_cache[host]
            return str(cert_path), str(key_path)
        cert_path = self._ca_dir / f"leaf-{host}.crt"
        key_path = self._ca_dir / f"leaf-{host}.key"
        if cert_path.exists() and key_path.exists():
            result = (str(cert_path), str(key_path))
            self._leaf_cache[host] = (cert_path, key_path)
            return result

        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(UTC)
        try:
            san: list[x509.GeneralName] = [x509.IPAddress(ipaddress.ip_address(host))]
        except ValueError:
            san = [x509.DNSName(host)]
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
            .issuer_name(self._ca_cert.subject)  # type: ignore[union-attr]  # __init__ 已创建 CA
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(hours=1))
            .not_valid_after(now + timedelta(days=_CERT_DAYS))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=False,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                    crl_sign=False,
                ),
                critical=True,
            )
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(self._ca_key, hashes.SHA256())  # type: ignore[arg-type]  # __init__ 已创建 CA
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        result = (str(cert_path), str(key_path))
        self._leaf_cache[host] = (cert_path, key_path)
        return result

    def _load_or_create(self) -> None:
        self._ca_dir.mkdir(parents=True, exist_ok=True)
        if self._ca_key_path.exists() and self._ca_cert_path.exists():
            loaded_key = serialization.load_pem_private_key(self._ca_key_path.read_bytes(), password=None)
            assert isinstance(loaded_key, EllipticCurvePrivateKey)
            self._ca_key = loaded_key
            self._ca_cert = x509.load_pem_x509_certificate(self._ca_cert_path.read_bytes())
            return
        self._create_ca()

    def _create_ca(self) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _CA_NAME)])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=_CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                    crl_sign=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256())
        )
        self._ca_key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
        )
        self._ca_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        self._ca_key = key
        self._ca_cert = cert
        logger.info("MITM CA created: %s", self._ca_cert_path)
