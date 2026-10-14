#!/usr/bin/env python3
"""발표 덱 HTML을 기계적으로 검사한다.

여기 있는 검사 항목은 전부 실제로 한 번씩 터졌던 것들이다.
추측으로 넣은 규칙은 없다. 자세한 재현 경위는 references/failure-catalog.md 참고.

사용:
    python3 <skill-dir>/scripts/deck_verify.py <deck.html> [--json]

종료 코드:
    0  통과 (경고만 있을 수 있음)
    1  오류 있음
    2  실행 불가 (파일 없음 / 크롬 없음)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANVAS_W, CANVAS_H = 1280, 720
FONT_FLOOR_RATIO = 0.02          # 슬라이드 높이의 2.0%
FONT_FLOOR_PX = CANVAS_H * FONT_FLOOR_RATIO   # 14.4px

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


class Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, check: str, message: str, where: str = "") -> None:
        self.items.append({"level": level, "check": check, "message": message, "where": where})

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "error"]

    @property
    def warnings(self) -> list[dict]:
        return [i for i in self.items if i["level"] == "warn"]


# ─────────────────────────────────────────────────────────────
# 정적 검사 — 브라우저 없이 소스만 읽는다
# ─────────────────────────────────────────────────────────────

def check_print_isolation(src: str, f: Findings) -> None:
    """반응형 @media가 인쇄로 새면 다단 레이아웃이 1열로 무너진다.

    실제 사고: 첫 PDF에서 모든 그리드가 세로로 쌓이고 글자가 겹쳤다.
    """
    for m in re.finditer(r"@media\s*([^{]+)\{", src):
        cond = m.group(1).strip()
        if "max-width" in cond and "screen" not in cond and "print" not in cond:
            f.add("error", "print-isolation",
                  f"@media({cond}) 에 screen 한정이 없다. 인쇄에도 적용되어 PDF가 무너진다.",
                  "screen and (max-width:...) 로 바꾸거나 블록을 제거할 것")


def check_print_setup(src: str, f: Findings) -> None:
    """@page 와 print-color-adjust 가 없으면 PDF가 A4 세로로 나오거나 색이 빠진다."""
    print_block = re.search(r"@media\s+print\s*\{(.*?)\n    \}", src, re.S)
    if not print_block:
        f.add("warn", "print-setup", "@media print 블록이 없다. PDF 출력을 쓰지 않는 덱이면 무시해도 된다.")
        return
    body = print_block.group(1)
    if "@page" not in body:
        f.add("error", "print-setup", "@page{size:...} 가 없다. PDF가 기본 용지(A4 세로)에 축소·분할된다.")
    if "print-color-adjust" not in body:
        f.add("error", "print-setup",
              "print-color-adjust:exact 가 없다. '배경 그래픽' 체크를 안 하면 배경·보더 색이 전부 빠진다.")
    # JS가 인라인 transform 을 넣는 덱에만 해당한다. 단일 페이지처럼 스케일을
    # 쓰지 않는 파일에는 무력화할 대상이 없다.
    scales_by_js = re.search(r"\.style\.transform\s*=", src)
    # .deck 를 직접 겨냥한 것이어야 한다. .slide 쪽 transform:none 은 이 문제를 못 막는다.
    if scales_by_js and not re.search(r"\.deck\s*\{[^}]*transform:\s*none\s*!important", body):
        f.add("error", "print-setup",
              "인쇄에서 .deck{transform:none!important} 가 없다. "
              "JS가 넣은 인라인 scale이 살아남아 페이지가 한쪽으로 몰린다.")


def check_fixed_font_sizes(src: str, f: Findings) -> None:
    """고정 캔버스에서는 하한 미만 폰트를 소스만으로 잡을 수 있다."""
    for m in re.finditer(r"font-size:\s*(\d+(?:\.\d+)?)px", src):
        px = float(m.group(1))
        if px < FONT_FLOOR_PX:
            line = src[: m.start()].count("\n") + 1
            f.add("error", "font-floor",
                  f"font-size:{px:g}px 는 하한 {FONT_FLOOR_PX:g}px(슬라이드 높이의 2%) 미만이다. 뒷줄에서 안 읽힌다.",
                  f"line {line}")


def check_dead_css(src: str, f: Findings) -> None:
    """죽은 셀렉터는 색 별칭이 이중으로 싸우는 사고의 전조다."""
    style = re.search(r"<style>(.*?)</style>", src, re.S)
    if not style:
        return
    css = style.group(1)
    # <style> 바깥 전체를 본다. class="service ${s.state}" 처럼 JS 템플릿 리터럴로
    # 만들어지는 클래스는 class 속성만 훑어서는 못 잡는다. 이름이 어디에라도
    # 등장하면 사용된 것으로 본다 — 오탐보다 미탐이 낫다.
    outside = src[: src.index("<style>")] + src[src.index("</style>") :]
    used_classes = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", outside))
    used_classes.update({"active", "past"})

    declared = set(re.findall(r"\.([a-z][a-z0-9-]+)", css))
    noise = {"png", "jpg", "jpeg", "svg", "webp", "html", "min", "max"}
    dead = sorted(declared - used_classes - noise)
    if dead:
        f.add("warn", "dead-css",
              f"쓰이지 않는 셀렉터 {len(dead)}개: {', '.join(dead[:12])}{' …' if len(dead) > 12 else ''}")


def check_asset_paths(src: str, path: Path, f: Findings) -> None:
    """덱 폴더 밖을 가리키면 폴더만 압축해 넘길 때 이미지가 깨진다."""
    base = path.parent
    for m in re.finditer(r'(?:src="|url\(")([^"]+\.(?:png|jpg|jpeg|webp|svg))"?', src):
        ref = m.group(1)
        if ref.startswith(("http://", "https://", "data:")):
            continue
        if ref.startswith("../"):
            f.add("error", "asset-path",
                  f"'{ref}' 가 덱 폴더 밖을 가리킨다. 폴더만 옮기면 깨진다.", ref)
        elif not (base / ref).exists():
            f.add("error", "asset-path", f"'{ref}' 파일이 없다.", ref)


def check_badge_semantics(src: str, f: Findings) -> None:
    """같은 배지 토큰을 두 의미축에 쓰면 청중이 범례를 신뢰하지 못한다.

    실제 사고: badge.plan 이 '사람이 담당' / 'Sprint 1' / '도메인 전환안'
    세 가지 뜻으로 동시에 쓰였다.
    """
    labels: dict[str, set[str]] = {}
    for m in re.finditer(r'<span class="badge([^"]*)"[^>]*>([^<]+)</span>', src):
        variant = " ".join(sorted(m.group(1).split())) or "(기본)"
        labels.setdefault(variant, set()).add(m.group(2).strip())
    for variant, texts in labels.items():
        if len(texts) > 1:
            f.add("info", "badge-semantics",
                  f"배지 '{variant}' 문구가 {len(texts)}가지다: {' / '.join(sorted(texts))}",
                  "모두 같은 의미축(구현 상태)인지 확인할 것. 역할·단계처럼 축이 다르면 별도 토큰을 쓴다")


def check_legend_consistency(src: str, f: Findings) -> None:
    """범례 색과 카드 색이 반대면 발표 중에 반드시 질문이 나온다."""
    if 'class="legend"' not in src:
        return
    outside = src[: src.index("<style>")] + src[src.index("</style>") :]
    pairs = [("badge plan", "proposed"), ("badge next", "backlog")]
    for badge, state in pairs:
        if badge in src and state not in outside:
            f.add("warn", "legend",
                  f"범례에 '{badge}' 가 있는데 대응하는 '{state}' 상태 카드가 없다. 범례와 카드가 어긋난다.")


def check_page_numbers(src: str, f: Findings) -> None:
    slides = re.findall(r'<section class="slide[^"]*"', src)
    auto = src.count('class="page"')
    hard = re.findall(r"<span>(\d{2})\s*/\s*(\d+)</span>", src)
    if auto and auto == len(slides):
        return  # 엔진이 자동으로 채운다
    if hard:
        total = {int(t) for _, t in hard}
        nums = [int(n) for n, _ in hard]
        if len(total) > 1 or (total and total.pop() != len(slides)):
            f.add("error", "page-numbers",
                  f"슬라이드는 {len(slides)}장인데 푸터 총 장수가 맞지 않는다.")
        if nums != sorted(nums) or nums != list(range(1, len(nums) + 1)):
            f.add("error", "page-numbers", f"페이지 번호가 연속이 아니다: {nums}")
        f.add("warn", "page-numbers",
              "번호가 하드코딩되어 있다. <span class=\"page\"></span> 로 두면 엔진이 자동으로 채운다.")


# ─────────────────────────────────────────────────────────────
# 동적 검사 — 실제 뷰포트에서 잰다
# ─────────────────────────────────────────────────────────────

PROBE_PAGE = """<!doctype html><meta charset="utf-8"><body><script>
/* 덱을 실제 크기의 iframe 에 띄워서 재고, 결과를 로컬 서버로 돌려준다.
   .deck 에 인라인 스타일로 크기를 강제하는 방식은 절대 쓰지 않는다.
   vh/dvh 가 바깥 창을 계속 따라가서 존재하지 않는 넘침이 계산된다. */
