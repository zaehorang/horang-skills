"""AXe `describe-ui` 화면 정보(JSON 트리)를 읽고 요소를 고른다. 드라이버 형식(AXLabel, AXUniqueId, frame …)을 아는 유일한 모듈.

judge.py(판정), verify.py(재현 검증), axq.py(CLI)가 같은 질의 규칙을 쓰도록 여기 한 곳에 둔다.

질의(query)는 dict다:
  label, contains, id, type, value      문자열 조건
  enabled, disabled, any                 참/거짓 (any = 화면 밖 요소도 포함)
  below, above                           중심 y 범위
  after                                  "x,y": 읽기 순서(y, x)로 이 점 뒤에 오는 요소만
  first, last, nth                       후보가 여럿일 때 고르는 방법(명시 선택). 없으면 암묵 선택(첫 후보)
"""

import argparse
import json
import re

SELECTORS = ("first", "last", "nth")


class ReadError(Exception):
    pass


def load(raw):
    try:
        roots = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise ReadError("화면 정보를 읽지 못함(빈 결과 또는 JSON 아님)")
    if not roots:
        raise ReadError("화면 정보가 비어 있음")
    return roots


def flatten(roots):
    """[(node, path, ancestor_paths)] 깊이 우선. path는 "/0/3/1" 같은 트리 안 위치"""
    out = []

    def walk(n, path, anc):
        out.append((n, path, anc))
        for i, c in enumerate(n.get("children") or []):
            walk(c, f"{path}/{i}", anc + [path])

    for i, r in enumerate(roots):
        walk(r, f"/{i}", [])
    return out


def node_at(roots, path):
    parts = [int(p) for p in path.strip("/").split("/")]
    n = roots[parts[0]]
    for p in parts[1:]:
        n = (n.get("children") or [])[p]
    return n


def frame(n):
    """(x, y, w, h). 영역 정보가 없으면 None"""
    f = n.get("frame")
    if not f or any(k not in f for k in ("x", "y", "width", "height")):
        return None
    return float(f["x"]), float(f["y"]), float(f["width"]), float(f["height"])


def center(n):
    f = frame(n) or (0, 0, 0, 0)
    return f[0] + f[2] / 2, f[1] + f[3] / 2


def screen(flat):
    app = next((n for n, _, _ in flat if n.get("type") == "Application"), None)
    f = frame(app) if app else None
    return f  # (0, 0, W, H) 또는 None


def describe(n):
    x, y = center(n)
    return "%-11s label=%r id=%r value=%r center=(%d,%d) enabled=%s" % (
        n.get("type"), n.get("AXLabel"), n.get("AXUniqueId"), n.get("AXValue"), x, y, n.get("enabled"))


def add_query_args(p):
    p.add_argument("--label"); p.add_argument("--contains"); p.add_argument("--id"); p.add_argument("--type")
    p.add_argument("--value")
    p.add_argument("--any", action="store_true")
    p.add_argument("--enabled", action="store_true"); p.add_argument("--disabled", action="store_true")
    p.add_argument("--below", type=float); p.add_argument("--above", type=float)
    p.add_argument("--after")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--first", action="store_true"); g.add_argument("--last", action="store_true")
    g.add_argument("--nth", type=int)


QUERY_FIELDS = ("label", "contains", "id", "type", "value", "any", "enabled", "disabled", "below", "above", "after",
                "first", "last", "nth")


def query_from_ns(ns):
    q = {}
    for k in QUERY_FIELDS:
        v = getattr(ns, k, None)
        if v is not None and v is not False:   # nth 0은 남긴다(0 == False라 'in'으로 거르면 사라진다)
            q[k] = v
    return q


def query_to_argv(q):
    out = []
    for k in QUERY_FIELDS:
        if k not in q:
            continue
        v = q[k]
        if v is True:
            out.append(f"--{k}")
        else:
            out += [f"--{k}", str(v)]
    return out


def matches(n, q, scr, x=None, y=None):
    label = n.get("AXLabel") or ""
    if "label" in q and label != q["label"]: return False
    if "contains" in q and q["contains"] not in label: return False
    if "id" in q and n.get("AXUniqueId") != q["id"]: return False
    if "type" in q and n.get("type") != q["type"]: return False
    if "value" in q and str(n.get("AXValue")) != str(q["value"]): return False
    if q.get("enabled") and not n.get("enabled"): return False
    if q.get("disabled") and n.get("enabled"): return False
    cx, cy = center(n) if x is None else (x, y)
    if not q.get("any"):
        W, H = (scr[2], scr[3]) if scr else (10_000, 10_000)
        if not (0 <= cx <= W and 0 <= cy <= H): return False
    if "below" in q and cy <= float(q["below"]): return False
    if "above" in q and cy >= float(q["above"]): return False
    if "after" in q:
        ax, ay = (float(v) for v in str(q["after"]).split(","))
        if (round(cy), cx) <= (round(ay), ax): return False
    return True


def hits(flat, q, scr):
    found = [(n, p, a) for n, p, a in flat if matches(n, q, scr)]
    return sorted(found, key=lambda t: (round(center(t[0])[1]), center(t[0])[0]))


def select(found, q):
    """(node, path, ancestors, selector) 또는 None. selector: first|last|nth|implicit|only"""
    if not found:
        return None
    if q.get("last"):
        return (*found[-1], "last")
    if "nth" in q:
        i = int(q["nth"])
        return (*found[i], "nth") if i < len(found) else None
    if q.get("first"):
        return (*found[0], "first")
    return (*found[0], "only" if len(found) == 1 else "implicit")


def pick(roots, q):
    """질의 결과와 출처 정보. 판정·읽기 기록에 그대로 들어간다"""
    flat = flatten(roots)
    scr = screen(flat)
    found = hits(flat, q, scr)
    s = select(found, q)
    info = {"found": s is not None, "n": len(found), "candidates": [p for _, p, _ in found[:10]],
            "screen": list(scr) if scr else None}
    if s:
        n, path, anc, sel = s
        info.update(path=path, ancestors=anc, selector=sel, label=n.get("AXLabel") or "",
                    value="" if n.get("AXValue") is None else str(n.get("AXValue")),
                    type=n.get("type"), enabled=n.get("enabled"), frame=frame(n), center=list(center(n)))
    return info, flat, scr


def first_int(s):
    """label의 첫 숫자(부호 없음). "남은 날 D-15" → 15"""
    m = re.search(r"\d+", s or "")
    return m.group(0) if m else ""
