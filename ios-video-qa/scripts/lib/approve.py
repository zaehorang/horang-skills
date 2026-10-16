"""각본 승인과 질문(gap) 답의 기록. 둘 다 사람의 결정이라 같은 규칙으로 지킨다.

    approve.py approve   <qa폴더> <ID…>                 사람: 대화형 터미널(tty)에서만, 에이전트 환경이면 거부
    approve.py approve   <qa폴더> --from <승인요청.json> 사람: 판단 페이지에서 내려받은 승인 요청을 반영(tty 필요)
    approve.py answer    <qa폴더> <G번호> <답>            사람: tty에서만. 그 규칙을 쓰는 질의(선택 방법 포함)도 함께 승인
    approve.py answer    <qa폴더> <G번호> --bind          사람: 답은 그대로 두고, 규칙을 쓰는 지금의 질의를 승인 범위에 더함
    approve.py answer    <qa폴더> --from <답.json>        사람: 페이지에서 내려받은 답 반영(tty 필요)
    approve.py gap-add   <qa폴더> --case ID --step N --item ID --origin code|ai --reason R --question Q --options "a|b" [--query JSON] [--blocking]
    approve.py record-change <qa폴더> <ID>               스크립트가 지난 실행과 다르면 steps/.changes/<ID>-<시각>.diff를 남긴다
    approve.py status    <qa폴더>                          승인·질문 상태 표
    approve.py judgments <qa폴더> --from <review.json>     사람: 리뷰 페이지의 "눈으로 확인" 판단 반영(tty 필요)

승인 범위는 각본(md) 전체와 그 스크립트(steps/<ID>.sh)다. 둘 중 하나라도 승인 뒤 바뀌면 다시 승인해야 한다.
선택 규칙(답이 있는 질문)은 규칙마다 승인된 쓰임(각본 범위·질의·선택 방법)을 저장하고, 실행 전 검사가 스크립트의 쓰임과 맞춰 본다.
via=bootstrap 기록(예전 엔진 시험용)은 읽기만 한다. 사람 승인으로 치지 않는다.

파일(qa 폴더 안)
  cases/.approved.json       각본별 현재 승인: {ID: {version, hash, script_hash, approved_by, at, via}}
  cases/.approved/<ID>.md    승인한 각본 원문, <ID>.sh 승인한 스크립트(바뀐 부분을 보여 주는 데 쓴다)
  cases/.approvals.log       승인 기록 체인(줄마다 앞 줄의 해시를 이어 받는다)
  cases/.approved.snapshot   이 명령이 마지막으로 쓴 .approved.json 사본
  gaps.json / gaps.log / gaps.snapshot   질문과 답(규칙의 쓰임 uses 포함), 같은 방식
  steps/.changes/            스크립트 변경 기록(<ID>.last = 지난 실행 때 내용, <ID>-<시각>.diff)

한계: 서명이 아니라 경로 표식(via)·각본 해시·기록 체인·스냅샷 비교로 지킨다. 같은 사용자 권한의 프로그램이 파일
여러 개를 함께 고치면 막지 못한다. 대신 실행 전 검사가 명령 밖 수정을 diff로 드러낸다.
"""

import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

AGENT_ENV_PREFIXES = ("CLAUDE_CODE_", "CODEX_", "CURSOR_AGENT", "AIDER_", "GEMINI_CLI", "OPENCODE", "AMP_")
AGENT_ENV_NAMES = ("CLAUDECODE", "CLAUDE_PID", "CODEX_SANDBOX", "CURSOR_TRACE_ID")
HUMAN_VIA = ("tty", "page")
ALL_VIA = HUMAN_VIA + ("bootstrap",)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def sha1(s):
    return hashlib.sha1(s.encode()).hexdigest()


