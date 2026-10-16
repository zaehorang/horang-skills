"""판정 기록 재현 검증(S6). 앱을 다시 돌리지 않고, 실행 때 저장한 화면 정보로 같은 판정 함수를 다시 돌린다.

    verify.py <results/시각-조건> [--quiet]      → verify.json, 요약 출력. 막을 조건이면 exit 1

근거 줄은 실행별 키(QA_EVID_KEY 환경 변수, 없으면 결과 폴더의 .evidence-key)로 서명을 확인한다. 서명이 없거나 맞지 않는
줄은 "근거 위조 의심"으로 막고 그 줄은 쓰지 않는다.

판정마다
  (a) 재현 일치: 저장된 트리에서 같은 질의·같은 판정 함수(judge_version)로 다시 판정해 결과가 같은가
  (b) 유효한 변형의 실패: 입력을 바꾼 변형을 같은 판정에 넣으면 실패로 바뀌는가. 변형은 먼저 유효한지 검사한다
      expect_present  맞은 요소(후보 전부)를 트리에서 지움 / 질의 문구를 트리에 없는 문구로       → 실패해야
      expect_gone     이 실행 중 실제로 보였던 같은 요소를 트리에 넣음                          → 실패해야
      expect_visible·tappable  요소를 화면 밖으로 옮김 / 시트가 요소를 덮게 함 / 키보드가 요소를 덮게 함 / (tappable) 비활성으로 → 실패해야
      check_*         읽은 요소의 값을 결과가 뒤집히는 값으로 바꾸고 같은 질의로 다시 읽음          → 실패해야
결과(항목마다): 검증됨 / 검증 불가 / 변형 부적합 / 판정 결함
  검증됨     (a) 일치 + (b) 유효한 변형이 실패로 바뀜(값 변화에 반응함)
  검증 불가  근거 화면 정보가 없음, 상수 입력만 남음, 속성 누락 등으로 다시 판정할 수 없음
  변형 부적합 유효한 변형을 만들지 못함(변형하면 질의가 다른 요소를 고르는 등)
  판정 결함  재현이 원래 결과와 다르거나, 유효한 변형에도 결과가 바뀌지 않음, 또는 사라져야 할 대상이
            이 실행 중 한 번도 화면에 없었음(항상 통과하는 판정)
항목 단위로 센다. 판정 기록이 없는 항목(건너뜀·미실행)도 분모에 들어가고 검증 불가 쪽으로 센다.
막는 조건(exit 1): 판정 결함 1개 이상, 근거 위조 의심, 검증 불가 비율이 상한을 넘음.
상한은 환경 변수 QA_UNVERIFIABLE_CASE_MAX(각본별, 기본 30) · QA_UNVERIFIABLE_RUN_MAX(전체, 기본 20), 단위는 %.
"""

import copy
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver"))
import axtree  # noqa: E402
import casefile  # noqa: E402
import judge  # noqa: E402

CASE_LIMIT = float(os.environ.get("QA_UNVERIFIABLE_CASE_MAX") or 30) / 100
RUN_LIMIT = float(os.environ.get("QA_UNVERIFIABLE_RUN_MAX") or 20) / 100
ABSENT = "∅변형∅"


def load_tree(case_dir, name, cache):
    if not name:
        return None
    if name not in cache:
        p = os.path.join(case_dir, "evidence", "trees", name)
        try:
            cache[name] = axtree.load(open(p).read()) if os.path.exists(p) else None
        except axtree.ReadError:
            cache[name] = None
    return cache[name]


def remove_paths(roots, paths):
    r = copy.deepcopy(roots)
    for path in sorted(paths, key=lambda p: [int(x) for x in p.strip("/").split("/")], reverse=True):
        parts = [int(x) for x in path.strip("/").split("/")]
        if len(parts) < 2:
            return None   # 루트(앱 전체)는 지울 수 없다
        parent = axtree.node_at(r, "/" + "/".join(map(str, parts[:-1])))
        kids = parent.get("children") or []
        if parts[-1] < len(kids):
            del kids[parts[-1]]
    return r


def app_node(roots):
    return next((n for n, _, _ in axtree.flatten(roots) if n.get("type") == "Application"), roots[0])


def insert_node(roots, node):
    r = copy.deepcopy(roots)
    n = copy.deepcopy(node)
    n["children"] = []
    app_node(r).setdefault("children", []).append(n)
    return r


