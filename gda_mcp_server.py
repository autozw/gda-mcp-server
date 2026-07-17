#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [ "fastmcp>=3.0.2" ]
# ///
"""
GDA-MCP-SERVER — CLI Server mode (gda.exe -sv)

No GUI / no 32-bit Python bridge.

  Cursor --stdio--> FastMCP --TCP--> gda.exe -sv <apk> <port>

Default port: 18888 (avoids Reqable/common 8888).
Default GDA:  D:\\mytools\\GDA4.12\\GDA.exe  (override with env GDA_EXE)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from fastmcp import FastMCP

from src.gda_sv import DEFAULT_GDA_EXE, DEFAULT_HOST, DEFAULT_PAGE_SIZE, DEFAULT_PORT, executor

mcp = FastMCP("GDA-MCP-Server (-sv)")

logger = logging.getLogger("gda-mcp-server.bootstrap")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


# ---- lifecycle ------------------------------------------------------------

@mcp.tool()
async def gda_start_server(apk_file: str, port: int = DEFAULT_PORT) -> dict:
    """Start gda.exe -sv with the given APK. Must be called before analysis tools."""
    return executor.start(apk_file, port=port)


@mcp.tool()
async def gda_attach(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict:
    """Attach to an already-running gda.exe -sv (does not spawn a new process)."""
    return executor.attach(host, port)


@mcp.tool()
async def gda_stop_server() -> dict:
    """Stop the GDA -sv process started by this MCP (no-op for attach-only)."""
    return executor.stop()


@mcp.tool()
async def gda_status() -> dict:
    """Show whether GDA -sv is running and which APK/port."""
    return executor.status()


# ---- recon ----------------------------------------------------------------

@mcp.tool()
async def gda_help() -> dict:
    """GDA shell help."""
    return executor.run("help")


@mcp.tool()
async def gda_binfo() -> dict:
    """APK base info: hashes, size, package, DEX stats."""
    return executor.run("binfo")


@mcp.tool()
async def gda_pname() -> dict:
    """Package name."""
    return executor.run("pname")


@mcp.tool()
async def gda_permission() -> dict:
    """Permission list."""
    return executor.run("permission")


@mcp.tool()
async def gda_axml() -> dict:
    """AndroidManifest.xml content."""
    return executor.run("axml")


@mcp.tool()
async def gda_cert() -> dict:
    """Signing certificate."""
    return executor.run("cert")


@mcp.tool()
async def gda_packer() -> dict:
    """Packer / protector detection."""
    return executor.run("packer")


@mcp.tool()
async def gda_header(n: int = 0) -> dict:
    """DEX header for the n-th DEX (0-based)."""
    return executor.run("header", {"n": n})


@mcp.tool()
async def gda_appstr(offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """Strings referenced by methods. Paginated by lines (default 200). Use next_offset to continue."""
    return executor.run("appstr", paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_interface() -> dict:
    """List interface classes."""
    return executor.run("interface")


# ---- malware / surface ----------------------------------------------------

@mcp.tool()
async def gda_attsf() -> dict:
    """Attack surface / exported components."""
    return executor.run("attsf")


@mcp.tool()
async def gda_malscan(offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """Malicious behavior scan. Paginated by lines (default 200). Use next_offset to continue."""
    return executor.run("malscan", paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_sensinf(offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """Sensitive information (keys, tokens, etc.). Paginated by lines (default 200)."""
    return executor.run("sensinf", paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_uri(offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """URLs / paths / content URIs. Paginated by lines (default 200)."""
    return executor.run("uri", paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_native() -> dict:
    """List native methods."""
    return executor.run("native")


@mcp.tool()
async def gda_api(offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """List sensitive API methods. Paginated by lines (default 200). Use next_offset to continue."""
    return executor.run("api", paginate=True, offset=offset, count=count)


# ---- code -----------------------------------------------------------------

@mcp.tool()
async def gda_listm(cname: str, offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """List methods of a class. Paginated by lines (default 200). cname like com.example.MainActivity"""
    return executor.run("listm", {"cname": cname}, paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_sclass(cidx: str) -> dict:
    """List subclasses by class index (hex), e.g. 0002d3"""
    return executor.run("sclass", {"cidx": cidx})


@mcp.tool()
async def gda_pclass(cidx: str) -> dict:
    """List parent class by class index (hex)."""
    return executor.run("pclass", {"cidx": cidx})


@mcp.tool()
async def gda_dasm(method_ref: str) -> dict:
    """Disassemble a method. e.g. method@0045F0 or -n signature"""
    return executor.run("dasm", {"method_ref": method_ref})


@mcp.tool()
async def gda_dec(target: str, offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """Decompile class/method. Paginated by lines (default 200). e.g. class@02001e"""
    return executor.run("dec", {"target": target}, paginate=True, offset=offset, count=count)


# ---- search / xref --------------------------------------------------------

@mcp.tool()
async def gda_find(
    search_type: str,
    name: str,
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """Search. search_type: class|class_with_package|method|method_with_package|field|api_method|string|all.
    Paginated by lines (default 200). Use next_offset to continue."""
    return executor.run(
        "find",
        {"search_type": search_type, "name": name},
        paginate=True,
        offset=offset,
        count=count,
    )


@mcp.tool()
async def gda_xref(
    xref_type: str,
    name: str,
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """Cross-reference. xref_type: class|method|field|string|resource|all. Paginated by lines."""
    return executor.run(
        "xref",
        {"xref_type": xref_type, "name": name},
        paginate=True,
        offset=offset,
        count=count,
    )


@mcp.tool()
async def gda_raw(cmd: str, offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> dict:
    """Send a raw GDA shell command (advanced). Paginated by lines (default 200)."""
    return executor.run("raw", {"cmd": cmd}, paginate=True, offset=offset, count=count)


@mcp.tool()
async def gda_set_output(file: str) -> dict:
    """Set GDA output file (set -o)."""
    return executor.run("set_output", {"file": file})


def main() -> None:
    parser = argparse.ArgumentParser(description="GDA MCP Server (-sv mode)")
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--gda-exe", default=os.environ.get("GDA_EXE", DEFAULT_GDA_EXE))
    args = parser.parse_args()

    executor.set_gda_exe(args.gda_exe)
    logger.info("[GDA MCP] exe=%s default_sv_port=%s", args.gda_exe, DEFAULT_PORT)

    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
