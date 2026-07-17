"""GDA -sv (CLI Server) client and process manager.

Protocol (official client_gda.py):
  send:  "<cmd>\\n"
  recv:  4-byte big-endian length + payload
"""

from __future__ import annotations

import locale
import logging
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("gda-mcp-server.sv")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

DEFAULT_GDA_EXE = os.environ.get("GDA_EXE", r"D:\mytools\GDA4.12\GDA.exe")
# Avoid 8888 — often taken by proxies (e.g. Reqable)
DEFAULT_PORT = int(os.environ.get("GDA_PORT", "18888"))
DEFAULT_HOST = os.environ.get("GDA_HOST", "127.0.0.1")
# Client-side line pagination for large GDA replies
DEFAULT_PAGE_SIZE = int(os.environ.get("GDA_PAGE_SIZE", "200"))
MAX_PAGE_SIZE = int(os.environ.get("GDA_MAX_PAGE_SIZE", "2000"))


def paginate_text(
    text: str,
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    """Slice GDA output by lines. count<=0 falls back to DEFAULT_PAGE_SIZE."""
    lines = text.splitlines(keepends=True)
    total = len(lines)
    off = max(0, int(offset))
    if count is None or int(count) <= 0:
        lim = DEFAULT_PAGE_SIZE
    else:
        lim = min(int(count), MAX_PAGE_SIZE)
    chunk = lines[off : off + lim]
    returned = len(chunk)
    next_off = off + returned
    truncated = next_off < total
    return {
        "total_lines": total,
        "offset": off,
        "count": returned,
        "page_size": lim,
        "truncated": truncated,
        "next_offset": next_off if truncated else None,
        "text": "".join(chunk),
    }


class GDAServerManager:
    def __init__(self, gda_exe_path: str = DEFAULT_GDA_EXE):
        self.gda_exe = gda_exe_path
        self.process: Optional[subprocess.Popen] = None
        self.apk_path: Optional[str] = None
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.lock = threading.Lock()
        self._external = False  # connected to already-running server

    def start_server(self, apk_path: str, port: int = DEFAULT_PORT, timeout: float = 180) -> bool:
        with self.lock:
            apk_path = os.path.abspath(apk_path)
            if self.is_running() and self.apk_path == apk_path and self.port == port:
                return True
            if self.is_running():
                self._stop_unlocked()

            if not os.path.isfile(self.gda_exe):
                raise FileNotFoundError(f"GDA.exe not found: {self.gda_exe}")
            if not os.path.isfile(apk_path):
                raise FileNotFoundError(f"APK not found: {apk_path}")

            self.apk_path = apk_path
            self.port = port
            self._external = False

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

            logger.info("Starting: %s -sv %s %s", self.gda_exe, apk_path, port)
            self.process = subprocess.Popen(
                [self.gda_exe, "-sv", apk_path, str(port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags,
            )
            ok = self._wait_for_server(port, timeout=timeout)
            if not ok and self.process.poll() is not None:
                err = ""
                try:
                    err = (self.process.stderr.read() or "")[:2000]
                except Exception:
                    pass
                raise RuntimeError(f"GDA exited early. stderr={err!r}")
            return ok

    def attach(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, apk_path: str = "") -> bool:
        """Use an already-running gda.exe -sv without spawning."""
        with self.lock:
            if not self._port_open(host, port):
                return False
            self.host = host
            self.port = port
            self.apk_path = apk_path or self.apk_path
            self._external = True
            self.process = None
            return True

    def _port_open(self, host: str, port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def _wait_for_server(self, port: int, timeout: float = 180) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.process is not None and self.process.poll() is not None:
                return False
            if self._port_open(self.host, port):
                return True
            time.sleep(0.4)
        return False

    def is_running(self) -> bool:
        if self._external:
            return self._port_open(self.host, self.port)
        if self.process is None:
            return False
        return self.process.poll() is None

    def _stop_unlocked(self) -> None:
        if self._external:
            self._external = False
            self.process = None
            self.apk_path = None
            return
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.apk_path = None

    def stop_server(self) -> None:
        with self.lock:
            self._stop_unlocked()

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running(),
            "external": self._external,
            "host": self.host,
            "port": self.port,
            "apk_path": self.apk_path,
            "gda_exe": self.gda_exe,
            "pid": None if self.process is None else self.process.pid,
        }


class GDAClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._lock = threading.Lock()

    def execute(self, cmd: str, recv_timeout: float = 120.0) -> str:
        with self._lock:
            try:
                with socket.create_connection((self.host, self.port), timeout=10) as sock:
                    sock.settimeout(recv_timeout)
                    sock.sendall((cmd + "\n").encode("utf-8", errors="replace"))
                    return self._recv_response(sock)
            except Exception as e:
                return f"Error: {e}"

    def _recv_response(self, sock: socket.socket) -> str:
        # Prefer length-prefixed framing (official client_gda.py)
        try:
            sock.settimeout(2.0)
            len_data = self._recv_exact(sock, 4)
            if len_data and len(len_data) == 4:
                resp_len = struct.unpack("!I", len_data)[0]
                # Guard absurd sizes
                if 0 < resp_len < 64 * 1024 * 1024:
                    sock.settimeout(120.0)
                    payload = self._recv_exact(sock, resp_len)
                    return self._decode(payload)
                # Not a length prefix — fall through with buffered bytes
                rest = self._recv_until_close(sock, initial=len_data)
                return self._decode(rest)
        except socket.timeout:
            pass
        except Exception:
            pass

        # Fallback: read until peer closes
        sock.settimeout(120.0)
        return self._decode(self._recv_until_close(sock))

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return buf

    @staticmethod
    def _recv_until_close(sock: socket.socket, initial: bytes = b"") -> bytes:
        buf = bytearray(initial)
        while True:
            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                break
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    @staticmethod
    def _decode(data: bytes) -> str:
        if not data:
            return ""
        enc = locale.getpreferredencoding(False) or "utf-8"
        try:
            return data.decode(enc)
        except Exception:
            return data.decode("utf-8", errors="replace")


FIND_OPT = {
    "class": "-c",
    "class_with_package": "-C",
    "method": "-m",
    "method_with_package": "-M",
    "field": "-d",
    "api_method": "-i",
    "string": "-s",
    "all": "-a",
}

XREF_OPT = {
    "class": "-c",
    "method": "-m",
    "field": "-f",
    "string": "-s",
    "resource": "-r",
    "all": "-a",
}


def build_command(skill: str, arguments: Dict[str, Any]) -> str:
    """Map skill name → GDA shell subcommand."""
    simple = {
        "help": "help",
        "exit": "exit",
        "axml": "axml",
        "binfo": "binfo",
        "pname": "pname",
        "permission": "permission",
        "attsf": "attsf",
        "packer": "packer",
        "cert": "cert",
        "appstr": "appstr",
        "malscan": "malscan",
        "sensinf": "sensinf",
        "interface": "interface",
        "uri": "uri",
        "native": "native",
        "api": "api",
    }
    if skill in simple:
        return simple[skill]

    if skill == "set_output":
        return f"set -o {arguments['file']}"
    if skill == "header":
        return f"header {arguments['n']}"
    if skill == "listm":
        return f"listm {arguments['cname']}"
    if skill == "sclass":
        return f"sclass {arguments['cidx']}"
    if skill == "pclass":
        return f"pclass {arguments['cidx']}"
    if skill == "dasm":
        return f"dasm {arguments['method_ref']}"
    if skill == "dec":
        return f"dec {arguments['target']}"
    if skill == "find":
        stype = arguments.get("search_type")
        name = arguments.get("name")
        if stype not in FIND_OPT or not name:
            raise ValueError("find requires search_type and name")
        return f"find {FIND_OPT[stype]} {name}"
    if skill == "xref":
        xtype = arguments.get("xref_type")
        name = arguments.get("name")
        if xtype not in XREF_OPT or not name:
            raise ValueError("xref requires xref_type and name")
        return f"xref {XREF_OPT[xtype]} {name}"
    if skill == "raw":
        cmd = arguments.get("cmd", "").strip()
        if not cmd:
            raise ValueError("raw requires cmd")
        return cmd
    raise ValueError(f"Unknown skill: {skill}")


class GDAExecutor:
    """Singleton-ish executor used by MCP tools."""

    def __init__(self, gda_exe: str = DEFAULT_GDA_EXE):
        self.manager = GDAServerManager(gda_exe)
        self.client: Optional[GDAClient] = None
        self._cache_cmd: Optional[str] = None
        self._cache_text: Optional[str] = None

    def set_gda_exe(self, path: str) -> None:
        self.manager.gda_exe = path

    def _clear_cache(self) -> None:
        self._cache_cmd = None
        self._cache_text = None

    def start(self, apk_file: str, port: int = DEFAULT_PORT) -> Dict[str, Any]:
        self._clear_cache()
        ok = self.manager.start_server(apk_file, port=port)
        if not ok:
            return {"ok": False, "error": "GDA -sv start timeout", "status": self.manager.status()}
        self.client = GDAClient(self.manager.host, self.manager.port)
        return {"ok": True, "message": f"GDA -sv ready on {self.manager.host}:{self.manager.port}", "status": self.manager.status()}

    def attach(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Dict[str, Any]:
        self._clear_cache()
        ok = self.manager.attach(host, port)
        if not ok:
            return {"ok": False, "error": f"Nothing listening on {host}:{port}"}
        self.client = GDAClient(host, port)
        return {"ok": True, "message": f"Attached to {host}:{port}", "status": self.manager.status()}

    def stop(self) -> Dict[str, Any]:
        self._clear_cache()
        self.manager.stop_server()
        self.client = None
        return {"ok": True, "message": "GDA server stopped"}

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "status": self.manager.status()}

    def run(
        self,
        skill: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        offset: int = 0,
        count: int = DEFAULT_PAGE_SIZE,
        paginate: bool = False,
    ) -> Dict[str, Any]:
        arguments = arguments or {}
        if not self.manager.is_running():
            return {
                "ok": False,
                "error": "GDA -sv is not running. Call gda_start_server(apk_file) or gda_attach first.",
            }
        if self.client is None:
            self.client = GDAClient(self.manager.host, self.manager.port)
        try:
            cmd = build_command(skill, arguments)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        # Reuse last full reply when paging the same command
        if paginate and self._cache_cmd == cmd and self._cache_text is not None:
            text = self._cache_text
            logger.info("[CMD cached] %s", cmd)
        else:
            logger.info("[CMD] %s", cmd)
            text = self.client.execute(cmd)
            if text.startswith("Error:"):
                return {"ok": False, "error": text, "cmd": cmd}
            if paginate:
                self._cache_cmd = cmd
                self._cache_text = text

        if not paginate:
            return {"ok": True, "cmd": cmd, "text": text}

        page = paginate_text(text, offset=offset, count=count)
        return {"ok": True, "cmd": cmd, **page}


# Module-level executor shared by tools
executor = GDAExecutor()
