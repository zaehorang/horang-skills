#!/usr/bin/env python3
"""발표 덱 HTML을 기계적으로 검사한다.

여기 있는 검사 항목은 대부분 실제로 한 번씩 터졌던 것들이다. 재현 경위는
references/failure-catalog.md 참고. 구조도(dg-*)와 팔레트(palette) 검사는
선·번호·색이 화면과 어긋나지 않게 하는 구조 검사다.

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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANVAS_W, CANVAS_H = 1280, 720
FONT_FLOOR_RATIO = 0.02          # 슬라이드 높이의 2.0%
# 기본 하단 패딩(약 5%)보다 넉넉한 10%: 중간 행으로 밀린 푸터를 탐지한다.
FOOT_GAP_RATIO = 0.10
# 본문 높이의 35%: 가운데 정렬로 위·아래에 나뉜 여유도 합산한다.
# 예시의 절반가량 빈 본문을 잡되 통상적인 간격·패딩은 허용하며, 의도적 여백은 정보로 남긴다.
EMPTY_CONTENT_RATIO = 0.35
FONT_FLOOR_PX = CANVAS_H * FONT_FLOOR_RATIO   # 14.4px
# 구조도 하나에 노드 9개까지. 그 이상이면 장을 나누거나 단계별로 쌓는다 (layout-budget.md).
DG_NODE_BUDGET = 9
# 코드 블록 하나에 12줄까지. 설명할 줄만 남긴다 (패턴 S).
CODE_LINE_BUDGET = 12
# 글자와 배경 대비 하한 (WCAG AA). 프로젝터는 대비를 크게 깎으므로 이 아래는 뒷줄에서 안 읽힌다.
# 보통 글자는 4.5:1, 큰 글자(24px 이상 또는 굵은 19px 이상)는 3:1.
CONTRAST_FLOOR = 4.5
CONTRAST_FLOOR_LARGE = 3.0
# 레터박스 검정·흰색은 팔레트가 아니라 무대 색이라 허용한다.
PALETTE_NEUTRALS = {"#000", "#000000", "#fff", "#ffffff"}

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


def strip_comments(src: str) -> str:
    """실제 참조가 아닌 HTML·CSS 주석을 검사에서 제외한다."""
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    return re.sub(r"<(style|script)\b[^>]*>.*?</\1>",
                  lambda m: re.sub(r"/\*.*?\*/", "", m.group(), flags=re.S),
                  src, flags=re.S | re.I)


def css_classes(src: str) -> set[str]:
    css = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", strip_comments(src), re.S | re.I))
    # 선언 값(파일 확장자·소수 등)이 아닌 규칙의 셀렉터에서만 수집한다.
    return {name for selector in re.findall(r"([^{}]+)\{", css)
            for name in re.findall(r"\.([A-Za-z_][\w-]*)", selector)}


def check_dead_css(src: str, f: Findings) -> None:
    """스타터의 재사용 패턴과 사용자가 추가한 미사용 클래스를 구분한다."""
    src = strip_comments(src)
    outside = re.sub(r"<style\b[^>]*>.*?</style>", "", src, flags=re.S | re.I)
    used = set(re.findall(r"[A-Za-z_][\w-]*", outside)) | {"active", "past"}
    dead = css_classes(src) - used
    starter = Path(__file__).resolve().parent.parent / "assets/starter/presentation.html"
    template = css_classes(starter.read_text(encoding="utf-8")) if starter.exists() else set()
    patterns = dead & template
    custom = sorted(dead - template)
    if patterns:
        f.add("info", "template-css", f"템플릿 패턴 미사용 {len(patterns)}개")
    if custom:
        f.add("warn", "dead-css",
              f"쓰이지 않는 셀렉터 {len(custom)}개: {', '.join(custom[:12])}{' …' if len(custom) > 12 else ''}")


def check_asset_paths(src: str, path: Path, f: Findings) -> None:
    """덱 폴더 밖을 가리키면 폴더만 압축해 넘길 때 이미지가 깨진다."""
    src = strip_comments(src)
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
    outside = re.sub(r"<style\b[^>]*>.*?</style>", "", strip_comments(src), flags=re.S | re.I)
    pairs = [("badge plan", "proposed"), ("badge next", "backlog")]
    for badge, state in pairs:
        if badge in src and state not in outside:
            f.add("warn", "legend",
                  f"범례에 '{badge}' 가 있는데 대응하는 '{state}' 상태 카드가 없다. 범례와 카드가 어긋난다.")


def check_palette(src: str, f: Findings) -> None:
    """색 값은 :root 팔레트와 [data-theme] 테마·[data-mode] 모드 블록에만 둔다.

    패턴 CSS에 색을 직접 쓰면 테마를 바꿔도 그 자리만 옛 색으로 남는다.
    """
    css = "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", strip_comments(src), re.S | re.I))
    stray: list[str] = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ":root" in selector or "[data-theme" in selector or "[data-mode" in selector:
            continue
        for hexv in re.findall(r"#[0-9A-Fa-f]{3,8}\b", body):
            if hexv.lower() not in PALETTE_NEUTRALS:
                stray.append(f"{selector.strip().splitlines()[-1].strip()} {hexv}")
    if stray:
        f.add("warn", "palette",
              f"팔레트 밖에 색 값이 {len(stray)}곳 있다: {', '.join(stray[:6])}{' …' if len(stray) > 6 else ''}",
              ":root · [data-theme] · [data-mode] 블록의 토큰으로 옮길 것. 한 요소만 다르면 style=\"--c:…\"")


def check_diagram_edges(src: str, f: Findings) -> None:
    """선이 가리키는 노드 id 가 없으면 엔진이 선을 그리지 못하고 조용히 빠진다."""
    body = strip_comments(src)
    ids = set(re.findall(r'\bid="([^"]+)"', body))
    for m in re.finditer(r'<i\b[^>]*class="dg-edge[^"]*"[^>]*>', body):
        tag = m.group()
        for attr in ("data-from", "data-to"):
            ref = re.search(attr + r'="([^"]*)"', tag)
            if not ref or ref.group(1) not in ids:
                line = body[: m.start()].count("\n") + 1
                f.add("error", "dg-edge",
                      f"구조도 선의 {attr}=\"{ref.group(1) if ref else ''}\" 노드가 없다. 선이 그려지지 않는다.",
                      f"line {line}")


def check_text_accent(src: str, f: Findings) -> None:
    """글자 강조(class="accent")는 한 장에 한 곳. 여러 곳을 칠하면 어디를 봐야 할지 흐려진다."""
    for i, sec in enumerate(re.findall(r'<section class="slide[^"]*".*?</section>', strip_comments(src), re.S), 1):
        n = len(re.findall(r'class="accent"', sec))
        if n > 1:
            f.add("warn", "accent-text", f"{i}장: 글자 강조가 {n}곳이다. 한 장에 한 곳, 짚는 요소와 같은 대상만 칠한다.",
                  "build.md '글자 강조'")


def check_title_style(src: str, f: Findings) -> None:
    """장 제목(h2)은 결론을 명사형으로 끝낸다. "~다·~요·~까" 서술형은 대본처럼 읽힌다.

    표지 제목(h1)은 질문형·문장형을 허용한다.
    """
    bad = []
    for raw in re.findall(r"<h2\b[^>]*>(.*?)</h2>", strip_comments(src), re.S):
        text = re.sub(r"<[^>]+>", "", raw).strip()
        if re.search(r"(다|요|까)[.!?]?$", text):
            bad.append(text)
    if bad:
        f.add("warn", "title-style",
              f"서술형으로 끝나는 장 제목이 {len(bad)}개: {', '.join(bad[:3])}{' …' if len(bad) > 3 else ''}",
              "결론은 두고 명사형으로 끝낼 것 (예: '정답률이 81%로 올랐다' → '정답률 54% → 81% 상승'). build.md '제목 쓰기'")


def check_guide_notes(src: str, path: Path, f: Findings) -> None:
    """갤러리 견본의 안내(.guide)를 복사해 온 채로 두면 발표 화면에 '견본' 표시가 나간다.

    갤러리 덱 자신(examples/gallery)은 안내가 있는 게 정상이라 정보로만 남긴다.
    """
    n = len(re.findall(r'class="[^"]*\bguide\b', strip_comments(src)))
    if not n:
        return
    if path.resolve().parent.name == "gallery":
        f.add("info", "guide", f"견본 안내 {n}곳 (갤러리 덱이라 정상)")
    else:
        f.add("warn", "guide", f"견본 안내(.guide)가 {n}곳 남아 있다. 발표 화면에 '견본' 표시가 나간다.",
              "푸터의 <span class=\"guide\"> 를 실제 보조 메시지로 바꿀 것")


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
  const out = {overflow: [], small: [], foot: [], empty: [], dg: [], contrast: [], canvas: null, slides: 0};
  // 계산된 색 → {rgb, a}. color-mix 결과는 'color(srgb r g b / a)' 꼴이다
  const parseColor = c => { const n = (c.match(/-?[\\d.]+/g) || []).map(Number);
    return c.startsWith('color(') ? {rgb: n.slice(0, 3).map(v => v * 255), a: n.length > 3 ? n[3] : 1}
                                  : {rgb: n.slice(0, 3), a: n.length > 3 ? n[3] : 1}; };
  const lum = rgb => { const [r, g, b] = rgb.map(x => { x /= 255; return x <= .03928 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; });
    return .2126 * r + .7152 * g + .0722 * b; };
  try {
    const d = f.contentDocument;
    const deck = d.querySelector('.deck');
    out.canvas = deck ? deck.offsetWidth + 'x' + deck.offsetHeight : null;
    const slides = [...d.querySelectorAll('.slide')];
    out.slides = slides.length;
    slides.forEach((s, i) => {
      const prev = s.className;
      s.classList.add('active');
      const bounds = s.getBoundingClientRect();
      const foot = s.querySelector('.foot');
      if (foot && foot.getClientRects().length) {
        const gap = (bounds.bottom - foot.getBoundingClientRect().bottom) / bounds.height;
        if (gap >= __FOOT_GAP__) out.foot.push({slide: i + 1, ratio: gap});
      }
      const c = s.querySelector('.content');
      if (c) {
        const ov = Math.round(c.scrollHeight - c.clientHeight);
        // 레이아웃 래퍼 전체 높이 대신 글자·미디어·실제로 칠해진 카드 박스를 잰다.
        const area = c.getBoundingClientRect();
        const visible = el => el.getClientRects().length &&
          getComputedStyle(el).visibility !== 'hidden' &&
          getComputedStyle(el).opacity !== '0' &&
          !el.closest('script,style,template');
        const rects = [];
        for (const el of c.querySelectorAll('*')) {
          if (!visible(el)) continue;
          const style = getComputedStyle(el);
          const painted = (style.backgroundColor !== 'rgba(0, 0, 0, 0)' &&
                           style.backgroundColor !== 'transparent') ||
            style.backgroundImage !== 'none' ||
            ['Top','Right','Bottom','Left'].some(side =>
              parseFloat(style['border' + side + 'Width']) > 0 &&
              !['none','hidden'].includes(style['border' + side + 'Style']));
          if (painted || el.matches('img,svg,canvas,video')) rects.push(el.getBoundingClientRect());
        }
        const walker = d.createTreeWalker(c, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const node = walker.currentNode;
          if (!node.textContent.trim() || !visible(node.parentElement)) continue;
          const range = d.createRange();
          range.selectNodeContents(node);
          rects.push(...range.getClientRects());
        }
        const top = rects.length ? Math.max(area.top, Math.min(...rects.map(r => r.top))) : area.top;
        const bottom = rects.length ? Math.min(area.bottom, Math.max(...rects.map(r => r.bottom))) : area.top;
        const above = Math.max(0, top - area.top) / area.height;
        const below = Math.max(0, area.bottom - bottom) / area.height;
        const gap = above + below;
        if (area.height > 0 && gap >= __EMPTY_CONTENT__)
          out.empty.push({slide: i + 1, ratio: gap, above, below});
        if (ov > 2) out.overflow.push({slide: i + 1, title: s.dataset.title || '', px: ov});
      }
      s.querySelectorAll('*').forEach(el => {
        if (!el.childElementCount && el.textContent.trim()) {
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < FLOOR) out.small.push({slide: i + 1, sel: (el.className || el.tagName) + '', px: fs});
        }
      });
      // 글자 대비: 글자색과 실제로 칠해진 가장 가까운 배경을 비교한다. 그라데이션·그림 위 글자는 배경을 알 수 없어 건너뛴다
      const seenC = new Set();
      s.querySelectorAll('*').forEach(el => {
        if (el.closest('svg,script,style') || !el.getClientRects().length) return;
        if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) return;
        const fg = parseColor(getComputedStyle(el).color); if (fg.a < .5) return;
        let e = el, bg = null;
        while (e) {
          const cs = getComputedStyle(e);
          if (cs.backgroundImage !== 'none') { bg = null; break; }
          const b = parseColor(cs.backgroundColor);
          if (b.a >= .9) { bg = b.rgb; break; }
          if (b.a > .05) { bg = null; break; }
          if (e === s) break;
          e = e.parentElement;
        }
        if (!bg) return;
        const L1 = lum(fg.rgb), L2 = lum(bg), ratio = (Math.max(L1, L2) + .05) / (Math.min(L1, L2) + .05);
        const key = (el.className || el.tagName) + '';
        const cs = getComputedStyle(el), px = parseFloat(cs.fontSize), w = parseInt(cs.fontWeight, 10);
        const floor = (px >= 24 || (px >= 19 && w >= 700)) ? __CONTRAST_LARGE__ : __CONTRAST__;
        if (ratio < floor && !seenC.has(key)) { seenC.add(key);
          out.contrast.push({slide: i + 1, sel: key, ratio: Math.round(ratio * 100) / 100, floor, text: el.textContent.trim().slice(0, 20)}); }
      });
      // 구조도: 노드 겹침 · 선 라벨이 노드를 가림 · 노드 예산 · 번호와 범례 짝
      const hit = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2 &&
                            Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2;
      s.querySelectorAll('.dg').forEach(dg => {
        const nodes = [...dg.querySelectorAll('.dg-node')].filter(n => n.closest('.dg') === dg && n.getClientRects().length);
        const rs = nodes.map(n => n.getBoundingClientRect());
        if (nodes.length > __DG_BUDGET__) out.dg.push({slide: i + 1, kind: 'budget', detail: nodes.length + '개'});
        for (let a = 0; a < rs.length; a++) for (let b = a + 1; b < rs.length; b++)
          if (hit(rs[a], rs[b])) out.dg.push({slide: i + 1, kind: 'overlap',
            detail: nodes[a].textContent.trim() + ' · ' + nodes[b].textContent.trim()});
        dg.querySelectorAll(':scope > .dg-label').forEach(l => {
          const r = l.getBoundingClientRect();
          const k = rs.findIndex(n => hit(n, r));
          if (k >= 0) out.dg.push({slide: i + 1, kind: 'label', detail: l.textContent + ' → ' + nodes[k].textContent.trim()});
        });
      });
      // 코드 블록: 줄 수 예산 · 가로 넘침(pre 는 줄을 접지 않아 오른쪽이 조용히 잘린다)
      s.querySelectorAll('pre.code').forEach(pre => {
        const lines = pre.textContent.replace(/\\n+$/, '').split('\\n').length;
        if (lines > __CODE_BUDGET__) out.dg.push({slide: i + 1, kind: 'code-budget', detail: lines + '줄'});
        const ov = Math.round(pre.scrollWidth - pre.clientWidth);
        if (ov > 2) out.dg.push({slide: i + 1, kind: 'code-overflow', detail: ov + 'px'});
      });
      // 번호 짝: 그림·코드 안 번호 = 범례·결과 칸 번호
      const legend = [...s.querySelectorAll('.dg-legend .dg-num, .code-out .dg-num')].map(n => n.textContent.trim());
      if (legend.length) {
        const marks = [...s.querySelectorAll('.dg .dg-num, .code .dg-num')].map(n => n.textContent.trim());
        const seq = legend.every((n, k) => n === String(k + 1));
        const same = [...marks].sort().join() === [...legend].sort().join();
        if (!seq || !same) out.dg.push({slide: i + 1, kind: 'numbers',
          detail: '그림 [' + marks.join(', ') + '] · 범례 [' + legend.join(', ') + ']'});
      }
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


def _serve(directory: Path, probe_html: str):
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

        def do_GET(self):
            if self.path == "/__deck_probe.html":
                payload = probe_html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                super().do_GET()

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

    probe_html = (
        PROBE_PAGE.replace("__FLOOR__", str(FONT_FLOOR_PX))
                  .replace("__FOOT_GAP__", str(FOOT_GAP_RATIO))
                  .replace("__EMPTY_CONTENT__", str(EMPTY_CONTENT_RATIO))
                  .replace("__DG_BUDGET__", str(DG_NODE_BUDGET))
                  .replace("__CODE_BUDGET__", str(CODE_LINE_BUDGET))
                  .replace("__CONTRAST_LARGE__", str(CONTRAST_FLOOR_LARGE))
                  .replace("__CONTRAST__", str(CONTRAST_FLOOR))
                  .replace("__W__", str(CANVAS_W))
                  .replace("__H__", str(CANVAS_H))
                  .replace("__DECK__", path.name))

    try:
        srv, box = _serve(path.parent, probe_html)
    except OSError as exc:
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
             f"http://127.0.0.1:{port}/__deck_probe.html"],
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

    for item in data.get("foot", []):
        f.add("warn", "foot-position",
              f"{item['slide']}장: 푸터 아래가 캔버스 하단에서 {item['ratio']:.0%} 떨어져 있다 (기준 {FOOT_GAP_RATIO:.0%}).")
    for item in data.get("empty", []):
        f.add("info", "empty-content",
              f"{item['slide']}장: 본문 영역의 {item['ratio']:.0%}가 비어 있다 "
              f"(위 {item['above']:.0%} · 아래 {item['below']:.0%}, 기준 {EMPTY_CONTENT_RATIO:.0%}). 의도한 여백인지 확인할 것.")

    dg_msg = {
        "overlap": ("error", "dg-overlap", "구조도 노드가 겹친다: {d}. --x/--y 칸을 확인할 것."),
        "numbers": ("error", "dg-numbers", "번호 짝이 맞지 않는다: {d}. 그림·코드 번호와 범례·결과 번호가 같아야 하고, 범례는 1부터 차례로."),
        "label": ("warn", "dg-label", "선 라벨이 노드를 가린다: {d}. data-label-at 이나 data-offset 으로 옮길 것."),
        "budget": ("warn", "dg-budget", f"구조도 노드가 {{d}}다 (예산 {DG_NODE_BUDGET}). 장을 나누거나 단계별로 쌓는다."),
        "code-overflow": ("error", "code-overflow", "코드 줄이 상자 오른쪽으로 {d} 넘쳐 잘린다. 줄을 나누거나 줄인다."),
        "code-budget": ("warn", "code-budget", f"코드가 {{d}}이다 (예산 {CODE_LINE_BUDGET}줄). 설명할 줄만 남기고 나머지는 … 로 접는다."),
    }
    for item in data.get("dg", []):
        level, check, msg = dg_msg[item["kind"]]
        f.add(level, check, f"{item['slide']}장: " + msg.format(d=item["detail"]))

    for c in data.get("contrast", []):
        f.add("error", "text-contrast",
              f"{c['slide']}장 '{c['sel']}' 글자 대비가 {c['ratio']}:1 (하한 {c.get('floor', CONTRAST_FLOOR):g}:1) — \"{c['text']}\". "
              f"모드·테마 토큰 상속을 확인할 것.")

    seen = set()
    for sm in data.get("small", []):
        key = (sm["slide"], sm["sel"])
        if key in seen:
            continue
        seen.add(key)
        f.add("error", "font-floor",
              f"{sm['slide']}장 '{sm['sel']}' 이 {sm['px']:.0f}px. "
              f"하한 {FONT_FLOOR_PX:g}px 미만이라 뒷줄에서 안 읽힌다.")

    status = "렌더 검사 완료 — 오류·경고 확인 필요" if f.errors or f.warnings else "렌더 검사 통과"
    f.add("info", "render", f"{status} — {data.get('slides')}장, 캔버스 {data.get('canvas')}")
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
    check_palette(src, f)
    check_diagram_edges(src, f)
    check_guide_notes(src, args.deck, f)
    check_title_style(src, f)
    check_text_accent(src, f)
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
