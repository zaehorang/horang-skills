"""각본 리뷰 페이지(로컬 HTML)를 만든다. 공유용(share.py)과 같은 템플릿을 쓰고 저장 방식만 다르다.

    review.py <qa폴더> <결과 폴더> [--out <html 경로>]     기본: <qa폴더>/review/index.html

페이지에서: 각본마다 자동 확인의 실행 결과(근거 사진), "눈으로 확인" 항목별 판단(미검토/정상/이상/판단 불가 + 메모),
질문(gap) 답, 승인 요청 체크. "판단 JSON 내려받기"로 파일을 받아 사람이
  qa approve --from <파일>   qa answer --from <파일>   qa judgments --from <파일>
로 반영한다(대화형 터미널에서만).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import approve  # noqa: E402
import casefile  # noqa: E402


def jload(p, default):
    try:
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default
    except json.JSONDecodeError:
        return default


def build(qa_dir, run_dir, rel):
    """rel(path) → 페이지에서 쓸 경로(로컬: 상대 경로, 공유: 자산 키)"""
    run_dir = os.path.realpath(run_dir)
    meta = jload(os.path.join(run_dir, "run.json"), {})
    approvals = approve.approvals(qa_dir).load()
    gaps = approve.gaps_for(qa_dir)
    cases = []
    for cid, name in casefile.list_cases(os.path.join(qa_dir, "cases"), kind="auto"):
        md = os.path.join(qa_dir, "cases", name)
        c = casefile.parse(md)
        d = os.path.join(run_dir, cid)
        cov = {r["id"]: r for r in jload(os.path.join(d, "coverage.json"), {}).get("items", [])}
        result = jload(os.path.join(d, "result.json"), {}).get("status")
        events = []
        if os.path.exists(os.path.join(d, "events.jsonl")):
            events = [json.loads(l) for l in open(os.path.join(d, "events.jsonl"), encoding="utf-8") if l.strip()]
        evidence = []
        if os.path.exists(os.path.join(d, "evidence.jsonl")):
            evidence = [json.loads(l) for l in open(os.path.join(d, "evidence.jsonl"), encoding="utf-8") if l.strip()]
        steps = []
        for s in c["steps"]:
            start = next((e for e in events if e["kind"] == "step" and int(e.get("step", 0)) == s["n"]), None)
            items = []
            for it in s["items"]:
                cv = cov.get(it["id"], {"status": "not-run" if result else None})
                ev = [e for e in evidence if e.get("item") == it["id"] and e.get("shot")]
                shot = None
                if ev:
                    p = os.path.join(d, ev[-1]["shot"])
                    boxp = p[:-4] + "-box.png"
                    shot = rel(boxp if os.path.exists(boxp) else p) if os.path.exists(p) else None
                items.append({"id": it["id"], "display": it["display"], "text": it["text"], "status": cv.get("status"),
                              "result": cv.get("result"), "reason": cv.get("reason"), "evidence": shot})
            shotp = os.path.join(d, "steps", f"{s['n']}.png")
            steps.append({"n": s["n"], "action": s["action"], "external": s["external"], "items": items,
                          "visual": casefile.split_items(s.get("visual", "")),
                          "shot": rel(shotp) if os.path.exists(shotp) else None,
                          "t": float(start["t"]) if start else None})
        vid = os.path.join(d, "video.mp4")
        h = c["header"]
        level, msgs = approve.approval_status(qa_dir, cid, md)
        cases.append({"id": cid, "title": c["title"], "summary": c["summary"], "hash": approve.case_hash(md),
                      "scriptHash": approve.script_hash(approve.script_path(qa_dir, cid)),
                      "approvalLevel": level, "approvalMsgs": msgs,
                      "spec": h["명세"], "state": h["준비"], "conditions": h["조건"], "result": result,
                      "approval": approvals.get(cid) or {}, "video": rel(vid) if os.path.exists(vid) else None,
                      "gaps": [g for g in gaps if g.get("case") == cid], "steps": steps})
    return {"run": os.path.basename(run_dir), "condition": f"{meta.get('condition', '')} · {meta.get('device', '')}".strip(" ·"),
            "cases": cases, "globalGaps": [g for g in gaps if g.get("case") == "*"], "mode": "local", "assetMap": {}}


def render(data, adapter_js=""):
    tpl = open(os.path.join(ENGINE, "assets", "pages", "template.html"), encoding="utf-8").read()
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")   # </script>·<!-- 가 데이터 안에서 닫히지 않게
    js = f"<script>\n{adapter_js}\n</script>" if adapter_js else ""
    return tpl.replace("__QA_DATA__", blob).replace("__QA_ADAPTER__", js)


def main(argv):
    qa_dir, run_dir = os.path.abspath(argv[0]), argv[1]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(qa_dir, "review", "index.html")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    base = os.path.dirname(out)
    data = build(qa_dir, run_dir, lambda p: os.path.relpath(os.path.realpath(p), base))
    open(out, "w", encoding="utf-8").write(render(data))
    n = sum(len(s["visual"]) for c in data["cases"] for s in c["steps"])
    print(f"각본 리뷰 페이지: {out} (각본 {len(data['cases'])}개, 눈으로 확인 {n}개, 질문 {sum(len(c['gaps']) for c in data['cases']) + len(data['globalGaps'])}개)")


if __name__ == "__main__":
    main(sys.argv[1:])