const FLOOR = __FLOOR__, W = __W__, H = __H__;
function send(o){ fetch('/__result', {method:'POST', body: JSON.stringify(o)}); }
const f = document.createElement('iframe');
f.style.cssText = `position:fixed;left:-99999px;top:0;width:${W}px;height:${H}px;border:0`;
f.src = '__DECK__';
document.body.appendChild(f);
setTimeout(() => send({error: 'timeout: 덱이 로드되지 않았다'}), 20000);
f.onload = () => setTimeout(() => {
  const out = {overflow: [], small: [], canvas: null, slides: 0};
  try {
    const d = f.contentDocument;
    const deck = d.querySelector('.deck');
    out.canvas = deck ? deck.offsetWidth + 'x' + deck.offsetHeight : null;
    const slides = [...d.querySelectorAll('.slide')];
    out.slides = slides.length;
    slides.forEach((s, i) => {
      const prev = s.className;
      s.classList.add('active');
      const c = s.querySelector('.content');
      if (c) {
        const ov = Math.round(c.scrollHeight - c.clientHeight);
        if (ov > 2) out.overflow.push({slide: i + 1, title: s.dataset.title || '', px: ov});
      }
      s.querySelectorAll('*').forEach(el => {
        if (!el.childElementCount && el.textContent.trim()) {
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < FLOOR) out.small.push({slide: i + 1, sel: (el.className || el.tagName) + '', px: fs});
        }
      });
      s.className = prev;
    });
  } catch (e) { out.error = String(e); }
  send(out);
}, 500);
</script></body>"""


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def _serve(directory: Path):
    """덱 폴더를 임시 HTTP 서버로 띄우고 /__result POST 를 받는다.

    file:// 대신 http:// 를 쓰는 이유는 iframe contentDocument 접근이
    same-origin 으로 자연스럽게 풀리기 때문이다.
    """
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    box: dict = {}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(directory), **kw)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            box["raw"] = self.rfile.read(n).decode("utf-8", "replace")
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, box


def run_dynamic(path: Path, f: Findings) -> dict | None:
    """헤드리스 크롬에서 실제로 렌더해 넘침과 폰트 하한을 잰다.

    고정 캔버스이므로 창 크기 하나만 재면 충분하다. 유동 레이아웃이었다면
    해상도마다 따로 재야 했다 — 고정 캔버스로 옮긴 이유 중 하나다.
    """
    import time

    chrome = find_chrome()
    if not chrome:
        f.add("warn", "render", "크롬을 찾지 못해 렌더 검사를 건너뛴다. 정적 검사만 수행했다.")
        return None

    probe = path.parent / f".deck_probe_{os.getpid()}.html"
    probe.write_text(
        PROBE_PAGE.replace("__FLOOR__", str(FONT_FLOOR_PX))
                  .replace("__W__", str(CANVAS_W))
                  .replace("__H__", str(CANVAS_H))
                  .replace("__DECK__", path.name),
        encoding="utf-8")

    try:
        srv, box = _serve(path.parent)
    except OSError as exc:
        probe.unlink(missing_ok=True)
        f.add("warn", "render",
              f"로컬 렌더 서버를 열지 못해 정적 검사만 수행했다: {exc}")
        return None
    port = srv.server_address[1]
    proc = None
    tmpdir = tempfile.mkdtemp()
    try:
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--user-data-dir={tmpdir}",
             f"--window-size={CANVAS_W},{CANVAS_H}",
             f"http://127.0.0.1:{port}/{probe.name}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 45
        while time.time() < deadline and "raw" not in box:
            time.sleep(0.25)
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        srv.shutdown()
        probe.unlink(missing_ok=True)
        shutil.rmtree(tmpdir, ignore_errors=True)

    if "raw" not in box:
        f.add("warn", "render", "렌더 결과를 받지 못했다. 정적 검사 결과만 신뢰할 것.")
        return None
    try:
        data = json.loads(box["raw"])
    except json.JSONDecodeError as exc:
        f.add("warn", "render", f"렌더 결과를 해석하지 못했다: {exc}")
        return None

    if data.get("error"):
        f.add("warn", "render", f"프로브 오류: {data['error']}")
        return data

    if data.get("canvas") and data["canvas"] != f"{CANVAS_W}x{CANVAS_H}":
        f.add("error", "canvas",
              f"캔버스가 {data['canvas']} 다. 고정 캔버스는 {CANVAS_W}x{CANVAS_H} 여야 한다.")

    for o in data.get("overflow", []):
        f.add("error", "overflow",
              f"{o['slide']}장{(' ' + o['title']) if o['title'] else ''}: 내용이 {o['px']}px 넘친다. "
              f"overflow:hidden 이라 조용히 잘린다.")

    seen = set()
    for sm in data.get("small", []):
        key = (sm["slide"], sm["sel"])
        if key in seen:
            continue
        seen.add(key)
        f.add("error", "font-floor",
              f"{sm['slide']}장 '{sm['sel']}' 이 {sm['px']:.0f}px. "
              f"하한 {FONT_FLOOR_PX:g}px 미만이라 뒷줄에서 안 읽힌다.")

    if not data.get("overflow") and not data.get("small"):
        f.add("info", "render", f"렌더 검사 통과 — {data.get('slides')}장, 캔버스 {data.get('canvas')}")
    return data


# ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="발표 덱 HTML 검사")
    ap.add_argument("deck", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-render", action="store_true", help="렌더 검사를 건너뛴다")
    args = ap.parse_args()

    if not args.deck.exists():
        print(f"파일이 없다: {args.deck}", file=sys.stderr)
        return 2

    src = args.deck.read_text(encoding="utf-8")
    f = Findings()

    check_print_isolation(src, f)
    check_print_setup(src, f)
    check_fixed_font_sizes(src, f)
    check_dead_css(src, f)
    check_asset_paths(src, args.deck, f)
    check_badge_semantics(src, f)
    check_legend_consistency(src, f)
    check_page_numbers(src, f)
    if not args.no_render:
        run_dynamic(args.deck, f)

    if args.json:
        print(json.dumps({"deck": str(args.deck), "findings": f.items}, ensure_ascii=False, indent=2))
        return 1 if f.errors else 0

    icon = {"error": "✗", "warn": "!", "info": "·"}
    if not f.items:
        print(f"✓ {args.deck.name} — 지적 사항 없음")
        return 0
    for level in ("error", "warn", "info"):
        rows = [i for i in f.items if i["level"] == level]
        for i in rows:
            print(f"{icon[level]} [{i['check']}] {i['message']}")
            if i["where"]:
                print(f"    → {i['where']}")
    print(f"\n오류 {len(f.errors)} · 경고 {len(f.warnings)}")
    return 1 if f.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
