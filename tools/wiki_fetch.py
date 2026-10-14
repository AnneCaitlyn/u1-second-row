"""Save Snapmaker wiki pages as plain text (the wiki is JS-rendered; guests can't use the source API).

    python tools/wiki_fetch.py OUT_DIR PATH [PATH ...]

PATH is the wiki path after /en/, e.g. snapmaker_u1/troubleshooting/toolhead_replacement_guide.
Images are kept as [img URL] lines so they can be downloaded later.
"""
import html
import pathlib
import re
import sys
import urllib.request

BASE = "https://wiki.snapmaker.com"


def page_text(path):
    req = urllib.request.Request(f"{BASE}/en/{path}", headers={"User-Agent": "Mozilla/5.0"})
    s = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    title = re.search(r"<title>(.*?)</title>", s, re.S)
    m = re.search(r'<template slot="contents">(.*?)</template>', s, re.S)
    t = m.group(1) if m else ""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", t, flags=re.S)
    t = re.sub(r'<img[^>]*src="([^"]+)"[^>]*>', lambda m: f"\n[img {BASE}{m.group(1)}]\n"
               if m.group(1).startswith("/") else f"\n[img {m.group(1)}]\n", t)
    t = re.sub(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', r"\2 <\1>", t, flags=re.S)
    t = re.sub(r"<h(\d)[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", t)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>|</tr>|</div>", "\n", t)
    t = re.sub(r"<t[dh][^>]*>", " | ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("¶", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t).strip()
    head = html.unescape(title.group(1).strip()) if title else path
    return f"# {head}\n\nSource: {BASE}/en/{path}\n\n{t}\n"


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for path in sys.argv[2:]:
        try:
            text = page_text(path)
        except Exception as e:  # keep going; report at the end of the line
            print(f"FAIL {path}: {e}")
            continue
        name = path.rstrip("/").split("/")[-1].lower() + ".md"
        (out / name).write_text(text, encoding="utf-8")
        print(f"ok   {name} ({len(text)} chars)")


if __name__ == "__main__":
    main()
