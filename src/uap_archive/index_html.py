"""Offline static HTML browser for the manifest.

Renders one self-contained ``site/index.html`` (~150 KB for the current
war.gov manifest) with embedded JSON, vanilla JS filter/sort, no external
dependencies. Works under ``python -m http.server`` or ``file://``,
which makes it USB-stick portable for readers on bad connections.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path

from uap_archive.manifest import DigitalObject, iter_manifest


def _human_bytes(n: int | None) -> str:
    if not n:
        return "—"
    val = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024:
            return f"{val:.1f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024
    return f"{val:.1f} PB"


def _row(obj: DigitalObject) -> dict:
    return {
        "agency": obj.agency,
        "title": obj.title or obj.object_filename,
        "filename": obj.object_filename,
        "media_type": obj.media_type or "",
        "size_bytes": obj.size_bytes or 0,
        "size_human": _human_bytes(obj.size_bytes),
        "source": obj.source,
        "url": obj.object_url,
        "naid": obj.naid,
        "sha256_short": (obj.sha256 or "")[:12],
    }


_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>UAP Disclosure Archive — manifest browser</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--fg:#222;--bg:#fafafa;--accent:#1a4d7a;--rule:#ddd;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 system-ui,-apple-system,sans-serif;color:var(--fg);background:var(--bg)}
header{padding:1rem 1.5rem;background:#fff;border-bottom:1px solid var(--rule)}
header h1{margin:0 0 .25rem;font-size:1.25rem;color:var(--accent)}
header p{margin:0;color:#555;font-size:.9rem}
.bar{padding:.6rem 1.5rem;background:#fff;border-bottom:1px solid var(--rule);display:flex;gap:1rem;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:10}
.bar input{flex:1;min-width:200px;padding:.4rem .6rem;border:1px solid #bbb;border-radius:3px;font:inherit}
.bar select{padding:.4rem;border:1px solid #bbb;border-radius:3px;font:inherit;background:#fff}
.bar .count{color:#555;font-size:.85rem;white-space:nowrap}
.stats{padding:.6rem 1.5rem;background:#f0f4f8;border-bottom:1px solid var(--rule);font-size:.85rem;color:#444;display:flex;gap:1.5rem;flex-wrap:wrap}
.stats b{color:var(--accent)}
table{width:100%;border-collapse:collapse;background:#fff}
th,td{padding:.45rem .8rem;text-align:left;border-bottom:1px solid var(--rule);vertical-align:top}
th{background:#f4f4f4;font-weight:600;font-size:.85rem;color:#444;cursor:pointer;user-select:none;position:sticky;top:3.6rem;z-index:5}
th:hover{background:#e8e8e8}
th.sort-asc::after{content:" ▲";color:var(--accent);font-size:.7em}
th.sort-desc::after{content:" ▼";color:var(--accent);font-size:.7em}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
td.mono{font-family:var(--mono);font-size:.82rem}
td a{color:var(--accent);text-decoration:none}
td a:hover{text-decoration:underline}
.agency{display:inline-block;padding:.05rem .4rem;border-radius:3px;background:#e8f0f7;color:var(--accent);font-size:.78rem;font-weight:600}
.agency.FBI{background:#fde8e8;color:#94312a}
.agency.DOW{background:#e6f0d9;color:#3c5d1a}
.agency.NASA{background:#e8e6f7;color:#3a2d7a}
.agency.DOS{background:#fff4d6;color:#7a5300}
.agency.NRC{background:#f7e6f0;color:#7a1a5d}
.agency.ODNI{background:#d9e8f7;color:#1a3a7a}
.agency.NSA{background:#e8e8e8;color:#444}
footer{padding:1rem 1.5rem;color:#777;font-size:.8rem;text-align:center;border-top:1px solid var(--rule);margin-top:1rem}
footer a{color:var(--accent)}
.empty{padding:2rem;text-align:center;color:#777;font-style:italic}
</style></head>
<body>
<header>
<h1>UAP Disclosure Archive</h1>
<p>Manifest browser. All entries link to original government source URLs.</p>
</header>
<div class="stats" id="stats"></div>
<div class="bar">
<input id="q" type="search" placeholder="filter — title, filename, NAID, sha256…" autocomplete="off">
<select id="agency"><option value="">all agencies</option></select>
<select id="type"><option value="">all media types</option></select>
<span class="count" id="count"></span>
</div>
<table id="t">
<thead><tr>
<th data-sort="agency">Agency</th>
<th data-sort="title">Title</th>
<th data-sort="filename">Filename</th>
<th data-sort="media_type">Type</th>
<th data-sort="size_bytes" class="num">Size</th>
<th data-sort="naid" class="num">NAID</th>
<th>Source</th>
</tr></thead>
<tbody id="tb"></tbody>
</table>
<footer>
Generated <span id="gen"></span> · __N_RECORDS__ records · __SOURCES_LABEL__<br>
Source data: U.S. federal government works, public domain (17 U.S.C. § 105).
Mirror code &amp; manifests: <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>.
</footer>
<script id="data" type="application/json">__DATA_JSON__</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const meta = __META_JSON__;
const $ = (id) => document.getElementById(id);

function render() {{
  const q = $("q").value.toLowerCase().trim();
  const ag = $("agency").value;
  const ty = $("type").value;
  const rows = data.filter(r => {{
    if (ag && r.agency !== ag) return false;
    if (ty && !(r.media_type || "").startsWith(ty)) return false;
    if (!q) return true;
    return [r.title, r.filename, r.url, String(r.naid || ""), r.sha256_short, r.agency]
      .some(v => (v || "").toLowerCase().includes(q));
  }});
  if (sortKey) {{
    rows.sort((a, b) => {{
      let av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" || typeof bv === "number") {{
        av = av || 0; bv = bv || 0;
        return sortDir * (av - bv);
      }}
      return sortDir * String(av || "").localeCompare(String(bv || ""));
    }});
  }}
  const totalBytes = rows.reduce((s, r) => s + (r.size_bytes || 0), 0);
  $("count").textContent = `${{rows.length}} of ${{data.length}} · ${{humanBytes(totalBytes)}}`;
  const tb = $("tb");
  if (!rows.length) {{
    tb.innerHTML = '<tr><td colspan="7" class="empty">No matching records.</td></tr>';
    return;
  }}
  tb.innerHTML = rows.map(r => `<tr>
    <td><span class="agency ${{r.agency}}">${{r.agency}}</span></td>
    <td>${{esc(r.title)}}</td>
    <td class="mono">${{esc(r.filename)}}</td>
    <td>${{esc(r.media_type)}}</td>
    <td class="num">${{r.size_human}}</td>
    <td class="num">${{r.naid || ""}}</td>
    <td><a href="${{esc(r.url)}}" rel="noopener" target="_blank">${{esc(r.source)}} ↗</a></td>
  </tr>`).join("");
}}

function esc(s) {{
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function humanBytes(n) {{
  if (!n) return "0 B";
  const u = ["B","KB","MB","GB","TB"]; let i = 0;
  while (n >= 1024 && i < u.length-1) {{ n /= 1024; i++; }}
  return i === 0 ? `${{n}} B` : `${{n.toFixed(1)}} ${{u[i]}}`;
}}

let sortKey = "agency", sortDir = 1;
document.querySelectorAll("th[data-sort]").forEach(th => {{
  th.addEventListener("click", () => {{
    const k = th.dataset.sort;
    sortDir = (sortKey === k) ? -sortDir : 1;
    sortKey = k;
    document.querySelectorAll("th").forEach(x => x.classList.remove("sort-asc", "sort-desc"));
    th.classList.add(sortDir > 0 ? "sort-asc" : "sort-desc");
    render();
  }});
}});
$("q").addEventListener("input", render);
$("agency").addEventListener("change", render);
$("type").addEventListener("change", render);

const agencies = [...new Set(data.map(r => r.agency))].sort();
agencies.forEach(a => {{
  const o = document.createElement("option"); o.value = a; o.textContent = a;
  $("agency").appendChild(o);
}});
const types = [...new Set(data.map(r => (r.media_type || "").split("/")[0]).filter(Boolean))].sort();
types.forEach(t => {{
  const o = document.createElement("option"); o.value = t; o.textContent = t;
  $("type").appendChild(o);
}});

$("stats").innerHTML = meta.agencies.map(a =>
  `<span><b>${{a.code}}</b>: ${{a.count}} records · ${{a.size}}</span>`
).join("") + ` <span>Total: <b>${{meta.total_count}}</b> records · <b>${{meta.total_size}}</b></span>`;
$("gen").textContent = meta.generated_at;
render();
</script>
</body></html>
"""


