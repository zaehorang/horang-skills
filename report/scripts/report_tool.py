#!/usr/bin/env python3
"""페이지 고정형 HTML 보고서를 검사하고 PDF로 렌더링한다.

사용법:
  python3 report_tool.py check  REPORT.html [--breaks]   # 넘침·짧은 꼬리 줄 검사, --breaks면 모든 줄바꿈 지점 출력
  python3 report_tool.py render REPORT.html [--pdf OUT.pdf] [--png DIR] [--dpi 60]

check 종료 코드: 0 = 넘침·꼬리 줄 없음, 1 = 문제 있음, 2 = 실행 실패.
보고서는 각 쪽이 <section class="page"> 이고, 하단 바닥글이 .foot 인 구조를 전제한다.
외부 패키지 없이 Chrome/Chromium 헤드리스와 (PNG 미리보기에만) poppler의 pdftoppm을 쓴다.
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    os.environ.get("REPORT_BROWSER", ""),   # 다른 경로의 브라우저를 쓰려면 이 환경 변수로 지정
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]

# 브라우저 안에서 측정한다. 1쪽 폭 210mm = 794px(96dpi) 창에서 실행한다.
PROBE_JS = r"""
window.addEventListener("load", () => {
  const MM = 25.4 / 96;
  const pages = [...document.querySelectorAll("section.page")];
  const pageOf = el => pages.findIndex(p => p.contains(el)) + 1;

  // 1) 넘침: 바닥글 윗선보다 아래로 내려간 요소가 있는가
  const overflow = pages.map((s, i) => {
    const top = s.getBoundingClientRect().top;
    const foot = s.querySelector(".foot");
    const limit = foot ? foot.getBoundingClientRect().top - top : s.clientHeight;
    let maxB = 0;
    s.querySelectorAll("*").forEach(e => {
      if (e.closest(".foot")) return;
      const b = e.getBoundingClientRect().bottom - top;
      if (b > maxB) maxB = b;
    });
    return {page: i + 1, used_mm: Math.round(maxB * MM), limit_mm: Math.round(limit * MM), over: maxB > limit - 4};
  });

  // 텍스트 블록 안에서 글자별 줄 위치를 구한다
  const SEL = "p, li, td, figcaption, h1, h2, .lede, .msg div, .stat .sub, .note p";
  const blocks = [...document.querySelectorAll(SEL)].filter(el =>
    !el.closest(".foot") && !el.closest("pre") && !el.querySelector(SEL));
  const orphans = [], breaks = [];
  blocks.forEach(el => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const chars = []; let n;
    while ((n = walker.nextNode())) {
      for (let i = 0; i < n.length; i++) {
        const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1);
        const rc = r.getClientRects()[0];
        chars.push({c: n.data[i], t: rc && rc.width > 0 ? rc.top : null, l: rc ? rc.left : 0, r: rc ? rc.right : 0});
      }
    }
    let lastTop = null, text = "", cuts = [], lines = [];
    chars.forEach(o => {
      if (o.t !== null) {
        if (lastTop === null || o.t - lastTop > 4) { if (lastTop !== null) cuts.push(text.length); lines.push({l: o.l, r: o.r}); }
        else { const L = lines[lines.length - 1]; L.l = Math.min(L.l, o.l); L.r = Math.max(L.r, o.r); }
        lastTop = o.t;
      }
      text += o.c;
    });
    if (!cuts.length) return;
    const pg = pageOf(el);
    cuts.forEach(b => {
      const L = text.slice(0, b).replace(/\s+/g, " ").trimEnd();
      const R = text.slice(b).replace(/\s+/g, " ").trimStart();
      breaks.push({page: pg, left: L.slice(-16), right: R.slice(0, 16)});
    });
    // 2) 짧은 꼬리 줄: 마지막 줄이 칸 폭의 18% 또는 글자 4.5개 폭보다 짧다. <br>로 일부러 나눈 블록은 제외
    if (el.querySelector("br")) return;
    const cs = getComputedStyle(el), box = el.getBoundingClientRect();
    const inner = box.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const last = lines[lines.length - 1], lw = last.r - last.l;
    if (lw < Math.max(inner * 0.18, parseFloat(cs.fontSize) * 4.5)) {
      orphans.push({page: pg, lines: lines.length, tail: text.replace(/\s+/g, " ").trim().slice(-40)});
    }
  });
  document.body.setAttribute("data-report-probe", JSON.stringify({pages: pages.length, overflow, orphans, breaks}));
});
"""


def chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    sys.exit("Chrome/Chromium을 찾지 못했다. 설치하거나 REPORT_BROWSER 환경 변수에 실행 파일 경로를 지정한다.")


def probe(report: str) -> dict:
    src = open(report, encoding="utf-8").read()
    if "</body>" not in src:
        sys.exit("</body>가 없는 HTML은 검사할 수 없다.")
    d = os.path.dirname(os.path.abspath(report))
    # 상대 경로 그림이 그대로 열리도록 같은 폴더에 임시 사본을 만든다
    fd, tmp = tempfile.mkstemp(prefix=".report_probe_", suffix=".html", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(src.replace("</body>", "<script>" + PROBE_JS + "</script></body>"))
        out = subprocess.run(
            [chrome(), "--headless=new", "--disable-gpu", "--virtual-time-budget=8000",
             "--window-size=794,1123", "--dump-dom", "file://" + tmp],
            capture_output=True, text=True, timeout=180).stdout
    finally:
        os.remove(tmp)
    m = re.search(r'data-report-probe="([^"]*)"', out)
    if not m:
        print("측정 결과를 받지 못했다(렌더 실패).", file=sys.stderr)
        sys.exit(2)
    return json.loads(html.unescape(m.group(1)))


def cmd_check(a) -> int:
    r = probe(a.report)
    print(f"쪽 수: {r['pages']}")
    over = [o for o in r["overflow"] if o["over"]]
    print("\n[넘침] 바닥글 위 사용 높이 / 한도")
    for o in r["overflow"]:
        print(f"  {o['page']:>2}쪽  {o['used_mm']:>3} / {o['limit_mm']} mm" + ("   <-- 넘침" if o["over"] else ""))
    print(f"\n[짧은 꼬리 줄] {len(r['orphans'])}건")
    for o in r["orphans"]:
        print(f"  {o['page']:>2}쪽  ({o['lines']}줄) …{o['tail']}")
    if a.breaks:
        print(f"\n[줄바꿈 지점] {len(r['breaks'])}곳. 단어 묶음이 갈라진 곳은 <span class=\"nw\">로 묶는다")
        for b in r["breaks"]:
            print(f"  {b['page']:>2}쪽  …{b['left']} ⏎ {b['right']}…")
    ok = not over and not r["orphans"]
    print("\n결과:", "통과" if ok else "수정 필요")
    return 0 if ok else 1


def cmd_render(a) -> int:
    report = os.path.abspath(a.report)
    pdf = os.path.abspath(a.pdf or os.path.splitext(report)[0] + ".pdf")
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", "file://" + report],
                   capture_output=True, timeout=180)
    if not os.path.exists(pdf):
        print("PDF 생성 실패", file=sys.stderr)
        return 2
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout if shutil.which("pdfinfo") else ""
    pages = re.search(r"Pages:\s+(\d+)", info)
    print(f"PDF: {pdf}" + (f"  ({pages.group(1)}쪽)" if pages else ""))
    if a.png:
        if not shutil.which("pdftoppm"):
            print("pdftoppm이 없어 PNG 미리보기를 건너뛴다(brew install poppler).", file=sys.stderr)
        else:
            os.makedirs(a.png, exist_ok=True)
            subprocess.run(["pdftoppm", "-r", str(a.dpi), "-png", pdf, os.path.join(a.png, "page")], check=True)
            print(f"PNG: {a.png}/page-*.png")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("report"); c.add_argument("--breaks", action="store_true")
    r = sub.add_parser("render"); r.add_argument("report"); r.add_argument("--pdf"); r.add_argument("--png"); r.add_argument("--dpi", type=int, default=60)
    a = ap.parse_args()
    return cmd_check(a) if a.cmd == "check" else cmd_render(a)


if __name__ == "__main__":
    sys.exit(main())
