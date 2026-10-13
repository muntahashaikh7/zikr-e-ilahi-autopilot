#!/usr/bin/env python3
"""Manual Microsoft Edge TTS client.

Route: raw TCP -> HTTP CONNECT (egress proxy) -> TLS -> WebSocket handshake
-> Edge speech protocol. The sandbox proxy MITMs TLS and strips the
`Connection: upgrade` header from the 101 response, which breaks strict WS
clients (aiohttp). This client accepts 101 without that header and proceeds.
Reuses edge_tts package helpers for DRM/SSML/message parsing.
"""
import base64
import os
import secrets
import socket
import ssl
import struct
import sys
import uuid

from edge_tts.communicate import (
    date_to_string,
    get_headers_and_data,
    mkssml,
    ssml_headers_plus_data,
)
from edge_tts.constants import SEC_MS_GEC_VERSION, WSS_HEADERS, WSS_URL
from edge_tts.data_classes import TTSConfig
from edge_tts.drm import DRM


def proxy_parts():
    p = os.environ.get("https_proxy")  # http://user:pass@host:port
    if not p:
        raise RuntimeError("proxy tunnel requested but https_proxy is not set")
    creds, hostport = p.split("://", 1)[1].split("@", 1)
    host, port = hostport.split(":")
    return creds, host, int(port)


def connect_tls_tunnel(target_host, timeout=30):
    creds, phost, pport = proxy_parts()
    s = socket.create_connection((phost, pport), timeout=timeout)
    auth = base64.b64encode(creds.encode()).decode()
    s.sendall(
        f"CONNECT {target_host}:443 HTTP/1.1\r\n"
        f"Host: {target_host}:443\r\n"
        f"Proxy-Authorization: Basic {auth}\r\n\r\n".encode()
    )
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = s.recv(4096)
        if not chunk:
            raise RuntimeError("proxy closed connection during CONNECT")
        resp += chunk
    if b" 200" not in resp.split(b"\r\n")[0]:
        raise RuntimeError(f"CONNECT failed: {resp.split(bchr(13))[0]}")
    ctx = ssl.create_default_context()
    ts = ctx.wrap_socket(s, server_hostname=target_host)
    ts.settimeout(timeout)
    return ts


def ws_handshake(ts, path_query, extra_headers):
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    headers = {
        "Host": "speech.platform.bing.com",
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Key": key,
        "Sec-WebSocket-Version": "13",
    }
    headers.update(extra_headers)
    req = f"GET {path_query} HTTP/1.1\r\n"
    for k, v in headers.items():
        req += f"{k}: {v}\r\n"
    req += "\r\n"
    ts.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = ts.recv(4096)
        if not chunk:
            raise RuntimeError("connection closed during WS handshake")
        resp += chunk
    status_line = resp.split(b"\r\n")[0].decode(errors="replace")
    # LENIENT: accept 101 even if proxy stripped the Connection header
    if " 101 " not in status_line:
        raise RuntimeError(f"WS handshake failed: {status_line[:200]}")
    return resp


def ws_send_text(ts, text):
    data = text.encode("utf-8")
    mask = secrets.token_bytes(4)
    n = len(data)
    if n < 126:
        hdr = struct.pack("!BB", 0x81, 0x80 | n)
    elif n < 65536:
        hdr = struct.pack("!BBH", 0x81, 0x80 | 126, n)
    else:
        hdr = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    ts.sendall(hdr + mask + masked)


class WSReader:
    def __init__(self, ts):
        self.ts = ts
        self.buf = b""

    def _fill(self, n):
        while len(self.buf) < n:
            chunk = self.ts.recv(65536)
            if not chunk:
                raise RuntimeError("connection closed mid-frame")
            self.buf += chunk

    def read_frame(self):
        self._fill(2)
        b1, b2 = self.buf[0], self.buf[1]
        fin = b1 & 0x80
        opcode = b1 & 0x0F
        length = b2 & 0x7F
        idx = 2
        if length == 126:
            self._fill(4)
            length = struct.unpack("!H", self.buf[2:4])[0]
            idx = 4
        elif length == 127:
            self._fill(10)
            length = struct.unpack("!Q", self.buf[2:10])[0]
            idx = 10
        self._fill(idx + length)
        payload = self.buf[idx : idx + length]
        self.buf = self.buf[idx + length :]
        if opcode == 0x8:  # close
            raise RuntimeError("server closed WS connection")
        if opcode == 0x9:  # ping -> pong
            self._send_frame(0xA, payload)
            return self.read_frame()
        return opcode, payload

    def _send_frame(self, opcode, payload):
        n = len(payload)
        mask = secrets.token_bytes(4)
        hdr = struct.pack("!BB", 0x80 | opcode, 0x80 | min(n, 125))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.ts.sendall(hdr + mask + masked)


def synthesize_direct(text, voice, out_path, timeout=60, rate="+0%", pitch="+0Hz", volume="+0%"):
    """Direct Edge TTS via the standard edge_tts library (normal internet:
    GitHub Actions, local machines). Same signature as synthesize()."""
    import asyncio

    async def _run():
        from edge_tts import Communicate
        comm = Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
        await comm.save(out_path)

    asyncio.run(_run())
    # edge_tts saves mp3; build script converts to wav itself
    return out_path


