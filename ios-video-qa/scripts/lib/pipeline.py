"""새 각본 파이프라인(S0~S7) 상태와 요소 찾기 기록. pipeline.sh가 부른다.

    pipeline.py status     <work폴더>
    pipeline.py mark       <work폴더> <Sn> <done|waiting|blocked|failed> [메모] [--inputs JSON]
    pipeline.py rerun      <work폴더> <Sn>                 Sn 이후 단계를 stale로(산출물은 지우지 않는다)
    pipeline.py locate-add <work폴더> <n.k> <트리 파일> <사진> <질의…>
    pipeline.py gaps       <qa폴더> <work폴더> <ID>        locate.json·각본에서 코드 질문 생성 → 답 없는 blocking 수 출력

단계와 의존: S0 각본 → S1 요소 찾기 → S2 질문 → S3 스크립트 → S4 실행 전 검사 → S5 실행 → S6 재현 검증 → S7 판단 페이지.
앞 단계를 다시 하면 뒤 단계는 모두 stale이 되어 다시 해야 한다. S5는 매번 준비 상태를 다시 만든다(states.sh).
"""

import datetime
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "driver"))
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
NAMES = {"S0": "각본", "S1": "요소 찾기", "S2": "질문", "S3": "스크립트", "S4": "실행 전 검사", "S5": "실행",
         "S6": "재현 검증", "S7": "판단 페이지"}


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def load(work):
    p = os.path.join(work, "pipeline.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {"stages": {s: {"status": "todo"} for s in STAGES}, "log": []}


def save(work, st):
    os.makedirs(work, exist_ok=True)
    json.dump(st, open(os.path.join(work, "pipeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def status_text(st):
    lines = []
    for s in STAGES:
        x = st["stages"][s]
        lines.append(f"{s} {NAMES[s]:<8} {x['status']:<8} {x.get('at', '')}  {x.get('note', '')}")
    return "\n".join(lines)


def mark(work, stage, status, note="", inputs=None):
    st = load(work)
    i = STAGES.index(stage)
    for prev in STAGES[:i]:
        if st["stages"][prev]["status"] not in ("done",) and status == "done":
            sys.exit(f"{stage}를 끝낼 수 없음: 앞 단계 {prev}({NAMES[prev]})가 {st['stages'][prev]['status']}")
    st["stages"][stage] = {"status": status, "at": now(), "note": note, "inputs": inputs}
    st["log"].append({"at": now(), "stage": stage, "status": status, "note": note})
    save(work, st)


def rerun(work, stage):
    st = load(work)
    i = STAGES.index(stage)
    stale = []
    for s in STAGES[i + 1:]:
        if st["stages"][s]["status"] != "todo":
            st["stages"][s]["status"] = "stale"
            stale.append(s)
    st["stages"][stage]["status"] = "todo"
    st["log"].append({"at": now(), "stage": stage, "status": "rerun", "note": "뒤 단계 stale: " + ",".join(stale)})
    save(work, st)
    print(f"{stage}를 다시 함. stale로 표시: {', '.join(stale) or '없음'}")


def locate_add(work, disp, tree_file, shot, query_argv):
    import argparse
    import axtree
    p = argparse.ArgumentParser()
    axtree.add_query_args(p)
    q = axtree.query_from_ns(p.parse_args(query_argv))
    roots = axtree.load(open(tree_file).read())
    flat = axtree.flatten(roots)
    found = axtree.hits(flat, q, axtree.screen(flat))
    case = json.load(open(os.path.join(work, "case.json"), encoding="utf-8"))
    item = next((it for s in case["steps"] for it in s["items"] if it["display"] == disp), None)
    if not item:
        sys.exit(f"각본에 항목 {disp}가 없음")
    lp = os.path.join(work, "locate.json")
    loc = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    loc[item["id"]] = {"display": disp, "text": item["text"], "query": q, "n": len(found), "at": now(),
                       "candidates": [{"path": pth, "label": n.get("AXLabel"), "type": n.get("type"), "value": n.get("AXValue"),
                                       "frame": axtree.frame(n)} for n, pth, _ in found[:12]],
                       "tree": os.path.relpath(tree_file, work), "shot": os.path.relpath(shot, work)}
    json.dump(loc, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{disp} '{item['text']}': 후보 {len(found)}개" + "".join(f"\n   - {c['type']} {c['label']!r} {c['value']!r}" for c in loc[item['id']]["candidates"][:6]))


def gaps(qa_dir, work, cid):
    """코드가 만드는 질문: 후보가 여럿(고르는 규칙 필요), 후보가 없음(질의·기대값 불명확), 기대값이 모호한 문구"""
    import casefile
    lp = os.path.join(work, "locate.json")
    loc = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else {}
    case = json.load(open(os.path.join(work, "case.json"), encoding="utf-8"))
    ap = [sys.executable, "-I", "-B", os.path.join(HERE, "approve.py"), "gap-add", qa_dir, "--case", cid, "--origin", "code", "--blocking"]
    made = []
    for s in case["steps"]:
        for it in s["items"]:
            L = loc.get(it["id"])
            if L is None:
                made.append(subprocess.run(ap + ["--step", str(s["n"]), "--item", it["id"], "--reason", "not-located",
                    "--question", f"{it['display']} '{it['text']}': 요소 찾기(S1)에서 이 항목을 화면에서 찾아보지 않았다. 무엇을 보면 되나?",
                    "--options", "화면 문구로 정한다|이 항목은 자동 확인이 아니다(눈으로 확인으로)"], capture_output=True, text=True).stdout.strip())
            elif L["n"] == 0:
                made.append(subprocess.run(ap + ["--step", str(s["n"]), "--item", it["id"], "--reason", "no-candidate",
                    "--question", f"{it['display']} '{it['text']}': 질의 {L['query']}에 맞는 요소가 화면에 없었다. 기대값이 무엇인가?",
                    "--options", "문구를 고친다|조건이 다르다(준비 상태)"], capture_output=True, text=True).stdout.strip())
            elif L["n"] > 1:
                labels = [f"{c['type']} {c['label'] or c['value'] or c['path']}" for c in L["candidates"][:4]]
                made.append(subprocess.run(ap + ["--step", str(s["n"]), "--item", it["id"], "--reason", "multiple-candidates",
                    "--candidates", json.dumps(L["candidates"][:6], ensure_ascii=False),
                    "--query", json.dumps(L["query"], ensure_ascii=False, sort_keys=True),
                    "--question", f"{it['display']} '{it['text']}': 질의 {L['query']}에 맞는 후보가 {L['n']}개다. 어느 것을 봐야 하나?",
                    "--options", "|".join(labels + ["다른 규칙"])], capture_output=True, text=True).stdout.strip())
    for v in casefile.gaps_scan(casefile.parse(os.path.join(qa_dir, "cases", case["file"]))):
        made.append(subprocess.run(ap + ["--step", str(v["step"]), "--item", v["item"], "--reason", "unclear-expectation",
            "--question", f"'{v['text']}'은 참·거짓으로 판정하기 어렵다. 무엇이 보이면 통과인가?", "--options", "문구를 구체적으로 고친다"],
            capture_output=True, text=True).stdout.strip())
    import approve
    open_ = [g for g in approve.gaps_for(qa_dir, cid) if g.get("case") == cid and g.get("blocking") and not g.get("answer")]
    print(json.dumps({"made": [m for m in made if m], "open_blocking": [g["id"] for g in open_]}, ensure_ascii=False))


def main(argv):
    cmd = argv[0]
    if cmd == "status":
        print(status_text(load(argv[1])))
    elif cmd == "mark":
        inputs = json.loads(argv[argv.index("--inputs") + 1]) if "--inputs" in argv else None
        rest = [a for a in argv[2:] if a != "--inputs" and (not inputs or a != argv[argv.index("--inputs") + 1])]
        mark(argv[1], rest[0], rest[1], rest[2] if len(rest) > 2 else "", inputs)
    elif cmd == "rerun":
        rerun(argv[1], argv[2])
    elif cmd == "locate-add":
        locate_add(argv[1], argv[2], argv[3], argv[4], argv[5:])
    elif cmd == "gaps":
        gaps(argv[1], argv[2], argv[3])


if __name__ == "__main__":
    main(sys.argv[1:])
