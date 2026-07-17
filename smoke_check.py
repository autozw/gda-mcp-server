"""Quick offline checks for -sv command builder / pagination (no GDA required)."""

from src.gda_sv import build_command, executor, paginate_text


def test_build():
    assert build_command("binfo", {}) == "binfo"
    assert build_command("listm", {"cname": "a.b.C"}) == "listm a.b.C"
    assert build_command("find", {"search_type": "string", "name": "http"}) == "find -s http"
    assert build_command("xref", {"xref_type": "method", "name": "send"}) == "xref -m send"
    assert build_command("dec", {"target": "-c Lcom/foo;"}) == "dec -c Lcom/foo;"
    print("build_command ok")


def test_paginate():
    text = "\n".join(f"line{i}" for i in range(500))
    p0 = paginate_text(text, offset=0, count=100)
    assert p0["total_lines"] == 500
    assert p0["count"] == 100
    assert p0["truncated"] is True
    assert p0["next_offset"] == 100
    assert p0["text"].startswith("line0")

    p1 = paginate_text(text, offset=100, count=100)
    assert p1["offset"] == 100
    assert "line100" in p1["text"]
    assert p1["next_offset"] == 200

    p_last = paginate_text(text, offset=450, count=100)
    assert p_last["count"] == 50
    assert p_last["truncated"] is False
    assert p_last["next_offset"] is None
    print("paginate_text ok")


if __name__ == "__main__":
    test_build()
    test_paginate()
    print("status:", executor.status())
