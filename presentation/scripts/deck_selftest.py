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
         edits=[("assets/COVER.png", "assets/NOPE.png")]),

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
    if case.render and use_render:
        dv.run_dynamic(deck, f)

    fired = {i["check"] for i in f.items if i["level"] in ("error", "warn", "info")}
    errors = {i["check"] for i in f.items if i["level"] == "error"}

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