def set_attr(roots, path, attr, value):
    r = copy.deepcopy(roots)
    n = axtree.node_at(r, path)
    if attr == "frame":
        n["frame"] = value
    else:
        n[attr] = value
    return r


def read_again(roots, read):
    q = read.get("query") or {}
    info, _, _ = axtree.pick(roots, q)
    return info, judge.read_value(info, read.get("kind") or "label")


# ── expect ────────────────────────────────────────────────

def all_trees_with(run_dir, q):
    """이 실행(없으면 최근 3회 실행)의 저장 트리에서 질의에 맞는 요소(첫 것)를 찾는다"""
    runs = [run_dir] + sorted((p for p in glob.glob(os.path.join(os.path.dirname(run_dir), "*"))
                               if os.path.isdir(p) and not os.path.islink(p) and os.path.basename(p) < os.path.basename(run_dir)),
                              reverse=True)[:3]
    for p in (f for r in runs for f in sorted(glob.glob(os.path.join(r, "*", "evidence", "trees", "*.json")))):
        try:
            roots = axtree.load(open(p).read())
        except axtree.ReadError:
            continue
        info, flat, scr = axtree.pick(roots, dict(q, any=True))
        if info["found"]:
            return axtree.node_at(roots, info["path"]), p
    return None, None


def verify_expect(ev, case_dir, run_dir, cache):
    fn = ev["fn"].replace("expect_", "")
    inp = (ev.get("inputs") or [{}])[0]
    read = inp.get("read") or {}
    roots = load_tree(case_dir, read.get("tree") or ev.get("tree"), cache)
    if roots is None:
        return "unverifiable", "근거 화면 정보가 없음"
    q = read.get("query") or {}
    kb = dict(keyboard=ev.get("keyboard", False), kb_ids=ev.get("kb_ids") or [], kb_labels=ev.get("kb_labels") or [])
    res, reason, info = judge.judge_expect(fn, roots, q, **kb)
    if res != ev["result"]:
        return "defect", f"재현 결과가 다름(기록 {ev['result']}, 재현 {res}: {reason})"
    if res != "pass":
        return "unverifiable", f"원래 판정이 통과가 아님({res})"
    muts, notes = [], []
    if fn == "present":
        if any(p in ("/0",) for p in info["candidates"]) or any(axtree.node_at(roots, p).get("type") == "Application" for p in info["candidates"]):
            return "defect", "질의가 앱 화면 전체에 맞음(무엇이 있어도 통과)"
        flat = axtree.flatten(roots)
        allp = [p for _, p, _ in axtree.hits(flat, q, axtree.screen(flat))]
        m = remove_paths(roots, allp)
        if m is not None:
            muts.append(("맞은 요소를 모두 지움", m, q))
        for k in ("label", "contains", "value", "id"):
            if k in q:
                q2 = dict(q, **{k: ABSENT})
                if not axtree.pick(roots, q2)[0]["found"]:
                    muts.append((f"질의의 {k}를 없는 문구로", roots, q2))
                break
    elif fn == "gone":
        node, where = None, None
        pre = load_tree(case_dir, ev.get("pre_tree"), cache) if ev.get("pre_tree") else None
        if pre is not None:
            pinfo, _, _ = axtree.pick(pre, dict(q, any=True))
            if pinfo["found"]:
                node, where = axtree.node_at(pre, pinfo["path"]), "기다리기 시작한 순간의 화면"
        if node is None:
            node, p = all_trees_with(run_dir, q)
            where = f"실행 기록의 다른 화면({os.path.relpath(p, os.path.dirname(run_dir))})" if node is not None else None
        if node is None:
            return "defect", "사라져야 할 대상이 이 실행과 최근 3회 실행에서 한 번도 화면에 없었음(질의가 틀렸으면 항상 통과)"
        m = insert_node(roots, node)
        if not axtree.pick(m, q)[0]["found"]:
            return "unfit", f"{where}에서 가져온 요소를 넣어도 질의에 맞지 않음(화면 밖 위치 등)"
        muts.append((f"{where}에서 본 요소를 다시 넣음", m, q))
    else:  # visible / tappable
        path = info.get("path")
        f = info.get("frame")
        scr = info.get("screen")
        if not path or not f or not scr:
            return "unverifiable", "영역 정보가 없음"
        moved = set_attr(roots, path, "frame", {"x": f[0], "y": scr[3] + 10, "width": f[2], "height": f[3]})
        muts.append(("요소를 화면 밖으로 옮김", moved, dict(q, any=True)))
        sheet = {"type": "Sheet", "AXLabel": ABSENT, "frame": {"x": 0, "y": f[1], "width": scr[2], "height": max(f[3], 1)}}
        muts.append(("시트가 요소를 덮게 함", insert_node(roots, sheet), q))
        if kb["kb_ids"]:
            occ = {"type": "Group", "AXUniqueId": kb["kb_ids"][0],
                   "frame": {"x": 0, "y": max(f[1] + f[3] / 2, scr[3] * 0.46), "width": scr[2], "height": scr[3]}}
            if f[1] + f[3] > occ["frame"]["y"]:
                muts.append(("키보드가 요소 아래쪽을 덮게 함", insert_node(roots, occ), q))
        if fn == "tappable":
            muts.append(("요소를 비활성으로", set_attr(roots, path, "enabled", False), q))
    if not muts:
        return "unfit", "유효한 변형을 만들지 못함"
    results = []
    for name, m, q2 in muts:
        r2, why, info2 = judge.judge_expect(fn, m, q2, **kb)
        if fn in ("visible", "tappable") and info2.get("found") and info2.get("path") != info.get("path") and name != "요소를 화면 밖으로 옮김":
            notes.append(f"{name}: 다른 요소를 고름(부적합)")
            continue
        results.append((name, r2, why))
    if not results:
        return "unfit", "; ".join(notes)
    stuck = [n for n, r2, _ in results if r2 == "pass"]
    if stuck:
        return "defect", "변형에도 통과: " + ", ".join(stuck)
    return "verified", "; ".join(f"{n} → {r2}" for n, r2, _ in results)