def normalize_case(text):
    """각본 해시용 정규화: 줄끝(CRLF·뒤 공백)과 파일 앞뒤 빈 줄만 정리한다"""
    lines = [l.rstrip() for l in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def case_hash(md_path):
    return sha1(normalize_case(open(md_path, encoding="utf-8").read()))


def script_hash(path):
    """스크립트 해시(각본과 같은 정규화). 파일이 없으면 None"""
    return sha1(normalize_case(open(path, encoding="utf-8").read())) if path and os.path.exists(path) else None


def script_path(qa_dir, cid):
    return os.path.join(qa_dir, "steps", cid + ".sh")


def git_user(qa_dir):
    r = subprocess.run(["git", "-C", qa_dir, "config", "user.name"], capture_output=True, text=True)
    return r.stdout.strip() or os.environ.get("USER", "?")


def agent_env():
    return sorted(k for k in os.environ if k in AGENT_ENV_NAMES or k.startswith(AGENT_ENV_PREFIXES))


def human_guard(what):
    """사람만 쓸 수 있는 경로인지. 아니면 이유를 출력하고 종료"""
    bad = agent_env()
    if bad:
        sys.exit(f"{what}: 에이전트 환경에서는 할 수 없습니다(감지: {', '.join(bad[:3])}…). 사람이 터미널에서 직접 실행하세요.")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit(f"{what}: 대화형 터미널에서만 할 수 있습니다.")


def confirm(prompt, expect):
    got = input(prompt).strip()
    if got != expect:
        sys.exit("입력이 맞지 않아 취소했습니다.")


# ── 기록 저장소(현재 상태 + 체인 기록 + 스냅샷) ─────────────

class Store:
    def __init__(self, data_path, log_path, snap_path, empty):
        self.data_path, self.log_path, self.snap_path, self.empty = data_path, log_path, snap_path, empty

    def load(self):
        if not os.path.exists(self.data_path):
            return json.loads(json.dumps(self.empty))
        return json.load(open(self.data_path, encoding="utf-8"))

    def raw(self):
        return open(self.data_path, encoding="utf-8").read() if os.path.exists(self.data_path) else ""

    def log_lines(self):
        if not os.path.exists(self.log_path):
            return []
        return [json.loads(l) for l in open(self.log_path, encoding="utf-8") if l.strip()]

    def save(self, data, entry):
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
        with open(self.data_path, "w", encoding="utf-8") as f:
            f.write(text)
        with open(self.snap_path, "w", encoding="utf-8") as f:
            f.write(text)
        lines = self.log_lines()
        prev = lines[-1]["sha"] if lines else ""
        body = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"entry": entry, "prev": prev, "sha": sha1(prev + body)}, ensure_ascii=False) + "\n")

    def integrity(self):
        """명령 밖 수정 검사. (문제 목록, diff 문자열)"""
        problems, diff = [], ""
        cur, snap = self.raw(), (open(self.snap_path, encoding="utf-8").read() if os.path.exists(self.snap_path) else "")
        if cur != snap:
            problems.append(f"{os.path.basename(self.data_path)}이(가) 승인 명령 밖에서 바뀜")
            diff = "".join(difflib.unified_diff(snap.splitlines(True), cur.splitlines(True), "명령이 쓴 것", "지금"))
        prev = ""
        for i, l in enumerate(self.log_lines()):
            body = json.dumps(l["entry"], ensure_ascii=False, sort_keys=True)
            if l.get("prev") != prev or l.get("sha") != sha1(prev + body):
                problems.append(f"{os.path.basename(self.log_path)} {i + 1}번째 줄의 체인이 끊김")
                break
            prev = l["sha"]
        return problems, diff


def approvals(qa_dir):
    c = os.path.join(qa_dir, "cases")
    return Store(os.path.join(c, ".approved.json"), os.path.join(c, ".approvals.log"), os.path.join(c, ".approved.snapshot"), {})


def gaps_store(qa_dir):
    return Store(os.path.join(qa_dir, "gaps.json"), os.path.join(qa_dir, "gaps.log"), os.path.join(qa_dir, "gaps.snapshot"),
                 {"gaps": []})


def find_case_md(qa_dir, cid):
    for f in sorted(os.listdir(os.path.join(qa_dir, "cases"))):
        if f.startswith(cid + "-") and f.endswith(".md"):
            return os.path.join(qa_dir, "cases", f)
    sys.exit(f"각본을 찾지 못함: {cid}")


# ── 승인 상태(실행 전 검사가 쓴다) ──────────────────────────

