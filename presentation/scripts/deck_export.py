#!/usr/bin/env python3
"""발표 덱 HTML을 16:9 PDF로 내보낸다.

사용:
    python3 <skill-dir>/scripts/deck_export.py <deck.html> [-o out.pdf]

덱의 @media print 는 다음을 갖춰야 한다 (deck_verify.py 가 검사한다):
    @page{size:1280px 720px;margin:0}     용지를 슬라이드 규격으로 고정
    print-color-adjust:exact              배경·보더 색을 실제로 인쇄
    .deck{transform:none!important}       JS가 넣은 인라인 scale 해제

출력은 960x540pt = 13.333x7.5in 이어야 하며, 아니면 오류로 끝난다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CANVAS_W, CANVAS_H = 1280, 720
EXPECT_PT = (960.0, 540.0)

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    return None


def inspect(pdf: Path) -> tuple[int, tuple[float, float] | None]:
    data = pdf.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    boxes = set(re.findall(rb"/MediaBox\s*\[([^\]]+)\]", data))
    size = None
    if boxes:
        v = [float(x) for x in list(boxes)[0].split()]
        size = (v[2], v[3])
    return pages, size


def main() -> int:
    ap = argparse.ArgumentParser(description="덱 HTML → 16:9 PDF")
    ap.add_argument("deck", type=Path)
    ap.add_argument("-o", "--out", type=Path, help="출력 경로 (기본: <deck>.pdf)")
    args = ap.parse_args()

    if not args.deck.exists():
        print(f"파일이 없다: {args.deck}", file=sys.stderr)
        return 2

    chrome = find_chrome()
    if not chrome:
        print("크롬을 찾지 못했다. Google Chrome 이 필요하다.", file=sys.stderr)
        return 2

    out = args.out or args.deck.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    # 크롬이 PDF를 다 쓰고도 종료하지 않는 경우가 있다. 파일이 안정될 때까지
    # 기다렸다가 직접 끝낸다. subprocess.run 으로 기다리면 그대로 멈춘다.
    if out.exists():
        out.unlink()
    tmp = tempfile.mkdtemp()
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         f"--user-data-dir={tmp}",
         "--no-pdf-header-footer",
         f"--window-size={CANVAS_W},{CANVAS_H}",
         "--virtual-time-budget=15000",
         f"--print-to-pdf={out.resolve()}",
         args.deck.resolve().as_uri()],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline, last, stable = time.time() + 120, -1, 0
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            if out.exists():
                size = out.stat().st_size
                stable = stable + 1 if size == last and size > 0 else 0
                last = size
                if stable >= 3:          # 3회 연속 같은 크기면 다 썼다고 본다
                    break
            time.sleep(0.4)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    if not out.exists() or out.stat().st_size == 0:
        print("PDF 생성 실패 — 덱이 로드되지 않았을 수 있다.", file=sys.stderr)
        return 1

    pages, size = inspect(out)
    print(f"{out}  —  {pages}페이지  {out.stat().st_size/1_000_000:.1f}MB")

    if size:
        w, h = size
        print(f"용지: {w:.0f}x{h:.0f}pt = {w/72:.2f}x{h/72:.2f}in  (비율 {w/h:.3f})")
        if (round(w), round(h)) != (round(EXPECT_PT[0]), round(EXPECT_PT[1])):
            print(
                f"\n✗ 용지가 {EXPECT_PT[0]:.0f}x{EXPECT_PT[1]:.0f}pt 가 아니다.\n"
                "  @media print 안에 @page{size:1280px 720px;margin:0} 이 있는지 확인할 것.\n"
                "  (presentation 스킬의 deck_verify.py로 진단 가능)",
                file=sys.stderr)
            return 1

    print("✓ 규격 확인됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