# ── check ─────────────────────────────────────────────────

def flip_target(fn, values, idx):
    """values[idx]를 무엇으로 바꾸면 판정이 뒤집히나(문자열). 못 정하면 None"""
    a = values
    num = [judge.as_number(v) for v in a]
    if fn in judge.NUMERIC_FNS:
        if any(n is None for n in num):
            return None
        def fmt(x):
            return str(int(x)) if float(x).is_integer() else str(x)
        if fn == "delta_eq":
            if idx == 0: return fmt(num[1] + num[2] + 1)
            if idx == 1: return fmt(num[0] - num[2] + 1)
            return None
        other = num[1 - idx]
        target = {("gt", 0): other, ("gt", 1): num[0], ("lt", 0): other, ("lt", 1): num[0],
                  ("ge", 0): other - 1, ("ge", 1): num[0] + 1, ("le", 0): other + 1, ("le", 1): num[0] - 1}[(fn, idx)]
        return fmt(target)
    if fn == "eq":
        if num[idx] is not None:   # 숫자는 숫자로 바꾼다(숫자만 읽는 읽기에 글자를 붙이면 값이 그대로다)
            return str(int(num[idx]) + 1) if float(num[idx]).is_integer() else str(num[idx] + 1)
        return a[idx] + "∅" if a[idx] else "∅"
    if fn == "ne":
        return a[1 - idx]
    if fn == "contains":
        return a[0].replace(a[1], "∅") if idx == 0 and a[1] else None
    return None


def substitute(read, old_attr_value, old_value, new_value):
    """읽은 속성 문자열에서 읽은 값만 바꾼다(number는 첫 숫자만)"""
    kind = read.get("kind") or "label"
    if kind == "number":
        return re.sub(re.escape(old_value), new_value, old_attr_value or "", count=1)
    return new_value