def approval_status(qa_dir, cid, md_path, sh_path=None):
    """(level, 메시지 목록) level: ok | pending(사람 승인 대기) | block(기록 위조 의심 등)"""
    st = approvals(qa_dir)
    data = st.load()
    problems, diff = st.integrity()
    if problems:
        return "block", [p for p in problems] + ([f"바뀐 부분:\n{diff}"] if diff else [])
    e = data.get(cid)
    if not e:
        return "pending", [f"{cid}: 승인 기록 없음. 사람이 `qa approve {cid}`로 승인해야 한다"]
    if e.get("via") not in ALL_VIA:
        return "block", [f"{cid}: 승인 경로가 알 수 없는 값({e.get('via')!r})"]
    logged = [l["entry"] for l in st.log_lines() if l["entry"].get("case") == cid]
    keys = ("version", "hash", "script_hash", "via")
    if not logged or {k: logged[-1].get(k) for k in keys} != {k: e.get(k) for k in keys}:
        return "block", [f"{cid}: 현재 승인이 승인 기록 체인의 마지막 기록과 다름(명령 밖 수정 의심)"]
    msgs = []
    if e.get("via") == "bootstrap":
        msgs.append(f"{cid}: 사람 승인 전(bootstrap v{e.get('version')}). 사람이 `qa approve {cid}`로 승인해야 한다")
    if case_hash(md_path) != e.get("hash"):
        old = os.path.join(qa_dir, "cases", ".approved", cid + ".md")
        changed = changed_sections(open(old, encoding="utf-8").read() if os.path.exists(old) else "",
                                   open(md_path, encoding="utf-8").read())
        msgs.append(f"{cid}: 각본이 승인(v{e.get('version')}) 뒤 바뀜: {', '.join(changed) or '내용'}. 다시 승인해야 한다")
    sh = sh_path or script_path(qa_dir, cid)
    cur = script_hash(sh)
    if not e.get("script_hash"):
        msgs.append(f"{cid}: 승인 기록에 스크립트가 없음(스크립트 승인 전)")
    elif cur != e.get("script_hash"):
        msgs.append(f"{cid}: 스크립트가 승인(v{e.get('version')}) 뒤 바뀜(바뀐 부분: steps/.changes). 다시 승인해야 한다")
    return ("pending" if msgs else "ok"), msgs


def human_approved(qa_dir, cid, md_path, sh_path=None):
    """사람이 승인했고 각본·스크립트가 그대로인가"""
    return approval_status(qa_dir, cid, md_path, sh_path)[0] == "ok"