def build_site(manifests_dir: Path, out_path: Path) -> dict:
    """Render the static index from every per-agency JSONL into one HTML file.

    Returns a small summary dict useful for tests + CLI output.
    """
    rows: list[dict] = []
    by_agency: dict[str, list[DigitalObject]] = {}
    for jsonl in sorted((manifests_dir / "by-agency").glob("*.jsonl")):
        for obj in iter_manifest(jsonl):
            rows.append(_row(obj))
            by_agency.setdefault(obj.agency, []).append(obj)

    agency_stats = []
    for code in sorted(by_agency):
        objs = by_agency[code]
        total = sum((o.size_bytes or 0) for o in objs)
        agency_stats.append({"code": code, "count": len(objs), "size": _human_bytes(total)})

    total_size = sum(r["size_bytes"] for r in rows)
    sources_seen = sorted({r["source"] for r in rows})

    meta = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "agencies": agency_stats,
        "total_count": len(rows),
        "total_size": _human_bytes(total_size),
    }

    rendered = (
        _TEMPLATE
        .replace("__DATA_JSON__", json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
        .replace("__META_JSON__", json.dumps(meta, ensure_ascii=False))
        .replace("__N_RECORDS__", str(len(rows)))
        .replace("__SOURCES_LABEL__", html.escape(", ".join(sources_seen) or "no sources yet"))
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    return {
        "out": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "record_count": len(rows),
        "agencies": agency_stats,
    }
