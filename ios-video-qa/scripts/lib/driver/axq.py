"""AXe `describe-ui` JSON에서 요소를 찾는 CLI. 엔진 내부(화면 키보드 키 찾기, 실패 시 덤프)용.
판정과 읽기는 judge.py를 쓴다. 질의 규칙은 axtree.py 한 곳에 있다.

    … | axq.py find --label 다음 --type Button --last     → "201 809" (못 찾으면 exit 1, 화면 정보를 못 읽으면 exit 2)

명령
  find    중심 좌표 "x y"        frame  "x y w h"
  label   label                  value  AXValue
  list    조건에 맞는 요소를 한 줄씩    dump  label/id/value가 있는 모든 요소
  screen  "W H"(앱 화면 크기)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axtree  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["find", "frame", "label", "value", "list", "dump", "screen"])
    axtree.add_query_args(p)
    a = p.parse_args()
    try:
        roots = axtree.load(sys.stdin.read())
    except axtree.ReadError as e:
        print(e, file=sys.stderr)
        sys.exit(2)   # 2 = 읽기 실패. 1 = 요소 없음
    flat = axtree.flatten(roots)
    scr = axtree.screen(flat)
    if a.cmd == "screen":
        if not scr:
            sys.exit(2)
        print("%d %d" % (scr[2], scr[3]))
        return
    if a.cmd == "dump":
        for n, _, _ in flat:
            if (n.get("AXLabel") or "").strip() or n.get("AXUniqueId") or n.get("AXValue") not in (None, ""):
                print(axtree.describe(n))
        return
    q = axtree.query_from_ns(a)
    found = axtree.hits(flat, q, scr)
    if a.cmd == "list":
        for n, _, _ in found:
            print(axtree.describe(n))
        sys.exit(0 if found else 1)
    s = axtree.select(found, q)
    if not s:
        sys.exit(1)
    n = s[0]
    if a.cmd == "label":
        print(n.get("AXLabel") or "")
    elif a.cmd == "value":
        print("" if n.get("AXValue") is None else n.get("AXValue"))
    elif a.cmd == "frame":
        f = axtree.frame(n) or (0, 0, 0, 0)
        print("%d %d %d %d" % f)
    else:
        x, y = axtree.center(n)
        print("%d %d" % (x, y))


if __name__ == "__main__":
    main()