def verify_check(ev, case_dir, cache):
    fn = ev["fn"].replace("check_", "")
    inputs = ev.get("inputs") or []
    values = [i.get("value", "") for i in inputs]
    reads = [(k, i["read"]) for k, i in enumerate(inputs) if not (i.get("read") or {}).get("const")]
    if not reads:
        return "unverifiable", "출처 있는 입력이 없음"
    trees = {}
    for k, r in reads:
        roots = load_tree(case_dir, r.get("tree"), cache)
        if roots is None:
            return "unverifiable", f"입력 {inputs[k].get('name')}의 근거 화면 정보가 없음"
        info, v = read_again(roots, r)
        if v != values[k]:
            return "defect", f"입력 {inputs[k].get('name')}을 다시 읽으니 값이 다름(기록 {values[k]!r}, 재현 {v!r})"
        trees[k] = roots
    # 같은 화면 정보의 같은 요소를 두 번 읽으면 두 입력은 언제나 같다
    keys = [((r.get("tree"), r.get("path"), r.get("kind"))) for _, r in reads]
    if len(keys) > 1 and len(set(keys)) == 1:
        return "defect", "두 입력이 같은 화면의 같은 요소를 읽음(항상 같은 값)"
    # 질의 조건이 곧 읽은 값이면(라벨로 찾아 라벨을 읽음) 그 입력은 사실상 상수다
    bound = []
    for k, r in reads:
        q, kind = r.get("query") or {}, r.get("kind") or "label"
        if (kind == "label" and q.get("label") == values[k]) or (kind == "value" and str(q.get("value")) == values[k]):
            bound.append(inputs[k].get("name"))
    if bound and len(bound) == len(reads):
        return "defect", f"읽은 값이 질의 조건에 묶여 있음({', '.join(bound)}: 찾는 조건과 읽는 값이 같아 사실상 상수)"
    res, why = judge.judge_check(fn, values)
    if res != ev["result"]:
        return "defect", f"재현 결과가 다름(기록 {ev['result']}, 재현 {res})"
    if res != "pass":
        return "unverifiable", f"원래 판정이 통과가 아님({res})"
    tried = []
    for k, r in reads:
        target = flip_target(fn, values, k)
        if target is None:
            tried.append(f"{inputs[k].get('name')}: 뒤집는 값을 정하지 못함")
            continue
        kind = r.get("kind") or "label"
        attr = {"label": "AXLabel", "number": "AXLabel", "value": "AXValue"}.get(kind)
        if not attr or not r.get("path"):
            tried.append(f"{inputs[k].get('name')}: 바꿀 수 없는 읽기({kind})")
            continue
        node = axtree.node_at(trees[k], r["path"])
        newattr = substitute(r, node.get(attr), values[k], target)
        if kind == "number" and axtree.first_int(node.get(attr) or "") != values[k]:
            attr = "AXValue"
            newattr = target
        # 같은 화면 정보·같은 요소를 읽은 다른 입력도 함께 바뀐다(같은 것을 두 번 읽은 판정을 잡는다)
        mutated = {}
        for k2, r2 in reads:
            base = mutated.get(r2.get("tree")) or trees[k2]
            if r2.get("tree") == r.get("tree") and r2.get("path") == r.get("path"):
                base = set_attr(base, r["path"], attr, newattr)
            mutated[r2.get("tree")] = base
        new_values = list(values)
        ok = True
        for k2, r2 in reads:
            info2, v2 = read_again(mutated[r2.get("tree")], r2)
            if r2.get("path") and info2.get("path") != r2.get("path"):
                ok = False   # 변형하니 질의가 다른 요소를 고름(질의가 그 값에 묶여 있음)
            new_values[k2] = v2
        if not ok:
            tried.append(f"{inputs[k].get('name')}: 값을 바꾸면 질의가 다른 요소를 고름(부적합)")
            continue
        r2, why2 = judge.judge_check(fn, new_values)
        if r2 == "pass":
            return "defect", f"입력 {inputs[k].get('name')}을 {target!r}로 바꿔도 통과(값 변화에 반응하지 않음)"
        return "verified", f"입력 {inputs[k].get('name')}을 {target!r}로 바꾸면 {r2}({why2})"
    return "unfit", "; ".join(tried) or "유효한 변형을 만들지 못함"


# ── 실행 단위 ─────────────────────────────────────────────

def evidence_key(run_dir):
    k = os.environ.get("QA_EVID_KEY")
    if k:
        return k
    p = os.path.join(run_dir, ".evidence-key")
    return open(p).read().strip() if os.path.exists(p) else None