def changed_sections(old, new):
    """바뀐 부분을 사람이 읽는 이름으로: 머리 항목, N단계 행동/자동 확인/눈으로 확인, 메모"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import casefile
    try:
        a, b = casefile.parse_text(old, "old.md"), casefile.parse_text(new, "new.md")
    except Exception:
        return ["형식"]
    out = []
    if a["title"] != b["title"] or a["summary"] != b["summary"]:
        out.append("제목·설명")
    if a["header"] != b["header"]:
        out.append("머리 항목")
    for i in range(max(len(a["steps"]), len(b["steps"]))):
        sa = a["steps"][i] if i < len(a["steps"]) else {}
        sb = b["steps"][i] if i < len(b["steps"]) else {}
        for k, name in (("action", "행동"), ("auto", "자동 확인"), ("visual", "눈으로 확인"), ("check", "확인")):
            if sa.get(k) != sb.get(k):
                out.append(f"{i + 1}단계 {name}")
        if not sa or not sb:
            out.append(f"{i + 1}단계 추가·삭제")
    if a["notes"] != b["notes"]:
        out.append("메모")
    return sorted(set(out), key=out.index)


def gaps_for(qa_dir, cid=None):
    return [g for g in gaps_store(qa_dir).load()["gaps"] if cid is None or g.get("case") in (cid, "*")]


def use_key(query, selector):
    return json.dumps({"query": query, "selector": selector}, ensure_ascii=False, sort_keys=True)


def rule_use_status(qa_dir, gid, scope, query, selector):
    """스크립트의 선택(`# 규칙: G번호`) 한 곳이 승인된 규칙 안에 있는가. (level, 메시지) level: ok | pending | block
    scope: 그 줄이 속한 각본 ID. 공통 파일(flows·states)은 "*"."""
    g = next((g for g in gaps_for(qa_dir) if g["id"] == gid), None)
    if not g:
        return "block", f"규칙 {gid}가 gaps.json에 없음"
    if g.get("case") not in ("*", scope):
        return "block", f"규칙 {gid}는 {g.get('case')}의 규칙이라 {scope}에서 쓸 수 없음"
    if not g.get("answer"):
        return "pending", f"규칙 {gid}에 답이 없음(사람 대기: `qa answer {gid} <답>`)"
    if g.get("via") not in HUMAN_VIA:
        return "pending", f"규칙 {gid}의 답이 사람 확인 전({g.get('via')}): {g.get('rule')}"
    if use_key(query, selector) not in {use_key(u.get("query"), u.get("selector")) for u in g.get("uses") or []}:
        return "pending", (f"규칙 {gid}의 승인 범위 밖 질의({selector}: {json.dumps(query, ensure_ascii=False)}). "
                           f"사람이 `qa answer {gid} --bind`로 확인해야 한다")
    return "ok", ""


def current_uses(qa_dir, gid):
    """지금 스크립트·flows·states에서 이 규칙을 쓰는 곳 [(파일:줄, 범위, 질의, 선택)]"""
    import casefile
    return [u for u in casefile.selector_uses(qa_dir) if u["rule"] == gid]


# ── 명령 ──────────────────────────────────────────────────

def do_approve(qa_dir, ids, via, approver):
    st = approvals(qa_dir)
    problems, _ = st.integrity()
    if problems:
        sys.exit("승인 기록이 명령 밖에서 바뀌어 있어 먼저 확인이 필요합니다: " + "; ".join(problems))
    data = st.load()
    for cid in ids:
        md = find_case_md(qa_dir, cid)
        sh = script_path(qa_dir, cid)
        e = {"case": cid, "version": (data.get(cid) or {}).get("version", 0) + 1, "hash": case_hash(md),
             "script_hash": script_hash(sh), "approved_by": approver, "at": now(), "via": via}
        data[cid] = {k: e[k] for k in ("version", "hash", "script_hash", "approved_by", "at", "via")}
        snap = os.path.join(qa_dir, "cases", ".approved")
        os.makedirs(snap, exist_ok=True)
        with open(os.path.join(snap, cid + ".md"), "w", encoding="utf-8") as f:
            f.write(open(md, encoding="utf-8").read())
        if os.path.exists(sh):
            with open(os.path.join(snap, cid + ".sh"), "w", encoding="utf-8") as f:
                f.write(open(sh, encoding="utf-8").read())
        st.save(data, e)
        print(f"{cid}: 승인 v{e['version']} ({via}, {approver})")


def do_answer(qa_dir, gid, answer, via, who, uses):
    """answer가 None이면 답은 그대로 두고 쓰임만 더한다"""
    st = gaps_store(qa_dir)
    problems, _ = st.integrity()
    if problems:
        sys.exit("질문 기록이 명령 밖에서 바뀌어 있어 먼저 확인이 필요합니다: " + "; ".join(problems))
    data = st.load()
    g = next((g for g in data["gaps"] if g["id"] == gid), None)
    if not g:
        sys.exit(f"질문 없음: {gid}")
    if answer is None and not g.get("answer"):
        sys.exit(f"{gid}에 답이 없어 쓰임만 승인할 수 없습니다. 먼저 답하세요")
    if answer is not None:
        opts = g.get("options") or []
        if answer.isdigit() and 1 <= int(answer) <= len(opts):
            answer = opts[int(answer) - 1]
        g.update(answer=answer, rule=answer, uses=[])
    elif g.get("via") not in HUMAN_VIA:
        sys.exit(f"{gid}의 답이 사람 확인 전({g.get('via')})이라 쓰임만 승인할 수 없습니다. 답을 다시 하세요")
    have = {use_key(u["query"], u["selector"]) for u in g.get("uses") or []}
    for u in uses:
        if use_key(u["query"], u["selector"]) not in have:
            g.setdefault("uses", []).append({"query": u["query"], "selector": u["selector"], "where": u["where"]})
            have.add(use_key(u["query"], u["selector"]))
    g.update(answered_by=who, at=now(), via=via)
    st.save(data, {"gap": gid, "answer": g["answer"], "rule": g["rule"], "uses": g.get("uses"), "via": via, "by": who,
                   "at": g["at"]})
    print(f"{gid}: 답 '{g['answer']}' · 승인된 쓰임 {len(g.get('uses') or [])}곳 ({via}, {who})")


def show_uses(uses):
    if not uses:
        print("  (지금 이 규칙을 쓰는 질의가 없음. 스크립트를 쓴 뒤 `--bind`로 더할 수 있다)")
    for u in uses:
        print(f"  {u['where']}  [{u['scope']}] {u['selector']}  {json.dumps(u['query'], ensure_ascii=False)}")


def record_change(qa_dir, cid):
    """스크립트가 지난 실행 때와 다르면 diff를 남긴다. 출력: 승인본과의 diff 파일(없으면 빈 줄)"""
    sh = script_path(qa_dir, cid)
    if not os.path.exists(sh):
        return
    d = os.path.join(qa_dir, "steps", ".changes")
    os.makedirs(d, exist_ok=True)
    cur = open(sh, encoding="utf-8").read()
    last_p = os.path.join(d, cid + ".last")
    last = open(last_p, encoding="utf-8").read() if os.path.exists(last_p) else None
    if last != cur:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        diff = "".join(difflib.unified_diff((last or "").splitlines(True), cur.splitlines(True),
                                            "지난 실행" if last is not None else "(처음)", "지금"))
        with open(os.path.join(d, f"{cid}-{stamp}.diff"), "w", encoding="utf-8") as f:
            f.write(diff)
        with open(last_p, "w", encoding="utf-8") as f:
            f.write(cur)
    snap = os.path.join(qa_dir, "cases", ".approved", cid + ".sh")
    if os.path.exists(snap):
        old = open(snap, encoding="utf-8").read()
        if old != cur:
            p = os.path.join(d, cid + ".since-approval.diff")
            with open(p, "w", encoding="utf-8") as f:
                f.write("".join(difflib.unified_diff(old.splitlines(True), cur.splitlines(True), "승인본", "지금")))
            print(p)


def gap_add(qa_dir, a):
    st = gaps_store(qa_dir)
    problems, _ = st.integrity()
    if problems:
        sys.exit("질문 기록이 명령 밖에서 바뀌어 있음: " + "; ".join(problems))
    data = st.load()
    key = (a.case, a.item, a.reason, a.question)
    for g in data["gaps"]:
        if (g.get("case"), g.get("item"), g.get("reason"), g.get("question")) == key:
            print(g["id"])
            return
    gid = "G%d" % (max([int(g["id"][1:]) for g in data["gaps"]] or [0]) + 1)
    g = {"id": gid, "case": a.case, "step": a.step, "item": a.item, "blocking": a.blocking, "origin": a.origin,
         "reason": a.reason, "question": a.question, "options": [o for o in (a.options or "").split("|") if o],
         "candidates": json.loads(a.candidates) if a.candidates else [], "where": a.where,
         "query": json.loads(a.query) if a.query else None, "answer": None, "rule": None, "uses": [], "created": now()}
    data["gaps"].append(g)
    st.save(data, {"gap": gid, "created": True, "case": a.case, "reason": a.reason})
    print(gid)


def main(argv):
    p = argparse.ArgumentParser(prog="approve.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    ap = sub.add_parser("approve"); ap.add_argument("qa"); ap.add_argument("ids", nargs="*")
    ap.add_argument("--from", dest="src")
    an = sub.add_parser("answer"); an.add_argument("qa"); an.add_argument("args", nargs="*")
    an.add_argument("--from", dest="src"); an.add_argument("--bind", action="store_true")
    ga = sub.add_parser("gap-add"); ga.add_argument("qa")
    for k in ("--case", "--item", "--origin", "--reason", "--question", "--options", "--candidates", "--where", "--query"):
        ga.add_argument(k)
    ga.add_argument("--step", type=int); ga.add_argument("--blocking", action="store_true")
    rc = sub.add_parser("record-change"); rc.add_argument("qa"); rc.add_argument("id")
    stt = sub.add_parser("status"); stt.add_argument("qa")
    jd = sub.add_parser("judgments"); jd.add_argument("qa"); jd.add_argument("--from", dest="src", required=True)
    a = p.parse_args(argv)
    qa = os.path.abspath(a.qa)

    if a.cmd == "approve":
        human_guard("각본 승인")
        if a.src:
            req = json.load(open(a.src, encoding="utf-8"))
            if req.get("kind") == "review":   # 리뷰 페이지가 내려준 통합 파일
                req = dict(req["approve"], reviewer=req.get("reviewer") or req["approve"].get("reviewer"))
            if req.get("kind") != "approve-request":
                sys.exit("승인 요청 파일이 아님")
            if not req.get("cases"):
                sys.exit("승인 요청한 각본이 없음")
            for c in req.get("cases", []):
                cur = case_hash(find_case_md(qa, c["id"]))
                if c.get("hash") != cur:
                    sys.exit(f"{c['id']}: 페이지에서 본 각본({c.get('hash', '')[:8]})과 지금 각본({cur[:8]})이 다름. 페이지를 다시 만드세요")
                if c.get("script_hash") != script_hash(script_path(qa, c["id"])):
                    sys.exit(f"{c['id']}: 페이지에서 본 스크립트와 지금 스크립트가 다름. 페이지를 다시 만드세요")
            ids = [c["id"] for c in req.get("cases", [])]
            print("승인할 각본(각본 + 스크립트): " + ", ".join(ids) + f" (페이지 확인자: {req.get('reviewer', '?')})")
            confirm("반영하려면 yes를 입력: ", "yes")
            do_approve(qa, ids, "page", req.get("reviewer") or git_user(qa))
            return 0
        if not a.ids:
            sys.exit("승인할 각본 ID가 없음")
        for cid in a.ids:
            md = find_case_md(qa, cid)
            print(open(md, encoding="utf-8").read())
            snap = os.path.join(qa, "cases", ".approved")
            for cur, old, name in ((md, os.path.join(snap, cid + ".md"), "각본"),
                                   (script_path(qa, cid), os.path.join(snap, cid + ".sh"), "스크립트")):
                if not os.path.exists(cur):
                    print(f"── {name} 없음: {cur}")
                    continue
                before = open(old, encoding="utf-8").read() if os.path.exists(old) else ""
                if name == "스크립트" and not before:
                    print("── 스크립트(처음 승인) ──")
                    print(open(cur, encoding="utf-8").read())
                elif before:
                    print(f"── 지난 승인과 다른 부분({name}) ──")
                    print("".join(difflib.unified_diff(before.splitlines(True), open(cur, encoding="utf-8").read().splitlines(True))))
            confirm(f"{cid}(각본과 스크립트)를 승인하려면 각본 ID를 다시 입력: ", cid)
        do_approve(qa, a.ids, "tty", git_user(qa))
        return 0
    if a.cmd == "answer":
        human_guard("질문 답")
        if a.src:
            req = json.load(open(a.src, encoding="utf-8"))
            if not req.get("answers"):
                sys.exit("답이 없음")
            plan = []
            for x in req.get("answers", []):
                uses = current_uses(qa, x["id"])
                print(f"{x['id']}: {x['answer']}")
                show_uses(uses)
                plan.append((x, uses))
            confirm("답과 위 쓰임을 반영하려면 yes를 입력: ", "yes")
            for x, uses in plan:
                do_answer(qa, x["id"], x["answer"], "page", req.get("reviewer") or git_user(qa), uses)
            return 0
        if not a.args:
            sys.exit("질문 번호가 없음")
        gid, ans = a.args[0], " ".join(a.args[1:])
        if not a.bind and not ans:
            sys.exit("답이 없음(쓰임만 승인하려면 --bind)")
        g = next((g for g in gaps_for(qa) if g["id"] == gid), None)
        if g:
            print(g["question"]); [print(f"  {i + 1}. {o}") for i, o in enumerate(g.get("options") or [])]
            if g.get("query"):
                print(f"  질문이 생긴 질의: {json.dumps(g['query'], ensure_ascii=False)}")
        uses = current_uses(qa, gid)
        print("이 규칙으로 승인할 쓰임(선택 방법·질의):")
        show_uses(uses)
        what = f"쓰임 {len(uses)}곳" if a.bind else f"답 '{ans}'과 쓰임 {len(uses)}곳"
        confirm(f"{gid}의 {what}을 확정하려면 질문 번호를 다시 입력: ", gid)
        do_answer(qa, gid, None if a.bind else ans, "tty", git_user(qa), uses)
        return 0
    if a.cmd == "judgments":
        # 눈으로 확인 판단도 사람의 결정이다(출시 판단에 미검토 0건이 필요). 사람만 반영한다
        human_guard("판단 기록 반영")
        req = json.load(open(a.src, encoding="utf-8"))
        if req.get("kind") != "review":
            sys.exit("리뷰 페이지가 내려준 파일이 아님")
        js = req.get("judgments") or []
        c = {k: sum(j["verdict"] == k for j in js) for k in ("미검토", "정상", "이상", "판단 불가")}
        print(f"{req.get('run')} · 확인자 {req.get('reviewer') or '?'} · " + " · ".join(f"{k} {v}" for k, v in c.items()))
        confirm("반영하려면 yes를 입력: ", "yes")
        d = os.path.join(qa, "judgments")
        os.makedirs(d, exist_ok=True)
        rec = {"run": req.get("run"), "condition": req.get("condition"), "reviewer": req.get("reviewer"), "imported_by": git_user(qa),
               "at": now(), "via": "page", "counts": c, "judgments": js, "fixed_questions": req.get("fixed_questions")}
        safe = lambda v: re.sub(r"[^\w.-]", "_", str(v or "unknown"))[:80]
        path = os.path.join(d, f"{safe(req.get('run'))}-{safe(req.get('reviewer'))}.json")
        json.dump(rec, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"저장: {path}. 출시 판단에는 미검토 0건, 이상 0건(또는 합의)이 필요")
        return 0
    if a.cmd == "gap-add":
        gap_add(qa, a)
        return 0
    if a.cmd == "record-change":
        record_change(qa, a.id)
        return 0
    if a.cmd == "status":
        data = approvals(qa).load()
        cases_dir = os.path.join(qa, "cases")
        ids = sorted({f.split("-", 2)[0] + "-" + f.split("-", 2)[1] for f in os.listdir(cases_dir)
                      if re.match(r"QA-\d+-.*\.md$", f)} | set(data))
        for cid in ids:
            e = data.get(cid) or {}
            md = next((os.path.join(cases_dir, f) for f in sorted(os.listdir(cases_dir)) if f.startswith(cid + "-") and f.endswith(".md")), None)
            level, msgs = approval_status(qa, cid, md) if md else ("block", ["각본 파일 없음"])
            state = {"ok": "승인됨", "pending": "사람 승인 대기", "block": "차단"}[level]
            print(f"{cid}\t{state}\tv{e.get('version', '-')}\t{e.get('via', '-')}\t{e.get('approved_by', '-')}\t{e.get('at', '-')}")
            for m in msgs:
                print(f"\t  · {m}")
        for g in gaps_for(qa):
            if not g.get("answer"):
                state = "답 없음"
            else:
                state = f"답: {g['answer']} ({g.get('via')}{', 사람 확인 전' if g.get('via') not in HUMAN_VIA else ''}) · 쓰임 {len(g.get('uses') or [])}곳"
            print(f"{g['id']}\t{g['case']}\t{'blocking' if g.get('blocking') else '-'}\t{state}\t{g['question']}")
        for name, st in (("승인", approvals(qa)), ("질문", gaps_store(qa))):
            problems, _ = st.integrity()
            if problems:
                print(f"⚠ {name} 기록: " + "; ".join(problems))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
