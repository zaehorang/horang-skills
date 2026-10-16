"""판정 함수와 읽기(출처 기록). 셸 판정 어휘(core.sh)와 재현 검증(verify.py)이 이 모듈의 같은 함수를 쓴다.

    judge.py screen                                         stdin 트리 → "W H"
    judge.py pick   [--save DIR] [--kind K] [--t T] [--retries R] -- <질의>
    judge.py expect present|gone|visible|tappable [--keyboard] [--kb-ids ..] [--kb-labels ..] [--save DIR] [기록 인자] -- <질의>
    judge.py check  eq|ne|gt|lt|ge|le|contains|delta_eq --in JSON --in JSON [--in JSON] [기록 인자]
    judge.py skip   --reason R [기록 인자]
    judge.py kbtop  --kb-ids .. --kb-labels ..               stdin 트리 → 키보드 윗변 y (없으면 exit 1)
    judge.py treesave <폴더>                                  stdin 트리 저장 → 파일 이름
    judge.py qjson  <질의>                                    질의 인자 → JSON(질문에 남길 질의)

출력은 셸이 eval할 수 있는 `P_*=값` 줄이다. 종료 코드: 0 통과/찾음, 1 실패/없음, 2 화면 정보 읽기 실패, 3 판정 불가, 4 인자 오류.
기록 인자(--evidence 파일 …)가 있으면 근거(evidence.jsonl)에 항목마다 한 줄씩 덧붙인다(덮어쓰지 않는다).

근거 한 줄마다 실행별 키(환경 변수 QA_EVID_KEY)로 서명(mac)한다. 키가 없으면 서명하지 않고, 서명 없는 줄은 실행 대조·재현 검증이 받지 않는다.

판정 함수의 피연산자는 출처 있는 읽기(pick 결과)여야 한다. 상수는 {"const": true}로 표시되고, 상수만으로 된 판정은
실행 전 검사(casefile.py)와 여기 check 둘 다에서 막는다.
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import shlex
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver"))
import axtree  # noqa: E402

JUDGE_VERSION = "1.1"   # 1.1: 덮는 요소(시트·알럿·팝오버) 가림 검사
EXPECT_FNS = ("present", "gone", "visible", "tappable")
CHECK_FNS = {"eq": 2, "ne": 2, "gt": 2, "lt": 2, "ge": 2, "le": 2, "contains": 2, "delta_eq": 3}
NUMERIC_FNS = ("gt", "lt", "ge", "le", "delta_eq")
NUM_RE = re.compile(r"-?\d+(\.\d+)?")
TOL = 0.5   # 포인트 오차 허용
# 앞에 떠서 아래 요소를 덮는 요소의 종류. 대상이 그 안에 있지 않으면 가림으로 본다
OVERLAY_TYPES = ("Sheet", "Alert", "Dialog", "Popover", "Menu")
# 키보드 판정은 화면 아래쪽(이 비율 아래)에 중심이 있는 키만 센다. 세로 iPhone 가정(references/keyboard-packs.md)
KB_LOWER_RATIO = 0.45


# ── 읽기 ──────────────────────────────────────────────────

def read_value(info, kind):
    if kind == "count":
        return str(info["n"])
    if not info["found"]:
        return ""
    if kind == "label":
        return info["label"]
    if kind == "value":
        return info["value"]
    if kind == "number":
        return axtree.first_int(info["label"]) or axtree.first_int(info["value"])
    if kind == "frame":
        return " ".join("%d" % v for v in info["frame"]) if info["frame"] else ""
    raise ValueError(kind)


def save_tree(raw, save_dir):
    if not save_dir:
        return None
    sha = hashlib.sha1(raw.encode()).hexdigest()[:12]
    os.makedirs(save_dir, exist_ok=True)
    path = os.path.join(save_dir, sha + ".json")
    if not os.path.exists(path):   # 같은 화면 정보는 한 번만(내용 해시로 중복 제거)
        with open(path, "w") as f:
            f.write(raw)
    return sha + ".json"


def provenance(q, info, tree, t, retries, kind=None):
    r = {"query": q, "tree": tree, "path": info.get("path"), "n": info["n"], "selector": info.get("selector"),
         "candidates": info["candidates"], "t_tree": t, "retries": retries, "frame": info.get("frame"),
         "screen": info.get("screen")}
    if kind:
        r["kind"] = kind
    return r


# ── 판정(순수 함수) ───────────────────────────────────────

def keyboard_top(flat, scr, kb_ids, kb_labels):
    if not scr:
        return None
    lower = scr[3] * KB_LOWER_RATIO
    ys, keys = [], 0
    assistant = next(iter(kb_ids), None) if isinstance(kb_ids, list) else None
    for n, _, _ in flat:
        f = axtree.frame(n)
        if not f or f[1] + f[3] / 2 <= lower or f[1] >= scr[3]:   # 화면 밖에 숨은 키(하드웨어 키보드 때)는 세지 않는다
            continue
        nid = n.get("AXUniqueId")
        if nid in kb_ids or (n.get("type") == "Button" and (n.get("AXLabel") or "") in kb_labels):
            ys.append(f[1])
            if nid != "SystemInputAssistantView":
                keys += 1   # 키가 있어야 화면 키보드다(하드웨어 키보드 때도 예상 단어 막대는 뜬다)
    return min(ys) if ys and keys else None


def is_keyboard_node(n, kb_ids):
    return n.get("AXUniqueId") in kb_ids


def overlap(a, b):
    """두 영역 (x, y, w, h)의 겹친 넓이"""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > TOL and h > TOL else 0.0


def covering(flat, path, f):
    """대상(path, 영역 f)을 덮는 앞 요소(시트·알럿 등). 대상이 그 안에 있거나 그 조상이면 제외. (path, 종류, 영역) 또는 None"""
    for n, p, _ in flat:
        if n.get("type") not in OVERLAY_TYPES:
            continue
        if path == p or path.startswith(p + "/") or p.startswith(path + "/"):
            continue
        of = axtree.frame(n)
        if of and overlap(f, of) > 0:
            return p, n.get("type"), of
    return None


def modal(flat, path):
    """대상 밖에 떠 있는 시트·알럿(누르기를 막는다). (path, 종류) 또는 None"""
    for n, p, _ in flat:
        if n.get("type") in ("Sheet", "Alert", "Dialog") and not (path == p or path.startswith(p + "/")):
            return p, n.get("type")
    return None


def judge_expect(fn, roots, q, keyboard=False, kb_ids=(), kb_labels=()):
    """(result, reason, info). result: pass | fail | undecidable"""
    info, flat, scr = axtree.pick(roots, q)
    if fn == "present":
        return ("pass", "있음", info) if info["found"] else ("fail", "화면에 없음", info)
    if fn == "gone":
        return ("pass", "없음", info) if not info["found"] else ("fail", f"아직 있음({info['n']}개)", info)
    # visible / tappable: 중심점이 아니라 영역 기준
    if not info["found"]:
        return "fail", "화면에 없음", info
    f = info["frame"]
    if f is None or scr is None:
        return "undecidable", "화면 정보에 영역 속성이 없음", info
    x, y, w, h = f
    W, H = scr[2], scr[3]
    if w <= 0 or h <= 0:
        return "fail", "영역 크기가 0", info
    if x < -TOL or y < -TOL or x + w > W + TOL or y + h > H + TOL:
        return "fail", f"화면 밖으로 잘림(영역 {x:.0f},{y:.0f},{w:.0f}x{h:.0f}, 화면 {W:.0f}x{H:.0f})", info
    for anc in info.get("ancestors") or []:
        an = axtree.node_at(roots, anc)
        if an.get("type") in ("ScrollView", "Table", "CollectionView"):
            af = axtree.frame(an)
            if af and (x < af[0] - TOL or y < af[1] - TOL or x + w > af[0] + af[2] + TOL or y + h > af[1] + af[3] + TOL):
                return "fail", f"스크롤 영역 밖으로 잘림(영역 y {y:.0f}~{y + h:.0f}, 스크롤 y {af[1]:.0f}~{af[1] + af[3]:.0f})", info
    cov = covering(flat, info["path"], f)
    if cov:
        cp, ct, of = cov
        return "fail", f"{ct}에 가려짐(요소 y {y:.0f}~{y + h:.0f}, {ct} y {of[1]:.0f}~{of[1] + of[3]:.0f})", info
    if fn == "tappable":
        md = modal(flat, info["path"])
        if md:
            return "fail", f"{md[1]}가 떠 있어 누를 수 없음", info
    top = keyboard_top(flat, scr, set(kb_ids), set(kb_labels))
    info["keyboard_top"] = top
    if keyboard and top is None:
        return "fail", "화면 키보드가 없음", info
    node = axtree.node_at(roots, info["path"])
    if top is not None and not is_keyboard_node(node, kb_ids) and y + h > top + TOL:
        return "fail", f"키보드에 가려짐(요소 아래끝 y={y + h:.0f}, 키보드 윗변 y={top:.0f})", info
    if fn == "tappable":
        if "enabled" not in node:
            return "undecidable", "화면 정보에 활성 속성이 없음", info
        if not node.get("enabled"):
            return "fail", "비활성", info
    where = f"키보드 위(아래끝 y={y + h:.0f} ≤ {top:.0f})" if top is not None else "화면 안"
    return "pass", f"보임: {where}", info


def as_number(v):
    v = (v or "").strip()
    return float(v) if NUM_RE.fullmatch(v) else None


def judge_check(fn, values):
    """values: 입력 값 문자열 목록. (result, reason)"""
    if any(v in (None, "") for v in values):
        return "undecidable", "비교할 값을 읽지 못함(빈 값)"
    if fn in NUMERIC_FNS:
        nums = [as_number(v) for v in values]
        if any(n is None for n in nums):
            return "undecidable", "숫자가 아닌 값: " + ", ".join(repr(v) for v, n in zip(values, nums) if n is None)
        a, b = nums[0], nums[1]
        ok = {"gt": a > b, "lt": a < b, "ge": a >= b, "le": a <= b,
              "delta_eq": len(nums) > 2 and a - b == nums[2]}[fn]
        expr = {"gt": f"{values[0]} > {values[1]}", "lt": f"{values[0]} < {values[1]}", "ge": f"{values[0]} ≥ {values[1]}",
                "le": f"{values[0]} ≤ {values[1]}",
                "delta_eq": f"{values[0]} − {values[1]} = {values[2] if len(values) > 2 else '?'}"}[fn]
        return ("pass" if ok else "fail"), expr
    a, b = values[0], values[1]
    ok = {"eq": a == b, "ne": a != b, "contains": b in a}[fn]
    expr = {"eq": f"{a!r} = {b!r}", "ne": f"{a!r} ≠ {b!r}", "contains": f"{a!r} ⊇ {b!r}"}[fn]
    return ("pass" if ok else "fail"), expr


# ── 근거 기록 ─────────────────────────────────────────────

def write_evidence(a, fn, inputs, result, reason, t_tree=None, tree=None, extra=None):
    if not a.evidence:
        return
    items = [i for i in (a.items or "").split(",") if i]
    errors = json.loads(a.errors) if a.errors else []
    cost = None
    if a.cost_start:
        cost = int((time.time() - float(a.cost_start)) * 1000)
    base = {"check_id": a.check_id, "items": items, "step": a.step, "phase": a.phase, "fn": fn, "desc": a.desc,
            "judge_version": JUDGE_VERSION, "inputs": inputs, "result": result, "reason": reason,
            "t_tree": t_tree, "tree": tree, "t_shot": a.t_shot, "shot": a.shot, "errors": errors, "cost_ms": cost}
    if extra:
        base.update(extra)
    key = os.environ.get("QA_EVID_KEY")
    with open(a.evidence, "a") as f:
        for it in items or [None]:   # 항목마다 한 줄(한 판정이 여러 항목을 덮어도 항목별 기록이 남는다)
            line = dict(base, item=it)
            if key:
                line["mac"] = mac(key, line)
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def mac(key, line):
    """casefile.evidence_mac과 같은 규칙: mac 필드를 뺀 정렬 JSON에 HMAC-SHA256"""
    body = json.dumps({k: v for k, v in line.items() if k != "mac"}, ensure_ascii=False, sort_keys=True)
    return hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()


def emit(**kv):
    for k, v in kv.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        elif v is None:
            v = ""
        print(f"P_{k.upper()}={shlex.quote(str(v))}")


def add_record_args(p):
    p.add_argument("--evidence"); p.add_argument("--check-id"); p.add_argument("--items"); p.add_argument("--step", type=int)
    p.add_argument("--desc"); p.add_argument("--phase"); p.add_argument("--shot"); p.add_argument("--t-shot", type=float)
    p.add_argument("--cost-start"); p.add_argument("--pre-tree"); p.add_argument("--errors")


class Parser(argparse.ArgumentParser):
    def error(self, message):   # 인자 오류는 4(2는 화면 정보 읽기 실패에 쓴다)
        print(f"judge.py 인자 오류: {message}", file=sys.stderr)
        sys.exit(4)


def main(argv):
    p = Parser(prog="judge.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    sub.add_parser("screen")
    pk = sub.add_parser("pick"); axtree.add_query_args(pk)
    pk.add_argument("--save"); pk.add_argument("--kind", default="label"); pk.add_argument("--t", type=float)
    pk.add_argument("--retries", type=int, default=0)
    ex = sub.add_parser("expect"); ex.add_argument("fn", choices=EXPECT_FNS); axtree.add_query_args(ex)
    ex.add_argument("--keyboard", action="store_true"); ex.add_argument("--kb-ids", default="")
    ex.add_argument("--kb-labels", default=""); ex.add_argument("--save"); ex.add_argument("--t", type=float)
    ex.add_argument("--retries", type=int, default=0); add_record_args(ex)
    ck = sub.add_parser("check"); ck.add_argument("fn", choices=list(CHECK_FNS)); ck.add_argument("--in", dest="inputs", action="append", default=[])
    add_record_args(ck)
    sk = sub.add_parser("skip"); sk.add_argument("--reason", default=""); add_record_args(sk)
    kb = sub.add_parser("kbtop"); kb.add_argument("--kb-ids", default=""); kb.add_argument("--kb-labels", default="")
    ts = sub.add_parser("treesave"); ts.add_argument("dir")
    qj = sub.add_parser("qjson"); axtree.add_query_args(qj)
    a = p.parse_args(argv)

    if a.cmd == "qjson":
        print(json.dumps(axtree.query_from_ns(a), ensure_ascii=False, sort_keys=True))
        return 0

    if a.cmd == "treesave":   # stdin 트리를 근거 폴더에 저장하고 파일 이름만 출력(내용 해시로 중복 제거)
        raw = sys.stdin.read()
        try:
            axtree.load(raw)
        except axtree.ReadError:
            return 2
        print(save_tree(raw, a.dir))
        return 0

    if a.cmd in ("screen", "pick", "expect", "kbtop"):
        raw = sys.stdin.read()
        try:
            roots = axtree.load(raw)
        except axtree.ReadError as e:
            print(e, file=sys.stderr)
            return 2
    if a.cmd == "screen":
        scr = axtree.screen(axtree.flatten(roots))
        if not scr:
            return 2
        print("%d %d" % (scr[2], scr[3]))
        return 0
    if a.cmd == "kbtop":
        flat = axtree.flatten(roots)
        top = keyboard_top(flat, axtree.screen(flat), set(a.kb_ids.split(",")), set(a.kb_labels.split(",")))
        if top is None:
            return 1
        print("%d" % top)
        return 0
    if a.cmd == "pick":
        q = axtree.query_from_ns(a)
        info, _, _ = axtree.pick(roots, q)
        tree = save_tree(raw, a.save)
        value = read_value(info, a.kind)
        prov = provenance(q, info, tree, a.t, a.retries, a.kind)
        emit(found=int(info["found"]), n=info["n"], sel=info.get("selector", ""), path=info.get("path", ""),
             x="%d" % info["center"][0] if info["found"] else "", y="%d" % info["center"][1] if info["found"] else "",
             label=info.get("label", ""), value=value, frame=" ".join("%d" % v for v in info["frame"]) if info.get("frame") else "",
             tree=tree or "", read={"value": value, "read": prov})
        return 0 if (info["found"] or a.kind == "count") else 1
    if a.cmd == "expect":
        q = axtree.query_from_ns(a)
        kb_ids = [s for s in a.kb_ids.split(",") if s]
        kb_labels = [s for s in a.kb_labels.split(",") if s]
        result, reason, info = judge_expect(a.fn, roots, q, a.keyboard, kb_ids, kb_labels)
        tree = save_tree(raw, a.save) if a.evidence else None
        prov = provenance(q, info, tree, a.t, a.retries)
        extra = {"keyboard": a.keyboard, "kb_ids": kb_ids, "kb_labels": kb_labels, "keyboard_top": info.get("keyboard_top"),
                 "pre_tree": a.pre_tree}
        write_evidence(a, "expect_" + a.fn, [{"name": "screen", "read": prov}], result, reason, a.t, tree, extra)
        emit(result=result, reason=reason, n=info["n"], sel=info.get("selector", ""), path=info.get("path", ""),
             x="%d" % info["center"][0] if info["found"] else "", y="%d" % info["center"][1] if info["found"] else "")
        return {"pass": 0, "fail": 1, "undecidable": 3}[result]
    if a.cmd == "check":
        inputs = [json.loads(s) for s in a.inputs]
        if len(inputs) != CHECK_FNS[a.fn]:
            emit(result="undecidable", reason=f"{a.fn}는 입력 {CHECK_FNS[a.fn]}개가 필요(받은 것 {len(inputs)}개)")
            return 3
        if all((i.get("read") or {}).get("const") for i in inputs):
            emit(result="undecidable", reason="상수만으로 된 판정(화면에서 읽은 값이 없음)")
            return 3
        result, reason = judge_check(a.fn, [i.get("value", "") for i in inputs])
        write_evidence(a, "check_" + a.fn, inputs, result, reason)
        emit(result=result, reason=reason)
        return {"pass": 0, "fail": 1, "undecidable": 3}[result]
    if a.cmd == "skip":
        if not a.reason.strip():
            emit(result="undecidable", reason="건너뛴 사유가 없음")
            return 3
        write_evidence(a, "skip", [], "skipped", a.reason)
        emit(result="skipped", reason=a.reason)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
