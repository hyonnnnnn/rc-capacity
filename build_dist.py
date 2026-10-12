"""rc-capacity.html → dist/ (연구실 배포용 PWA)

dist/index.html  : 단일 파일. ExcelJS 를 안에 넣어 인터넷 없이도 엑셀 내보내기까지 동작.
                   아티팩트 전용 저장 기능(claude.use("downloads")) 대신 브라우저 표준 다운로드(<a download>)를 씀.
dist/manifest.webmanifest, sw.js, icon-*.png : 스마트폰 "홈 화면에 추가" + 오프라인 캐시 (https 로 올렸을 때만 동작).

실행: python3 build_dist.py
"""
import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
SRC = (ROOT / "rc-capacity.html").read_text(encoding="utf-8")
LIB = (ROOT / "lib" / "exceljs.min.js").read_text(encoding="utf-8")
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)
VER = datetime.datetime.now().strftime("%Y%m%d-%H%M")

# 1) CDN 스크립트 → 인라인
cdn = re.search(r'<script src="https://cdnjs\.cloudflare\.com/ajax/libs/exceljs/[^"]+"></script>', SRC)
assert cdn, "ExcelJS script tag not found"
body = SRC.replace(cdn.group(0), "<script>" + LIB.replace("</script>", "<\\/script>") + "</script>")

# 2) 저장 기능 대체: 아티팩트 런타임이 없으면 표준 다운로드
SHIM = """<script>
if (!window.claude) window.claude = { use: async n => n !== "downloads" ? null : { save: async ({ filename, data }) => {
  const type = filename.endsWith(".html") ? "text/html;charset=utf-8" : filename.endsWith(".json") ? "application/json" : filename.endsWith(".png") ? "image/png" : "application/octet-stream";
  const blob = data instanceof Blob ? data : new Blob([data], { type });
  if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {   // 데스크톱 프로그램(app.py): OS 저장 대화상자
    const b64 = btoa(Array.from(new Uint8Array(await blob.arrayBuffer()), c => String.fromCharCode(c)).join(""));
    const ok = await window.pywebview.api.save_file(filename, b64); if (!ok) throw new Error("cancelled"); return; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); } } };
</script>"""
SW_REG = """<script>
if ("serviceWorker" in navigator && location.protocol.startsWith("http")) navigator.serviceWorker.register("./sw.js").catch(() => {});
</script>"""
HEAD = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f5f8b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="build" content="{VER}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-192.png">
<style>html{{margin:0}}body{{margin:0}}</style>
</head>
<body>
{SHIM}
"""
(DIST / "index.html").write_text(HEAD + body + "\n" + SW_REG + "\n</body>\n</html>\n", encoding="utf-8")

# 3) manifest + service worker
(DIST / "manifest.webmanifest").write_text("""{
  "name": "RC 단면 내력 계산기 · 3D FEM",
  "short_name": "RC 내력",
  "lang": "ko",
  "start_url": "./index.html",
  "scope": "./",
  "display": "standalone",
  "background_color": "#eef0f1",
  "theme_color": "#1f5f8b",
  "description": "RC·복합 단면 휨·전단·축 내력, M-N 상관도, M-φ, 사용성, 보 해석, 3D 비선형 FEM (土木学会 示方書)",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
""", encoding="utf-8")
(DIST / "sw.js").write_text(f"""// 오프라인 캐시: index.html 은 네트워크 우선(새 버전 반영), 나머지는 캐시 우선
const CACHE = "rc-capacity-{VER}";
const ASSETS = ["./", "./index.html", "./manifest.webmanifest", "./icon-192.png", "./icon-512.png", "./icon-512-maskable.png"];
self.addEventListener("install", e => {{ e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting())); }});
self.addEventListener("activate", e => {{ e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); }});
self.addEventListener("fetch", e => {{
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  if (url.origin === location.origin && (url.pathname.endsWith("/") || url.pathname.endsWith("index.html")))
    e.respondWith(fetch(e.request).then(r => {{ const cp = r.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); return r; }}).catch(() => caches.match(e.request)));
  else e.respondWith(caches.match(e.request).then(r => r || fetch(e.request).then(res => {{ if (url.origin === location.origin || url.hostname.includes("gstatic") || url.hostname.includes("googleapis")) {{ const cp = res.clone(); caches.open(CACHE).then(c => c.put(e.request, cp)); }} return res; }}).catch(() => r)));
}});
""", encoding="utf-8")

# 4) 아이콘: 단면 + 철근 그림 (PIL)
from PIL import Image, ImageDraw

def icon(size, maskable=False):
    im = Image.new("RGB", (size, size), "#1f5f8b")
    d = ImageDraw.Draw(im)
    pad = size * (0.2 if maskable else 0.12)
    x0, y0, x1, y1 = pad, pad, size - pad, size - pad
    d.rounded_rectangle([x0, y0, x1, y1], radius=size * 0.06, fill="#eef0f1")            # 단면
    d.rectangle([x0, y0, x1, y0 + (y1 - y0) * 0.3], fill="#9fb7c8")                       # 압축 블록
    r = (x1 - x0) * 0.06
    for q in (0.25, 0.5, 0.75):                                                           # 인장철근 3본
        cx, cy = x0 + (x1 - x0) * q, y1 - (y1 - y0) * 0.16
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#2b3a42")
    d.line([x0, y0 + (y1 - y0) * 0.3, x1, y0 + (y1 - y0) * 0.3], fill="#1f5f8b", width=max(2, size // 64))
    return im

icon(192).save(DIST / "icon-192.png")
icon(512).save(DIST / "icon-512.png")
icon(512, maskable=True).save(DIST / "icon-512-maskable.png")
print("built", VER, "→", DIST, "index.html", (DIST / "index.html").stat().st_size // 1024, "KB")
