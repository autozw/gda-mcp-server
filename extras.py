"""Higher-level helpers built on GDA -sv + APK zip (no GUI)."""

from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from .gda_sv import DEFAULT_PAGE_SIZE, executor, paginate_text

_CLASS_LINE_RE = re.compile(
    r"\[class@([0-9a-fA-F]+)\]:\s+(\S+)"
)
_FIELD_RE = re.compile(
    r"^\s*(?:public|protected|private|static|final|volatile|transient|\s)+"
    r".+?\s+(\w+)\s*;\s*$"
)
_BINFO_MAIN_RE = re.compile(r"MainActivity:\s*(\S+)", re.I)
_BINFO_PKG_RE = re.compile(r"Package Name:\s*(\S+)", re.I)

# Android binary XML from GDA axml is already decoded to text XML
_NS = {"android": "http://schemas.android.com/apk/res/android"}


def _need_running() -> Optional[Dict[str, Any]]:
    if not executor.manager.is_running():
        return {
            "ok": False,
            "error": "GDA -sv is not running. Call gda_start_server(apk_file) or gda_attach first.",
        }
    return None


def cache_stats() -> Dict[str, Any]:
    cmd = executor._cache_cmd
    text = executor._cache_text
    lines = 0 if text is None else len(text.splitlines())
    chars = 0 if text is None else len(text)
    return {
        "ok": True,
        "has_cache": text is not None,
        "cached_cmd": cmd,
        "cached_lines": lines,
        "cached_chars": chars,
    }


def clear_cache() -> Dict[str, Any]:
    executor._clear_cache()
    return {"ok": True, "message": "MCP response cache cleared"}


def get_main_activity() -> Dict[str, Any]:
    err = _need_running()
    if err:
        return err
    r = executor.run("binfo")
    if not r.get("ok"):
        return r
    text = r.get("text") or ""
    m = _BINFO_MAIN_RE.search(text)
    pkg = _BINFO_PKG_RE.search(text)
    return {
        "ok": True,
        "main_activity": m.group(1) if m else None,
        "package": pkg.group(1) if pkg else None,
        "source": "binfo",
    }


def get_manifest_component(component_type: str = "activity") -> Dict[str, Any]:
    """component_type: activity|service|receiver|provider|all"""
    err = _need_running()
    if err:
        return err
    r = executor.run("axml")
    if not r.get("ok"):
        return r
    xml_text = r.get("text") or ""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"axml parse failed: {e}", "text": xml_text[:2000]}

    want = component_type.lower().strip()
    tags = {
        "activity": "activity",
        "service": "service",
        "receiver": "receiver",
        "provider": "provider",
    }
    if want == "all":
        selected = list(tags.values())
    elif want in tags:
        selected = [tags[want]]
    else:
        return {
            "ok": False,
            "error": "component_type must be activity|service|receiver|provider|all",
        }

    items: List[Dict[str, Any]] = []
    app = root.find("application")
    if app is None:
        return {"ok": True, "component_type": want, "items": [], "count": 0}

    for tag in selected:
        for node in app.findall(tag):
            name = node.attrib.get("{http://schemas.android.com/apk/res/android}name") or node.attrib.get(
                "name"
            )
            exported = node.attrib.get(
                "{http://schemas.android.com/apk/res/android}exported"
            ) or node.attrib.get("exported")
            items.append(
                {
                    "type": tag,
                    "name": name,
                    "exported": exported,
                }
            )
    return {"ok": True, "component_type": want, "count": len(items), "items": items}