def synthesize_gtts(text, out_path, lang="ar"):
    """Last-resort TTS via Google Translate TTS. Works from datacenter IPs
    where Edge TTS 403s. Voice is simpler than Edge neural voices, but it
    keeps the pipeline alive. Returns out_path (mp3)."""
    from gtts import gTTS
    gTTS(text=text, lang=lang).save(out_path)
    return out_path


def synthesize(text, voice, out_path, timeout=60, _ssml=None, rate="+0%", pitch="+0Hz", volume="+0%"):
    # Auto-route with graceful fallbacks:
    #   1. direct edge_tts when NOT behind the sandbox proxy,
    #   2. proxy-tunnel when https_proxy is set (this VM),
    #   3. gTTS last resort (Edge 403s datacenter IPs like GitHub runners).
    # Never raises a bare KeyError; the final error lists every route tried.
    import os
    errors = []
    use_proxy = "https_proxy" in os.environ
    if not use_proxy and _ssml is None:
        try:
            return synthesize_direct(text, voice, out_path, timeout,
                                     rate=rate, pitch=pitch, volume=volume)
        except Exception as e:
            errors.append(f"direct edge-tts failed: {e}")
    if use_proxy:
        try:
            return synthesize_via_proxy(text, voice, out_path, timeout, _ssml,
                                        rate, pitch, volume)
        except Exception as e:
            errors.append(f"proxy-tunnel edge-tts failed: {e}")
    try:
        return synthesize_gtts(text, out_path)
    except Exception as e:
        errors.append(f"gtts fallback failed: {e}")
    raise RuntimeError("all TTS routes failed: " + " | ".join(errors))


def synthesize_via_proxy(text, voice, out_path, timeout=60, _ssml=None, rate="+0%", pitch="+0Hz", volume="+0%"):
    # Build URL + headers exactly like edge_tts does
    url = (
        f"{WSS_URL}&ConnectionId={uuid.uuid4().hex}"
        f"&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}"
    )
    # WSS_URL is wss://host/path?query -> split path+query
    path_query = url.split("wss://speech.platform.bing.com", 1)[1]
    extra = DRM.headers_with_muid(WSS_HEADERS)

    ts = connect_tls_tunnel("speech.platform.bing.com", timeout=timeout)
    try:
        ws_handshake(ts, path_query, extra)
        reader = WSReader(ts)

        tc = TTSConfig(voice=voice, rate=rate, volume=volume, pitch=pitch, boundary="SentenceBoundary")
        ws_send_text(
            ts,
            f"X-Timestamp:{date_to_string()}\r\n"
            "Content-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{'
            '"sentenceBoundaryEnabled":"true","wordBoundaryEnabled":"false"'
            '},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n',
        )
        ssml_text = _ssml if _ssml is not None else mkssml(tc, text)
        ws_send_text(
            ts,
            ssml_headers_plus_data(uuid.uuid4().hex, date_to_string(), ssml_text),
        )

        audio = b""
        got_audio = False
        while True:
            opcode, payload = reader.read_frame()
            if opcode == 0x1:  # text
                txt = payload.decode("utf-8", errors="replace")
                if "Path:turn.end" in txt:
                    break
            elif opcode == 0x2:  # binary
                hlen = struct.unpack("!H", payload[:2])[0]
                # Parse headers leniently: block ends with trailing \r\n
                # which yields an empty final element; skip empties.
                headers = {}
                for line in payload[2 : 2 + hlen].split(b"\r\n"):
                    if not line or b":" not in line:
                        continue
                    k, v = line.split(b":", 1)
                    headers[k] = v
                data = payload[2 + hlen :]
                if headers.get(b"Path") == b"audio":
                    audio += data
                    got_audio = True
        if not got_audio:
            raise RuntimeError("no audio received from service")
        with open(out_path, "wb") as f:
            f.write(audio)
        return len(audio)
    finally:
        try:
            ts.close()
        except Exception:
            pass


def build_custom_ssml(voice, inner_xml, rate="+0%", pitch="+0Hz", volume="+0%"):
    """Build SSML whose inner XML is caller-supplied (may contain <phoneme> tags)."""
    return (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
        f"<voice name='{voice}'>"
        f"<prosody pitch='{pitch}' rate='{rate}' volume='{volume}'>"
        f"{inner_xml}"
        "</prosody>"
        "</voice>"
        "</speak>"
    )


def synthesize_ssml(inner_xml, voice, out_path, timeout=60, rate="+0%", pitch="+0Hz", volume="+0%"):
    """Synthesize with raw SSML inner XML (e.g. containing <phoneme alphabet="ipa"> tags)."""
    ssml = build_custom_ssml(voice, inner_xml, rate, pitch, volume)
    return synthesize("", voice, out_path, timeout, _ssml=ssml)


if __name__ == "__main__":
    voice = sys.argv[1]
    out = sys.argv[2]
    text = open(sys.argv[3], encoding="utf-8").read().strip()
    n = synthesize(text, voice, out)
    print(f"OK: wrote {n} audio bytes to {out}")