def main(argv):
    run_dir = os.path.abspath(argv[0])
    quiet = "--quiet" in argv
    key = evidence_key(run_dir)
    out = {"cases": {}, "warnings": [], "blocking": [], "limits": {"case": CASE_LIMIT, "run": RUN_LIMIT}}
    kinds = ("verified", "unverifiable", "unfit", "defect", "skipped", "not_run")
    tot = {k: 0 for k in kinds}
    if key is None:
        out["blocking"].append("근거 서명 키가 없음(이 실행의 근거를 믿을 수 없음)")
    for case_dir in sorted(p for p in glob.glob(os.path.join(run_dir, "QA-*")) if os.path.isdir(p)):
        cid = os.path.basename(case_dir)
        cj = os.path.join(case_dir, "case.json")
        if not os.path.exists(cj):
            continue
        case = json.load(open(cj, encoding="utf-8"))
        evs, bad = casefile.read_evidence(os.path.join(case_dir, "evidence.jsonl"), key or "")
        if bad:
            out["blocking"].append(f"{cid}: 서명이 맞지 않는 근거 {bad}줄(근거 위조 의심. 그 줄은 쓰지 않음)")
        cache, checks = {}, {}
        for e in evs:
            if e.get("fn") == "skip":
                continue
            checks.setdefault(e["check_id"], e)
        per_check = {}
        for cid_, e in checks.items():
            if e.get("judge_version") != judge.JUDGE_VERSION:
                per_check[cid_] = ("unverifiable", f"판정기 버전이 다름({e.get('judge_version')})")
            elif e["fn"].startswith("expect_"):
                per_check[cid_] = verify_expect(e, case_dir, run_dir, cache)
            else:
                per_check[cid_] = verify_check(e, case_dir, cache)
        items = {}
        for e in evs:
            if e.get("fn") == "skip" or not e.get("item"):
                continue
            st, why = per_check[e["check_id"]]
            items.setdefault(e["item"], []).append({"check_id": e["check_id"], "status": st, "why": why, "desc": e.get("desc")})
        order = ["defect", "unverifiable", "unfit", "verified"]
        item_status = {}
        for it in casefile.all_items(case):
            lst = items.get(it["id"])
            if lst:
                worst = min(lst, key=lambda x: order.index(x["status"]))["status"]
                item_status[it["id"]] = {"status": worst, "checks": lst}
            elif any(e.get("item") == it["id"] and e.get("fn") == "skip" for e in evs):
                item_status[it["id"]] = {"status": "skipped", "checks": [{"status": "skipped", "why": "건너뜀(판정 기록 없음)", "desc": it["text"]}]}
            else:
                item_status[it["id"]] = {"status": "not_run", "checks": [{"status": "not_run", "why": "판정 기록 없음", "desc": it["text"]}]}
        s = {k: sum(v["status"] == k for v in item_status.values()) for k in kinds}
        n = len(item_status) or 1
        s["unverifiable_ratio"] = (s["unverifiable"] + s["unfit"] + s["skipped"] + s["not_run"]) / n
        for k in kinds:
            tot[k] += s[k]
        out["cases"][cid] = {"summary": s, "items": item_status}
        if s["unverifiable_ratio"] > CASE_LIMIT:
            out["blocking"].append(f"{cid}: 검증 불가 비율 {s['unverifiable_ratio']:.0%}가 각본 상한 {CASE_LIMIT:.0%}를 넘음")
        if s["defect"]:
            out["blocking"].append(f"{cid}: 판정 결함 {s['defect']}개")
    n = sum(tot.values()) or 1
    tot["unverifiable_ratio"] = (tot["unverifiable"] + tot["unfit"] + tot["skipped"] + tot["not_run"]) / n
    out["summary"] = tot
    if tot["unverifiable_ratio"] > RUN_LIMIT:
        out["blocking"].append(f"전체 검증 불가 비율 {tot['unverifiable_ratio']:.0%}가 상한 {RUN_LIMIT:.0%}를 넘음")
    json.dump(out, open(os.path.join(run_dir, "verify.json"), "w"), ensure_ascii=False, indent=1)
    if not quiet:
        print(f"재현 검증: 검증됨 {tot['verified']} · 검증 불가 {tot['unverifiable']} · 변형 부적합 {tot['unfit']} · "
              f"건너뜀 {tot['skipped']} · 미실행 {tot['not_run']} · 판정 결함 {tot['defect']} · "
              f"검증 불가 비율 {tot['unverifiable_ratio']:.0%}")
        for cid, c in out["cases"].items():
            for it, v in c["items"].items():
                if v["status"] != "verified":
                    worst = next(x for x in v["checks"] if x["status"] == v["status"])
                    print(f"  {cid} {it}: {v['status']} — {worst['desc']}: {worst['why']}")
        for w in out["warnings"]:
            print("  ⚠ " + w)
        for b in out["blocking"]:
            print("  ✗ " + b)
    return 1 if out["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