def _parse_class_lines(text: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for line in text.splitlines():
        m = _CLASS_LINE_RE.search(line)
        if m:
            out.append({"idx": m.group(1), "name": m.group(2)})
    return out


def find_classes(
    name: str = ".",
    with_package: bool = True,
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
) -> Dict[str, Any]:
    """List/search classes via GDA find -C/-c. Default name='.' matches many packages."""
    err = _need_running()
    if err:
        return err
    stype = "class_with_package" if with_package else "class"
    r = executor.run(
        "find",
        {"search_type": stype, "name": name},
        paginate=False,
    )
    if not r.get("ok"):
        return r
    classes = _parse_class_lines(r.get("text") or "")
    total = len(classes)
    off = max(0, int(offset))
    lim = count if count and count > 0 else DEFAULT_PAGE_SIZE
    page = classes[off : off + lim]
    next_off = off + len(page)
    return {
        "ok": True,
        "cmd": r.get("cmd"),
        "total": total,
        "offset": off,
        "count": len(page),
        "truncated": next_off < total,
        "next_offset": next_off if next_off < total else None,
        "items": page,
    }


def get_package_tree(name: str = ".", max_packages: int = 500) -> Dict[str, Any]:
    err = _need_running()
    if err:
        return err
    r = find_classes(name=name, with_package=True, offset=0, count=10_000_000)
    if not r.get("ok"):
        return r
    tree: Dict[str, List[str]] = defaultdict(list)
    for item in r.get("items") or []:
        cname = item["name"]
        if "." in cname:
            pkg, _, cls = cname.rpartition(".")
        else:
            pkg, cls = "", cname
        tree[pkg].append(cls)
    packages = sorted(tree.keys())
    if len(packages) > max_packages:
        packages = packages[:max_packages]
        truncated = True
    else:
        truncated = False
    return {
        "ok": True,
        "package_count": len(tree),
        "class_count": r.get("total"),
        "truncated": truncated,
        "packages": {p: sorted(tree[p]) for p in packages},
    }


def get_fields_of_class(cname_or_idx: str, offset: int = 0, count: int = DEFAULT_PAGE_SIZE) -> Dict[str, Any]:
    """Parse field declarations from gda_dec output (best-effort)."""
    err = _need_running()
    if err:
        return err
    target = cname_or_idx.strip()
    if not target.startswith("class@") and not target.startswith("-"):
        # Prefer class@idx if given as hex-like; else try find then dec
        if re.fullmatch(r"[0-9a-fA-F]+", target):
            target = f"class@{target}"
        else:
            fr = executor.run(
                "find",
                {"search_type": "class_with_package", "name": target},
                paginate=False,
            )
            if fr.get("ok"):
                classes = _parse_class_lines(fr.get("text") or "")
                exact = [c for c in classes if c["name"] == target or c["name"].endswith("." + target)]
                if exact:
                    target = f"class@{exact[0]['idx']}"
                elif classes:
                    target = f"class@{classes[0]['idx']}"
            target = target if target.startswith("class@") else f"-c {cname_or_idx}"

    r = executor.run("dec", {"target": target}, paginate=False)
    if not r.get("ok"):
        return r
    text = r.get("text") or ""
    fields: List[str] = []
    for line in text.splitlines():
        # skip methods / annotations-ish
        if "(" in line or line.strip().startswith("@"):
            continue
        m = _FIELD_RE.match(line)
        if m:
            fields.append(line.strip())
    page = paginate_text("\n".join(fields) + ("\n" if fields else ""), offset=offset, count=count)
    return {
        "ok": True,
        "target": target,
        "total_fields": len(fields),
        "offset": page["offset"],
        "count": page["count"],
        "truncated": page["truncated"],
        "next_offset": page["next_offset"],
        "fields": [ln for ln in page["text"].splitlines() if ln.strip()],
    }


def get_main_application_classes(
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
    include_code: bool = False,
) -> Dict[str, Any]:
    """Classes under the app package from binfo/axml."""
    info = get_main_activity()
    if not info.get("ok"):
        return info
    pkg = info.get("package")
    if not pkg:
        return {"ok": False, "error": "package name not found in binfo"}
    listed = find_classes(name=pkg, with_package=True, offset=offset, count=count)
    if not listed.get("ok"):
        return listed
    result: Dict[str, Any] = {
        "ok": True,
        "package": pkg,
        "main_activity": info.get("main_activity"),
        "total": listed.get("total"),
        "offset": listed.get("offset"),
        "count": listed.get("count"),
        "truncated": listed.get("truncated"),
        "next_offset": listed.get("next_offset"),
        "names": [i["name"] for i in listed.get("items") or []],
        "items": listed.get("items"),
    }
    if include_code:
        codes = []
        for item in (listed.get("items") or [])[: min(20, len(listed.get("items") or []))]:
            dr = executor.run("dec", {"target": f"class@{item['idx']}"}, paginate=True, offset=0, count=80)
            codes.append(
                {
                    "name": item["name"],
                    "idx": item["idx"],
                    "code": dr.get("text") if dr.get("ok") else dr.get("error"),
                }
            )
        result["codes"] = codes
        if listed.get("count", 0) > 20:
            result["code_note"] = "Only first 20 classes on this page include code snippets."
    return result


def list_resource_files(
    offset: int = 0,
    count: int = DEFAULT_PAGE_SIZE,
    prefix: str = "res/",
) -> Dict[str, Any]:
    """List files inside the opened APK (zip), no GUI."""
    apk = executor.manager.apk_path
    if not apk:
        return {"ok": False, "error": "No apk_path (start server with an APK first)."}
    try:
        with zipfile.ZipFile(apk, "r") as zf:
            names = sorted(
                n for n in zf.namelist() if not n.endswith("/") and n.startswith(prefix)
            )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    off = max(0, int(offset))
    lim = count if count and count > 0 else DEFAULT_PAGE_SIZE
    page = names[off : off + lim]
    next_off = off + len(page)
    return {
        "ok": True,
        "apk": apk,
        "prefix": prefix,
        "total": len(names),
        "offset": off,
        "count": len(page),
        "truncated": next_off < len(names),
        "next_offset": next_off if next_off < len(names) else None,
        "files": page,
    }


def get_resource_file(path: str, max_chars: int = 100_000) -> Dict[str, Any]:
    """Read a text-ish entry from the APK zip. Binary files return size + hex head."""
    apk = executor.manager.apk_path
    if not apk:
        return {"ok": False, "error": "No apk_path (start server with an APK first)."}
    path = path.lstrip("/")
    try:
        with zipfile.ZipFile(apk, "r") as zf:
            data = zf.read(path)
    except KeyError:
        return {"ok": False, "error": f"not found in apk: {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Heuristic: try utf-8 text
    try:
        text = data.decode("utf-8")
        truncated = len(text) > max_chars
        return {
            "ok": True,
            "path": path,
            "size": len(data),
            "encoding": "utf-8",
            "truncated": truncated,
            "text": text[:max_chars],
        }
    except UnicodeDecodeError:
        head = data[:64].hex(" ")
        return {
            "ok": True,
            "path": path,
            "size": len(data),
            "encoding": "binary",
            "hex_head": head,
            "note": "Binary resource; only hex head returned.",
        }
