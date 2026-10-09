"""TLS Client Hello Desynchronization (RFC-Compliant Multi-Record Split).
Membypass blokir SNI / DPI ISP di Indonesia tanpa memerlukan VPN / WireGuard,
sehingga 100% aman dari deteksi Sangfor Firewall dan tidak memicu blokir MAC address.
"""

import socket
import ssl
import time
import urllib.parse
from config import HI_UA

# Cache DNS hasil resolve DoH / direct
_DNS_CACHE = {}


def _resolve_host(host: str) -> str:
    """Resolve domain ke IPv4 dengan proteksi anti DNS-poisoning ISP.
    Urutan: Cache -> System DNS -> DoH (Cloudflare 1.1.1.1 / Google 8.8.8.8) -> Hardcoded Fallback."""
    if not host:
        return host
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    
    # Cek apakah host sudah merupakan IP numerik
    if all(part.isdigit() for part in host.split(".") if part):
        _DNS_CACHE[host] = host
        return host

    # 1. Coba resolve DNS sistem lokal
    try:
        ip = socket.gethostbyname(host)
        # Abaikan bila di-poison ke IP localhost atau private range
        if ip and not ip.startswith("10.") and not ip.startswith("127.") and not ip.startswith("192.168."):
            _DNS_CACHE[host] = ip
            return ip
    except Exception:
        pass

    # 2. Bypass DNS Blokir ISP via DoH (DNS-over-HTTPS)
    for doh_url in ("https://1.1.1.1/dns-query", "https://dns.google/resolve"):
        try:
            import urllib.request
            import json
            req = urllib.request.Request(
                f"{doh_url}?name={host}&type=A",
                headers={"Accept": "application/dns-json", "User-Agent": HI_UA}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    answers = data.get("Answer", [])
                    for ans in answers:
                        if ans.get("type") == 1 and ans.get("data"):
                            ip = ans["data"]
                            _DNS_CACHE[host] = ip
                            return ip
        except Exception:
            pass

    # 3. Fallback IP CDN yang diketahui
    known = {
        "hls.dramahot.top": "93.123.109.210",
        "dramahot.top": "93.123.109.210",
    }
    if host in known:
        _DNS_CACHE[host] = known[host]
        return known[host]

    return host


def tls_desync_connect(host: str, port: int = 443, timeout: float = 8.0):
    """Membuka socket TLS dengan Client Hello dipecah menjadi 2 TLS Record.
    Record 1: 1 byte data Client Hello.
    Record 2: Sisa data Client Hello.
    Menghilangkan signature SNI utuh dari pemindaian DPI ISP."""
    ip = _resolve_host(host)
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.settimeout(timeout)
    raw_sock.connect((ip, port))
    raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    in_bio, out_bio = ssl.MemoryBIO(), ssl.MemoryBIO()
    sslobj = ctx.wrap_bio(in_bio, out_bio, server_hostname=host)

    try:
        sslobj.do_handshake()
    except ssl.SSLWantReadError:
        pass

    b = out_bio.read()
    if len(b) > 10:
        # Pecah Client Hello menjadi 2 valid TLS records
        rec1 = b[:3] + b"\x00\x01" + b[5:6]
        rec2_data = b[6:]
        rec2 = b[:3] + len(rec2_data).to_bytes(2, "big") + rec2_data

        raw_sock.sendall(rec1)
        time.sleep(0.04)  # Jeda mikro agar terkirim terpisah di TCP layer
        raw_sock.sendall(rec2)
    else:
        raw_sock.sendall(b)

    # Selesaikan TLS Handshake
    start_t = time.time()
    while time.time() - start_t < timeout:
        d = raw_sock.recv(8192)
        if not d:
            break
        in_bio.write(d)
        try:
            sslobj.do_handshake()
            if out_bio.pending:
                raw_sock.sendall(out_bio.read())
            break
        except ssl.SSLWantWriteError:
            raw_sock.sendall(out_bio.read())
        except ssl.SSLWantReadError:
            if out_bio.pending:
                raw_sock.sendall(out_bio.read())

    return raw_sock, sslobj, in_bio, out_bio


def tls_desync_request(url: str, headers: dict = None, timeout: float = 10.0) -> bytes:
    """Kirim HTTP GET request via desync TLS socket dan kembalikan response body bytes."""
    p = urllib.parse.urlsplit(url)
    host = p.netloc.split(":")[0]
    port = p.port or 443
    path = p.path or "/"
    if p.query:
        path += "?" + p.query

    raw_sock, sslobj, in_bio, out_bio = tls_desync_connect(host, port, timeout=timeout)
    
    h_lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}",
        f"User-Agent: {HI_UA}",
        "Accept: */*",
        "Connection: close",
    ]
    if headers:
        for k, v in headers.items():
            if k.lower() not in ("host", "connection"):
                h_lines.append(f"{k}: {v}")
    
    req_data = "\r\n".join(h_lines) + "\r\n\r\n"
    sslobj.write(req_data.encode("utf-8"))
    raw_sock.sendall(out_bio.read())

    # Baca seluruh HTTP response
    resp_raw = b""
    raw_sock.settimeout(timeout)
    while True:
        try:
            d = raw_sock.recv(16384)
            if not d:
                break
            in_bio.write(d)
            while True:
                try:
                    chunk = sslobj.read(16384)
                    if not chunk:
                        break
                    resp_raw += chunk
                except (ssl.SSLWantReadError, ssl.SSLZeroReturnError):
                    break
        except socket.timeout:
            break
        except Exception:
            break

    try:
        raw_sock.close()
    except Exception:
        pass

    # Pisahkan header dan body HTTP
    idx = resp_raw.find(b"\r\n\r\n")
    if idx >= 0:
        return resp_raw[idx + 4:]
    return resp_raw


async def tls_desync_stream(url: str, headers: dict = None, chunk_size: int = 65536):
    """Async generator untuk streaming segmen video via desync TLS."""
    import asyncio
    p = urllib.parse.urlsplit(url)
    host = p.netloc.split(":")[0]
    port = p.port or 443
    path = p.path or "/"
    if p.query:
        path += "?" + p.query

    loop = asyncio.get_running_loop()
    raw_sock, sslobj, in_bio, out_bio = await loop.run_in_executor(
        None, lambda: tls_desync_connect(host, port, timeout=10.0)
    )

    h_lines = [
        f"GET {path} HTTP/1.1",
        f"Host: {host}",
        f"User-Agent: {HI_UA}",
        "Accept: */*",
        "Connection: close",
    ]
    if headers:
        for k, v in headers.items():
            if k.lower() not in ("host", "connection"):
                h_lines.append(f"{k}: {v}")

    req_data = "\r\n".join(h_lines) + "\r\n\r\n"
    sslobj.write(req_data.encode("utf-8"))
    raw_sock.sendall(out_bio.read())

    # Stream chunks
    header_parsed = False
    buf = b""
    raw_sock.settimeout(12.0)

    while True:
        try:
            d = await loop.run_in_executor(None, lambda: raw_sock.recv(32768))
            if not d:
                break
            in_bio.write(d)
            while True:
                try:
                    chunk = sslobj.read(32768)
                    if not chunk:
                        break
                    if not header_parsed:
                        buf += chunk
                        sep = buf.find(b"\r\n\r\n")
                        if sep >= 0:
                            header_parsed = True
                            body_part = buf[sep + 4:]
                            buf = b""
                            if body_part:
                                yield body_part
                    else:
                        yield chunk
                except (ssl.SSLWantReadError, ssl.SSLZeroReturnError):
                    break
        except Exception:
            break

    try:
        raw_sock.close()
    except Exception:
        pass
