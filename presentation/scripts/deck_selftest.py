#!/usr/bin/env python3
"""deck_verify.py 가 실제로 잡아야 할 것을 잡는지 검증한다.

fixture 를 파일로 커밋하지 않고 template.html 에 **변형을 가해 생성**한다.
템플릿이 바뀌어도 fixture 가 낡지 않게 하기 위해서다.

각 케이스는 두 가지를 함께 본다.
  1. 기대한 검사가 걸리는가        (미탐 방지)
  2. 기대하지 않은 오류가 없는가   (오탐 방지)

2번이 특히 중요하다. 오탐을 고치다가 진짜 탐지를 죽이는 일이 실제로 있었다.

사용:
    python3 <skill-dir>/scripts/deck_selftest.py            # 전체
    python3 <skill-dir>/scripts/deck_selftest.py --fast     # 렌더 케이스 제외 (크롬 미사용)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from decimal import Decimal
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "assets/starter/presentation.html"
ASSETS = ROOT / "assets/starter/assets"

# deck_verify 를 모듈로 불러 검사 함수를 직접 호출한다.
spec = importlib.util.spec_from_file_location("deck_verify", ROOT / "scripts/deck_verify.py")
dv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dv)


@dataclass
class Case:
    name: str
    why: str
    expect: set[str] = field(default_factory=set)   # 걸려야 하는 검사 코드
    edits: list[tuple[str, str]] = field(default_factory=list)
    absent: set[str] = field(default_factory=set)
    render: bool = False                            # 크롬 렌더가 필요한가

    def build(self, src: str) -> str:
        for old, new in self.edits:
            if src.count(old) < 1:
                raise AssertionError(f"[{self.name}] 변형 지점을 찾지 못했다: {old[:60]!r}")
            src = src.replace(old, new, 1)
        return src


RESPONSIVE_BLOCK = """    @media (max-width:900px){ .split{grid-template-columns:1fr} }
    @media print{"""

CASES = [
    Case("asset-path/comments", "주석 속 경로는 참조가 아니다",
         absent={"asset-path"},
         edits=[("</style>", '/* url("assets/MISSING.png") */</style>'),
                ("</head>", '<!-- <img src="assets/MISSING_TOO.png"> --></head>')]),
    Case("dead-css/template", "스타터 미사용 클래스는 정보로만 묶는다",
         expect={"template-css"}, absent={"dead-css"},
         edits=[('class="cover-visual-wrap"', 'class="removed-wrap"')]),
    Case("foot-position", "푸터가 캔버스 중간에 뜨면 경고한다",
         expect={"foot-position"},
         edits=[("</style>", '.slide .foot{grid-area:auto;position:absolute;top:300px;bottom:auto;left:54px;right:54px}</style>')],
         render=True),
    Case("empty-content/centered", "가운데 정렬 본문의 위·아래 여유를 합산한다",
         expect={"empty-content"},
         edits=[("</style>", '.slide .content{display:flex!important;align-items:center;justify-content:center}.slide .content>*{display:none!important}.slide .content::before{content:none}</style>'),
                ('</style>', '.slide .content>p.test-visible{display:block!important}</style>'),
                ('<div class="content">', '<div class="content"><p class="test-visible">짧은 본문</p>')],
         render=True),
    Case("empty-content/card", "글자가 짧아도 큰 카드 박스는 내용에 포함한다",
         edits=[("</style>", '.slide .content{display:flex!important;align-items:center;justify-content:center}.slide .content>*{display:none!important}.slide .content>article.test-card{display:block!important;height:80%;width:100%;background:var(--card)}</style>'),
                ('<div class="content">', '<div class="content"><article class="test-card">짧은 본문</article>')],
         render=True),
    Case("asset-path/body-glob", "본문의 assets/*부터 다음 CSS 주석까지 지우지 않는다",
         expect={"asset-path"},
         edits=[('<div class="content">', '<div class="content"><p>assets/*</p><img src="assets/MISSING.png"><style>/* comment */</style>')]),
    Case("legend/style-attributes", "속성이 있는 style 태그도 안전하게 제외한다",
         expect={"legend"},
         edits=[('<style>', '<style type="text/css">'),
                ('<div class="content">', '<div class="content"><div class="legend"><span class="badge plan">제안</span></div>'),
                ('class="service proposed"', 'class="service confirmed"'),
                ('class="service proposed"', 'class="service confirmed"')]),
    Case("render-baseline", "정상 템플릿 푸터에는 경고하지 않는다",
         absent={"foot-position"}, render=True),
    Case("ok", "손대지 않은 템플릿은 오류가 없어야 한다"),

    Case("print-isolation",
         "반응형 @media 에 screen 한정이 없으면 인쇄에서 레이아웃이 무너진다",
         expect={"print-isolation"},
         edits=[("    @media print{", RESPONSIVE_BLOCK)]),

    Case("print-setup/page",
         "@page 가 없으면 PDF가 A4 세로로 축소·분할된다",
         expect={"print-setup"},
         edits=[("@page{size:1280px 720px;margin:0}", "")]),

    Case("print-setup/color",
         "print-color-adjust 가 없으면 배경·보더 색이 인쇄에서 빠진다",
         expect={"print-setup"},
         edits=[("*{-webkit-print-color-adjust:exact;print-color-adjust:exact}", "*{}")]),

    Case("print-setup/transform",
         "인쇄에서 인라인 scale 을 해제하지 않으면 페이지가 한쪽에 몰린다",
         expect={"print-setup"},
         edits=[(".deck{width:auto;height:auto;transform:none!important}",
                 ".deck{width:auto;height:auto}")]),

    Case("print-setup/no-js-scale",
         "JS 스케일을 쓰지 않는 단일 페이지에는 transform 해제를 요구하지 않는다",
         edits=[(".deck{width:auto;height:auto;transform:none!important}",
                 ".deck{width:auto;height:auto}"),
                ("deck.style.transform=", "void 0; //")]),

    Case("font-floor",
         "슬라이드 높이의 2% 미만 글자는 뒷줄에서 안 읽힌다",
         expect={"font-floor"},
         edits=[("    .foot{display:flex;", "    .tiny-label{font-size:11px}\n    .foot{display:flex;")]),

    Case("asset-path/missing",
         "없는 파일을 참조하면 빈 칸이 나간다",
         expect={"asset-path"},
         edits=[('<div class="content', '<img src="assets/NOPE.png"><div class="content')]),

    Case("asset-path/outside",
         "덱 폴더 밖을 참조하면 폴더만 옮길 때 깨진다",
         expect={"asset-path"},
         edits=[("assets/PHOTO.png", "../elsewhere/PHOTO.png")]),

    Case("badge-semantics",
         "같은 배지가 두 의미로 쓰이면 범례를 신뢰할 수 없다",
         expect={"badge-semantics"},
         edits=[('<span class="badge plan">제안</span>',
                 '<span class="badge plan">제안</span><span class="badge plan">2단계</span>')]),

    Case("page-numbers",
         "번호를 하드코딩하면 슬라이드를 옮길 때 어긋난다",
         expect={"page-numbers"},
         edits=[('<span class="page"></span>', "<span>01 / 99</span>")]),

    Case("dead-css",
         "죽은 셀렉터는 색 별칭이 이중으로 싸우는 사고의 전조다",
         expect={"dead-css"},
         edits=[("    .foot{display:flex;", "    .zzz-never-used{color:red}\n    .foot{display:flex;")]),

    Case("palette",
         "패턴 CSS에 색을 직접 쓰면 테마를 바꿔도 그 자리만 옛 색으로 남는다",
         expect={"palette"},
         edits=[("    .foot{display:flex;", "    .stray-color{color:#2F6FB0}\n    .foot{display:flex;")]),

    Case("palette/theme-block",
         "테마 블록과 인라인 --c 지정은 팔레트 경고 대상이 아니다",
         absent={"palette"},
         edits=[("    *{box-sizing:border-box}", '    [data-theme="forest"]{--accent:#3F7A4A}\n    *{box-sizing:border-box}'),
                ('<div class="dg-lane tone-b">', '<div class="dg-lane tone-b" style="--c:#2F6FB0">')]),

    Case("dg-edge",
         "선이 없는 노드를 가리키면 그려지지 않고 조용히 빠진다",
         expect={"dg-edge"},
         edits=[('data-from="o-run" data-to="o-out"', 'data-from="o-run" data-to="o-nope"')]),

    Case("dg-overlap",
         "두 노드를 같은 칸에 두면 겹쳐서 읽히지 않는다",
         expect={"dg-overlap"},
         edits=[('id="o-run" style="--x:4;--y:1"', 'id="o-run" style="--x:3;--y:1"')],
         render=True),

    Case("dg-numbers",
         "그림 번호와 범례 번호가 어긋나면 순서대로 짚을 수 없다",
         expect={"dg-numbers"},
         edits=[('<li><span class="dg-num">3</span>', '<li><span class="dg-num">4</span>')],
         render=True),

    Case("code-overflow",
         "pre 는 줄을 접지 않아 긴 줄이 상자 오른쪽에서 조용히 잘린다",
         expect={"code-overflow"},
         edits=[('result = run(state[<span class="s">"input"</span>])',
                 'result = run(state[<span class="s">"input"</span>], ' + "option_value, " * 12 + ')')],
         render=True),

    Case("code-budget",
         "코드가 12줄을 넘으면 설명할 줄이 묻힌다",
         expect={"code-budget"},
         edits=[('<span class="k">def</span> handle(state):', '<span class="k">def</span> handle(state):' + "\n    pass" * 9),
                ('<div class="code-out">', '<div class="code-out" style="display:none">')],
         render=True),

    Case("dg-numbers/code",
         "코드 강조 번호와 결과 칸 번호가 어긋나면 어느 줄 얘기인지 놓친다",
         expect={"dg-numbers"},
         edits=[('<div><span class="dg-num">2</span><div><strong>', '<div><span class="dg-num">3</span><div><strong>')],
         render=True),

    Case("guide",
         "갤러리 견본의 안내를 복사해 온 채로 두면 발표 화면에 '견본' 표시가 나간다",
         expect={"guide"},
         edits=[('<footer class="foot"><span>보조 메시지</span>', '<footer class="foot"><span class="guide">패턴 B · 요령</span>')]),

    Case("paper-white",
         "흰 바탕 옵션을 어느 테마에 겹쳐도 레이아웃·대비 검사가 깨지지 않는다",
         edits=[('<html lang="ko">', '<html lang="ko" data-theme="ocean" data-paper="white">')],
         render=True),

    Case("canvas",
         "고정 캔버스가 1280x720 에서 벗어나면 PDF 규격이 깨진다",
         expect={"canvas"},
         edits=[("--canvas-h: 720px", "--canvas-h: 800px")],
         render=True),

    Case("overflow",
         "내용이 넘치면 overflow:hidden 이라 조용히 잘린다",
         expect={"overflow"},
         edits=[('<div class="mcell"><span class="no">P1</span><strong>이름</strong><p>한 구절</p></div>',
                 '<div class="mcell"><span class="no">P1</span><strong>이름</strong>'
                 + "<p>넘치게 만들기 위한 긴 문장입니다.</p>" * 14 + "</div>")],
         render=True),
]


def run_case(case: Case, src: str, workdir: Path, use_render: bool) -> tuple[bool, str]:
    deck = workdir / f"{case.name.replace('/', '_')}.html"
    deck.write_text(case.build(src), encoding="utf-8")

    f = dv.Findings()
    text = deck.read_text(encoding="utf-8")
    dv.check_print_isolation(text, f)
    dv.check_print_setup(text, f)
    dv.check_fixed_font_sizes(text, f)
    dv.check_dead_css(text, f)
    dv.check_asset_paths(text, deck, f)
    dv.check_badge_semantics(text, f)
    dv.check_legend_consistency(text, f)
    dv.check_page_numbers(text, f)
    dv.check_palette(text, f)
    dv.check_diagram_edges(text, f)
    dv.check_guide_notes(text, deck, f)
    if case.render and use_render:
        render_data = dv.run_dynamic(deck, f)

    if case.name == "empty-content/centered" and use_render:
        first = next((item for item in (render_data or {}).get("empty", []) if item["slide"] == 1), None)
        assert first and first["above"] > 0 and first["below"] > 0, render_data
    if case.name == "empty-content/card" and use_render:
        assert render_data and not any(item["slide"] == 1 for item in render_data.get("empty", [])), render_data

    if case.name == "foot-position" and use_render:
        assert not any("렌더 검사 통과" in i["message"] for i in f.items), f.items

    fired = {i["check"] for i in f.items if i["level"] in ("error", "warn", "info")}
    errors = {i["check"] for i in f.items if i["level"] == "error"}

    expected_levels = {"template-css": "info", "empty-content": "info", "foot-position": "warn", "dead-css": "warn",
                       "palette": "warn", "dg-edge": "error", "dg-overlap": "error", "dg-numbers": "error",
                       "code-overflow": "error", "code-budget": "warn", "guide": "warn"}
    for item in f.items:
        if item["check"] in expected_levels and item["level"] != expected_levels[item["check"]]:
            return False, f"검사 심각도가 다르다: {item}"
    forbidden = case.absent & fired
    if forbidden:
        return False, f"나오면 안 되는 검사: {sorted(forbidden)}"
    if case.render and use_render and ("render" in {i["check"] for i in f.warnings}):
        return False, "렌더 검사를 실행하지 못했다"
    missing = case.expect - fired
    if missing:
        return False, f"기대한 검사가 걸리지 않았다: {', '.join(sorted(missing))}"

    # 오탐 검사: 기대하지 않은 '오류'가 있으면 실패로 본다 (경고·정보는 허용)
    unexpected = errors - case.expect
    if unexpected:
        detail = "; ".join(i["message"] for i in f.items
                           if i["level"] == "error" and i["check"] in unexpected)
        return False, f"기대하지 않은 오류: {', '.join(sorted(unexpected))} — {detail[:160]}"

    if case.name == "ok" and errors:
        return False, f"손대지 않은 템플릿에서 오류: {', '.join(sorted(errors))}"

    return True, ""


def test_numbers(workdir: Path) -> None:
    spec = importlib.util.spec_from_file_location("deck_numbers", ROOT / "scripts/deck_numbers.py")
    dn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dn)
    j = workdir / "results.json"
    c = workdir / "data.csv"
    j.write_text(json.dumps({"rate": 0.292, "nested": [0.804, -0.594], "flag": True}), encoding="utf-8")
    c.write_text("value,label\n120,other\n1.25,unused\n", encoding="utf-8")
    values = dn.load_evidence([j, c])
    assert Decimal("120") in values and Decimal("1") not in values
    src = """<style>.x{top:999px}</style><!-- 888 -->
    <section class="slide"><p>0.29 80.4% −0.59 120 1,200</p>
    <script>777</script><span hidden>666</span><span style="display:none">555</span>
    <span class="page">01 / 02</span><p>2026년 오후 3시 05:30 40초 9쪽</p></section>
    <section class="slide"><p>0.31 1.25</p></section>"""
    rows = dn.audit(src, values, ignore_pages=True, ignore_years=True, ignore_times=True)
    assert rows[0]["unsupported"] == ["1,200"], rows
    assert rows[1]["unsupported"] == ["0.31"], rows
    raw = dn.audit(src, values)
    assert "2026" in raw[0]["unsupported"] and "9" in raw[0]["unsupported"], raw
    assert dn.audit(src, values, ignore_pages=True, ignore_years=True, ignore_times=True,
                    ignore_regex=r"1,200")[0]["unsupported"] == []
    assert dn.supported("29%", {Decimal("0.292")})
    assert dn.audit('<section class="slide">확률0.29·회의999회</section>', values)[0]["unsupported"] == ["999"]
    assert not dn.supported("0", {Decimal("0.292")})
    assert dn.supported("0.63", {Decimal("0.625")})
    assert not dn.supported("0.30", {Decimal("0.292")})

    def numbers(text, **options):
        return dn.audit('<section class="slide">' + text + '</section>', set(), **options)[0]['numbers']

    assert numbers('<p>AUC는 0.999.</p><p>총 777.</p>') == ['0.999', '777']
    assert numbers('Sprint-1 COVID-19 GPT-4 -2 −3 +5 A-6.25') == ['1', '19', '4', '-2', '−3', '+5', '6.25']
    assert numbers('0.29 / 0.63 10 / 15', ignore_pages=True) == ['0.29', '0.63', '10', '15']
    assert numbers('<footer class="foot"><span>02 / 07</span><span>0.29 / 0.63</span></footer>',
                   ignore_pages=True) == ['0.29', '0.63']
    assert numbers('2·3·4쪽 2, 3쪽 2~4쪽 2-4쪽 6장 7페이지', ignore_pages=True) == []
    assert numbers('3시스템 7분석 8시간표 9초기 오후 3시 7분 40초 1.5시간 05:30',
                   ignore_times=True) == ['3', '7', '8', '9']
    assert numbers('2024년도 2025년 2026 2023년대', ignore_years=True) == ['2023']


def test_gallery_sync() -> None:
    """갤러리 견본(presentation.html·palette.html)의 CSS·엔진이 스타터와 같아야 한다.

    색 토큰·테마를 스타터에서만 고치고 갤러리에 안 옮기면 견본과 실제 덱의 색이 어긋난다.
    """
    gal = ROOT / "examples/gallery"
    if not gal.exists():
        return
    src = TEMPLATE.read_text(encoding="utf-8")
    cut = lambda s: s[: s.index('<main class="deck"')]
    start_tail = lambda s: s[s.index("  </main>"):]
    head = cut(src).replace("<title>발표 제목</title>", "")
    for name in ("presentation.html", "palette.html"):
        other = (gal / name).read_text(encoding="utf-8")
        h = cut(other)
        h = h[: h.index("<title>")] + h[h.index("</title>") + len("</title>"):]
        if "팔레트 장 전용" in h:
            h = h[: h.index("  <style>\n    /* 팔레트 장 전용")] + h[h.index("</head>"):]
        assert h == head, f"{name} 의 <head> 가 스타터와 다르다 — 스타터 CSS 를 갤러리에 다시 옮길 것"
        tail = start_tail(other)
        if name == "palette.html":   # 팔레트 전용 스크립트 한 덩어리만 더 붙어 있다
            i = tail.index("  <script>\n    /* 이 장은 ?theme=")
            tail = tail[:i] + tail[tail.index("</body>", i):]
        assert tail == start_tail(src), f"{name} 의 엔진 스크립트가 스타터와 다르다 — ?theme·?paper 같은 엔진 수정이 빠진다"


def main() -> int:
    ap = argparse.ArgumentParser(description="deck_verify 자체 테스트")
    ap.add_argument("--fast", action="store_true", help="렌더 케이스를 건너뛴다 (크롬 미사용)")
    args = ap.parse_args()

    if not TEMPLATE.exists():
        print(f"템플릿이 없다: {TEMPLATE}", file=sys.stderr)
        return 2

    src = TEMPLATE.read_text(encoding="utf-8")
    passed = failed = skipped = 0

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        if ASSETS.exists():
            shutil.copytree(ASSETS, workdir / "assets")

        try:
            test_gallery_sync()
            print("  ✓  gallery-sync             갤러리 견본의 CSS·엔진이 스타터와 같다")
            passed += 1
        except AssertionError as exc:
            print(f"  ✗  gallery-sync             {exc}")
            failed += 1

        try:
            test_numbers(workdir)
            print("  ✓  numbers                  추출·복수 근거·반올림·백분율·제외 옵션")
            passed += 1
        except (AssertionError, ValueError) as exc:
            print(f"  ✗  numbers                  {exc}")
            failed += 1

        for case in CASES:
            if case.render and args.fast:
                print(f"  −  {case.name:24s} (렌더 케이스, --fast 로 건너뜀)")
                skipped += 1
                continue
            try:
                ok, msg = run_case(case, src, workdir, use_render=not args.fast)
            except AssertionError as exc:
                ok, msg = False, str(exc)
            if ok:
                print(f"  ✓  {case.name:24s} {case.why}")
                passed += 1
            else:
                print(f"  ✗  {case.name:24s} {msg}")
                failed += 1

    print(f"\n통과 {passed} · 실패 {failed}" + (f" · 건너뜀 {skipped}" if skipped else ""))
    if failed:
        print("\n실패는 둘 중 하나를 뜻한다:\n"
              "  · 검사가 약해졌다 (미탐) — deck_verify.py 의 해당 검사를 확인할 것\n"
              "  · 템플릿이 바뀌어 변형 지점이 사라졌다 — CASES 의 edits 를 갱신할 것")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
