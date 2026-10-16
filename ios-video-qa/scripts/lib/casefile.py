"""각본 md(`qa/cases/QA-*.md`)를 읽고, 스크립트를 실행 전에 검사하고, 실행 뒤 항목별 실행 여부를 대조한다.

    casefile.py parse    <md>                        각본을 JSON으로(항목 ID 포함)
    casefile.py env      <md>                        스크립트가 source할 zsh 변수
    casefile.py ids      <md>                        단계별 확인 항목 ID(스크립트 작성용)
    casefile.py check    <md> <script> <qa폴더>       실행 전 검사(S4). "차단\t…" / "대기\t…" / "경고\t…" 줄
                                                      exit 1 차단 있음 · 5 사람 승인 대기만 있음 · 0 통과
    casefile.py check-shared <qa폴더>                 flows.sh·states.sh 검사(선택 규칙, 금지 어휘). 종료 코드는 check와 같다
    casefile.py uses     <qa폴더>                     선택 규칙(`# 규칙: G번호`)을 쓰는 곳 전부(JSON)
    casefile.py gaps-scan <md>                       기대값이 불명확한 자동 확인(코드가 만드는 질문 후보)
    casefile.py coverage <case.json> <evidence.jsonl> [--out 파일]   실행 대조표(실행됨/건너뜀/미실행)
                         근거 줄의 서명(QA_EVID_KEY 환경 변수의 실행별 키)이 맞지 않는 줄은 세지 않는다. exit 0 미실행 없음 · 1 있음
    casefile.py verdict  <coverage.json> <rc> <qa폴더> <md> <script>   각본 결과: pass | fail | incomplete | skipped
                         건너뜀이 있으면 통과가 아니다(skipped). 사람이 승인한 스크립트의 건너뜀(사유 포함)만 통과로 센다
    casefile.py list     <cases 폴더> [--condition 이름] [--auto|--manual] [ID…]

항목 ID: 자동 확인 칸을 ' · '로 나눈 항목마다 "정규화 문구 SHA-1 앞 8자리#단계.순번"(예: 3f9a1b2c#3.2).
정규화는 줄끝·바깥 공백만. 문구가 바뀌거나 단계가 삽입·재배열되면 ID가 바뀌어 스크립트 연결이 무효가 된다.

머리 항목 키는 한국어가 기준이고 영어 별칭을 받는다(HEADER_ALIASES). 값도 같다(INPUT_ALIASES, RUN_ALIASES).
"""

import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RUN_ALIASES = {"자동": "자동", "수동": "수동", "auto": "자동", "manual": "수동"}
STEP_RE = re.compile(r"^\s*step\s+(\d+)\b", re.M)
HEADER_KEYS = ("명세", "준비", "실행", "입력", "조건", "화면", "비교 제외")
HEADER_ALIASES = {"spec": "명세", "prep": "준비", "state": "준비", "run": "실행", "input": "입력", "conditions": "조건",
                  "condition": "조건", "screens": "화면", "screen": "화면", "ignore": "비교 제외", "exclude": "비교 제외"}
LIST_KEYS = ("조건", "화면", "비교 제외")
NOTES_HEADINGS = ("메모", "notes")
EXTERNAL_MARKS = ("[외부]", "[external]")
# 각본 '입력:' 값 → 실행 방식. software: 화면 키보드 · hardware: 하드웨어 키 입력 · none: 글자 입력 없음
INPUT_ALIASES = {"화면 키보드": "software", "블루투스 키보드": "hardware", "없음": "none",
                 "software keyboard": "software", "hardware keyboard": "hardware", "bluetooth keyboard": "hardware",
                 "none": "none"}
EXPECT_CALLS = ("expect_present", "expect_gone", "expect_visible", "expect_tappable")
CHECK_CALLS = ("check_eq", "check_ne", "check_gt", "check_lt", "check_ge", "check_le", "check_contains", "check_delta_eq")
CHECK_ARITY = {"check_delta_eq": 3}
JUDGE_CALLS = EXPECT_CALLS + CHECK_CALLS + ("skip",)
QUERY_CALLS = ("ui_tap", "ui_press", "ui_find", "ui_wait", "ui_wait_gone", "ui_locate", "ui_read") + EXPECT_CALLS
LEGACY = ("ui_check", "ui_expect", "ui_expect_gone", "ui_expect_above_keyboard", "ui_number", "ui_label", "ui_value",
          "ui_frame")
WAIT_LIKE = ("ui_wait", "ui_wait_gone", "ui_locate", "ui_read", "home_ready", "ui_wait_stable", "ui_drag", "ui_swipe") + JUDGE_CALLS
VAGUE = ("적절", "정상", "자연스럽", "어색", "제대로", "잘 ", "깔끔")
# 스크립트·flows·states에서 쓰면 안 되는 것: 근거·판정 상태를 직접 건드리거나 엔진 함수를 바꿀 수 있는 어휘
FORBIDDEN = [
    (r"\bEVID\b|\bQARJ?_|\bQA_EVID_KEY\b|\b_?QA_KEY\b|NONCE", "근거·읽기 기록 변수를 직접 다룸"),
    (r"\.failed\b|judge\.py|\bJUDGE\b|evidence|python", "판정기·근거 파일을 직접 다룸"),
    (r"(?<![\w])_(?!sleep\b)[A-Za-z]\w*", "엔진 내부 함수·변수(_로 시작)를 씀(_sleep만 허용)"),
    (r"\b(eval|source|exec|trap|unset|unfunction|declare|printenv|env|alias|builtin|command)\b|^\s*\.\s", "셸 우회 어휘"),
    (r"\btypeset\b(?!\s+-A\s+QA_STATES=)", "셸 우회 어휘(typeset은 QA_STATES 선언만)"),
    (r"\bset\b\s*(?:[-+]|$)|\bfunctions\[|\bexport\b", "셸 상태를 바꾸는 어휘"),
    (r"\b(rm|mv|cp|ln|chmod|tee|dd)\b", "파일을 쓰거나 지우는 어휘"),
    (r"\$\{?(OUT|RUN_DIR|TREES|SHOTS|FIXTURES)\b", "결과 폴더를 직접 다룸"),
    (r"\b(QA_(?!STATES=)[A-Z_]+|UI_[A-Z_]+|KEYBOARD|KB_[A-Z_]+|SCREEN_[WH]|OUT|ENGINE|LIB|BUNDLE_ID|APP_PATH|UDID|P_[A-Z_]+)\+?=",
     "엔진 변수에 값을 넣음"),
]


def input_values():
    return list(INPUT_ALIASES)


def engine_functions():
    """엔진 셸 함수 이름(스크립트가 같은 이름으로 다시 정의하면 판정을 바꿀 수 있다)"""
    names = {"check_" + f for f in ("eq", "ne", "gt", "lt", "ge", "le", "contains", "delta_eq")}
    here = Path(__file__).parent
    for f in [here / "core.sh", here / "sim.sh", here / "explore.sh"] + list((here / "driver").glob("*.sh")):
        if f.exists():
            names |= set(re.findall(r"^\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\)", f.read_text(encoding="utf-8"), re.M))
    return names


def norm_item(text):
    return text.replace("\r\n", "\n").strip()


def item_id(text, n, k):
    return hashlib.sha1(norm_item(text).encode()).hexdigest()[:8] + f"#{n}.{k}"


def split_items(cell):
    return [x for x in (cell or "").split(" · ") if x.strip()]


def split_row(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(path):
    path = Path(path)
    return parse_text(path.read_text(encoding="utf-8"), path.name)


def parse_text(text, name):
    lines = text.splitlines()
    case = {"file": name, "id": "", "title": "", "summary": "", "header": {}, "steps": [], "notes": [], "manual": False}
    m = re.match(r"#\s+(QA-M?\d+)\s+(.*)", lines[0] if lines else "")
    if not m:
        raise ValueError(f"{name}: 첫 줄이 '# QA-NN 제목' 형식이 아님")
    case["id"], case["title"] = m.group(1), m.group(2).strip()
    summary, in_table, in_notes, header_done = [], False, False, False
    for line in lines[1:]:
        s = line.strip()
        if s.startswith("## "):
            in_table = False
            in_notes = s[3:].strip().lower() in NOTES_HEADINGS
            continue
        if in_notes:
            if s.startswith("- "):
                case["notes"].append(s[2:].strip())
            elif s:
                case["notes"].append(s)
            continue
        if s.startswith("|"):
            cells = split_row(s)
            if cells and cells[0] in ("#", "") or set("".join(cells)) <= set("-: "):
                in_table = True
                if cells and cells[0] == "#":
                    case["manual"] = len(cells) == 3
                continue
            if in_table and cells and cells[0].isdigit():
                case["steps"].append(make_step(cells, case["manual"]))
            continue
        hm = re.match(r"-\s+([^:：]+)\s*[:：]\s*(.*)", s)
        hkey = hm and HEADER_ALIASES.get(hm.group(1).strip().lower(), hm.group(1).strip())
        if hm and hkey in HEADER_KEYS and not in_table:
            key, val = hkey, hm.group(2).strip()
            case["header"][key] = [v.strip() for v in val.split(",") if v.strip()] if key in LIST_KEYS else val
            header_done = True
            continue
        if s and not header_done and not in_table:
            summary.append(s)
    case["summary"] = " ".join(summary)
    h = case["header"]
    if "실행" in h:
        h["실행"] = RUN_ALIASES.get(h["실행"].lower(), h["실행"])
    case["manual"] = case["manual"] or h.get("실행", "자동") == "수동"
    h.setdefault("실행", "수동" if case["manual"] else "자동")
    h.setdefault("입력", "화면 키보드")
    case["input_mode"] = INPUT_ALIASES.get(h["입력"].lower(), "")
    h.setdefault("조건", ["기본"])
    h.setdefault("화면", [])
    h.setdefault("비교 제외", [])
    h.setdefault("명세", "없음")
    h.setdefault("준비", "")
    return case


def make_step(cells, manual):
    n = int(cells[0])
    action = cells[1] if len(cells) > 1 else ""
    mark = next((m for m in EXTERNAL_MARKS if action.lower().startswith(m)), None)
    external = mark is not None
    if external:
        action = action[len(mark):].strip()
    if manual:
        return {"n": n, "action": action, "external": external, "check": cells[2] if len(cells) > 2 else "", "items": []}
    auto = cells[2] if len(cells) > 2 else ""
    items = [{"id": item_id(t, n, k), "display": f"{n}.{k}", "text": norm_item(t)} for k, t in enumerate(split_items(auto), 1)]
    return {"n": n, "action": action, "external": external, "auto": auto,
            "visual": cells[3] if len(cells) > 3 else "", "items": items}


def all_items(case):
    return [it for s in case["steps"] for it in s["items"]]


def validate(case):
    errs = []
    ns = [s["n"] for s in case["steps"]]
    if ns != list(range(1, len(ns) + 1)):
        errs.append(f"{case['id']}: 단계 번호가 1부터 차례가 아님: {ns}")
    if not case["steps"]:
        errs.append(f"{case['id']}: 단계 표가 없음")
    if len(case["steps"]) > 10:
        errs.append(f"{case['id']}: 단계가 {len(case['steps'])}개. 10개를 넘으면 나눈다")
    for s in case["steps"]:
        if not s["action"]:
            errs.append(f"{case['id']}: {s['n']}단계의 행동이 비어 있음")
    h = case["header"]
    if not case.get("input_mode"):
        errs.append(f"{case['id']}: 입력 '{h['입력']}'은 모르는 값 (가능: {', '.join(input_values())})")
    if h["실행"] not in ("자동", "수동"):
        errs.append(f"{case['id']}: 실행 '{h['실행']}'은 모르는 값 (가능: {', '.join(RUN_ALIASES)})")
    return errs


# ── 스크립트 읽기 ─────────────────────────────────────────

def code_and_comment(line):
    """따옴표 밖의 첫 '#'에서 코드와 주석을 나눈다(셸 $#, ${#…}는 주석이 아님)"""
    q, i = None, 0
    while i < len(line):
        c = line[i]
        if q:
            if c == "\\" and q == '"':
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
        elif c == "#" and (i == 0 or line[i - 1] in " \t;") :
            return line[:i], line[i + 1:]
        i += 1
    return line, ""


def calls_in(code, names):
    """code 안에서 names 중 하나로 시작하는 호출과 그 인자 토큰 목록"""
    out = []
    for m in re.finditer(r"(?<![\w$-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", code):
        rest = code[m.end():]
        lx = shlex.shlex(rest, posix=True, punctuation_chars=";&|")
        lx.whitespace_split = True
        lx.commenters = ""   # 주석은 code_and_comment가 이미 떼었다. 항목 ID의 '#'을 주석으로 읽지 않게
        toks = []
        try:
            for t in lx:
                if t in (";", "&&", "||", "|", "&", ";;") or t in ("}", "fi", "then", "done"):
                    break
                toks.append(t)
        except ValueError:
            toks = rest.split()
        out.append((m.group(1), toks))
    return out


def rule_ref(lines, i):
    """i번째 줄(0부터)이나 바로 윗줄 주석의 '규칙: G번호'"""
    for j in (i, i - 1):
        if j < 0:
            continue
        _, com = code_and_comment(lines[j])
        m = re.search(r"규칙\s*[:：]\s*(G\d+)", com)
        if m and (j == i or not code_and_comment(lines[j])[0].strip()):
            return m.group(1)
    return None


def has_reason(lines, i):
    for j in (i, i - 1):
        if j < 0:
            continue
        code, com = code_and_comment(lines[j])
        if re.search(r"이유\s*[:：]", com) and (j == i or not code.strip()):
            return True
    return False


def read_names(text):
    names = []
    for line in text.splitlines():
        code, _ = code_and_comment(line)
        for _, toks in calls_in(code, ("ui_read",)):
            if toks:
                names.append(toks[0])
    return names


def selector_query(code):
    """후보를 고르는 질의 한 줄에서 (질의 dict(선택 방법 제외), 선택 방법 "first"|"last"|"nth:N")"""
    import argparse
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver"))
    import axtree
    toks = None
    for _, t in calls_in(code, QUERY_CALLS):
        if any(x in ("--first", "--last", "--nth") for x in t):
            toks = t
            break
    if toks is None:
        try:
            toks = shlex.split(code, comments=False)
        except ValueError:
            toks = code.split()
    if not any(t.startswith("--") for t in toks):
        return None, None
    toks = toks[next(i for i, t in enumerate(toks) if t.startswith("--")):]
    nth = None
    if "--nth" in toks:   # 변수로 정한 위치(--nth $i)도 그대로 비교한다
        k = toks.index("--nth")
        nth = toks[k + 1] if k + 1 < len(toks) else ""
        toks = toks[:k] + toks[k + 2:]
    p = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    axtree.add_query_args(p)
    try:
        ns, _ = p.parse_known_args(toks)
    except (argparse.ArgumentError, SystemExit, ValueError):
        return None, None
    q = axtree.query_from_ns(ns)
    sel = "first" if q.pop("first", False) else "last" if q.pop("last", False) else None
    if nth is not None:
        sel = f"nth:{nth}"
    return q, sel


def selector_uses(qa_dir):
    """`# 규칙: G번호`를 단 선택 질의 전부. 범위: steps/<ID>.sh는 그 ID, flows·states는 "*" """
    out = []
    qa = Path(qa_dir)
    files = [(qa / f, "*") for f in ("flows.sh", "states.sh")] + [(p, p.stem) for p in sorted((qa / "steps").glob("*.sh"))]
    for path, scope in files:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            code, _ = code_and_comment(line)
            if not re.search(r"--(first|last|nth)\b", code):
                continue
            gid = rule_ref(lines, i)
            q, sel = selector_query(code)
            out.append({"where": f"{path.name}:{i + 1}", "scope": scope, "rule": gid, "query": q, "selector": sel})
    return out


def shared_checks(qa_dir, text, label, scope="*"):
    """스크립트·flows·states 공통: 선택 규칙, 대체 선택, 금지 어휘, 엔진 함수 재정의, 숫자 좌표, 고정 대기.
    (차단, 경고, 사람 대기)"""
    import approve
    errs, warns, pending = [], [], []
    lines = text.splitlines()
    prev_code = ""
    engine_fns = engine_functions()
    for i, line in enumerate(lines):
        code, com = code_and_comment(line)
        if not code.strip():
            continue
        where = f"{label}:{i + 1}"
        for name in LEGACY:
            if re.search(r"(?<![\w-])" + name + r"(?![\w-])", code):
                errs.append(f"{where}: 옛 어휘 `{name}`(판정 함수·ui_read로 바꾼다)")
        if re.search(r"(?<![\w-])(axe|drv_\w+)(?![\w-])", code) or "xcrun" in code or "simctl" in code:
            errs.append(f"{where}: 실행 도구 직접 호출")
        bare = re.sub(r"'[^']*'", "''", code)   # 작은따옴표 안은 글자 그대로라 검사하지 않는다
        for pat, why in FORBIDDEN:
            m = re.search(pat, bare)
            if m:
                errs.append(f"{where}: 금지 어휘 `{m.group(0).strip()}`({why})")
        # 파일로 내보내기(>, >>). 산술 (( ))·조건 [[ ]] 안의 비교와 /dev/null·다른 출력으로 돌리기(>&)는 허용
        redir = re.sub(r"\(\((?:[^()]|\([^()]*\))*\)\)|\[\[.*?\]\]", "", bare)
        redir = re.sub(r'"(?:[^"\\$`]|\\.)*"', '""', redir)   # 명령 치환이 없는 큰따옴표 문자열 안의 '>'는 글자다
        m = re.search(r"(?<![<>&])\d*>>?(?!&|\s*/dev/null\b)\s*\S+", redir)
        if m:
            errs.append(f"{where}: 금지 어휘 `{m.group(0).strip()}`(파일로 내보냄)")
        fm = re.match(r"\s*(?:function\s+)?([A-Za-z_]\w*)\s*\(\)", code)
        if fm and fm.group(1) in engine_fns:
            errs.append(f"{where}: 엔진 함수 `{fm.group(1)}`를 다시 정의함")
        if re.search(r"(ui_tap_xy|ui_drag)\s+-?\d", code):
            errs.append(f"{where}: 숫자 좌표(화면 크기 비율 px나 요소 질의를 쓴다)")
        if re.search(r"--(first|last|nth)\b", code):
            gid = rule_ref(lines, i)
            if not gid:
                errs.append(f"{where}: 후보를 고르는 질의(--first/--last/--nth)에 승인된 선택 규칙이 없음(`# 규칙: G번호`)")
            else:
                q, sel = selector_query(code)
                if sel is None:
                    errs.append(f"{where}: 선택 질의를 읽지 못함(규칙 {gid}와 맞춰 볼 수 없음)")
                else:
                    level, msg = approve.rule_use_status(qa_dir, gid, scope, q, sel)
                    if level == "block":
                        errs.append(f"{where}: {msg}")
                    elif level == "pending":
                        pending.append(f"{where}: {msg}")
        if re.search(r"ui_(locate|tap|read|wait|find)\b[^|]*\|\|\s*ui_(locate|tap|read|wait|find)\b", code) and not rule_ref(lines, i):
            errs.append(f"{where}: 대체 선택(앞 질의가 실패하면 다른 요소를 고름)에 승인된 규칙이 없음")
        if re.search(r"--any\b", code) and not has_reason(lines, i):
            warns.append(f"{where}: 화면 밖 포함(--any)에 `# 이유:`가 없음")
        if re.match(r"\s*ui_pause\b", code):
            prev_ok = any(re.search(r"(?<![\w-])" + w + r"(?![\w-])", prev_code) for w in WAIT_LIKE)
            if not prev_ok and not has_reason(lines, i):
                errs.append(f"{where}: 근거 없는 고정 대기(ui_pause 앞에 화면 확인이 없음. `# 이유:`를 달거나 대기·확인으로 바꾼다)")
        if not re.match(r"\s*(ui_shot_here|ui_info|ui_note|local)\b", code):   # 기록·선언은 앞 문장을 바꾸지 않는다
            prev_code = code
    return errs, warns, pending


def check_script(case, script_path, qa_dir):
    """실행 전 검사(S4). (차단 목록, 경고 목록, 사람 대기 목록)"""
    import approve
    errs = validate(case)
    warns, pending = [], []
    cid = case["id"]
    text = Path(script_path).read_text(encoding="utf-8")
    lines = text.splitlines()

    marks = [(m.start(), int(m.group(1))) for m in STEP_RE.finditer(text)]
    nums = [n for _, n in marks]
    if len(nums) != len(case["steps"]):
        errs.append(f"{cid}: md {len(case['steps'])}단계, 스크립트 {len(nums)}단계")
    if nums != sorted(nums) or len(set(nums)) != len(nums):
        errs.append(f"{cid}: 스크립트의 step 번호가 차례가 아님: {nums}")
    line_step = {}
    cur = 0
    for i, line in enumerate(lines):
        m = re.match(r"^\s*step\s+(\d+)\b", line)
        if m:
            cur = int(m.group(1))
        line_step[i] = cur

    e2, w2, p2 = shared_checks(qa_dir, text, Path(script_path).name, cid)
    errs += e2
    warns += w2
    pending += p2

    md_items = {it["id"]: (s["n"], it) for s in case["steps"] for it in s["items"]}
    covered = {}
    shared_reads = []
    for f in ("flows.sh", "states.sh"):
        p = Path(qa_dir) / f
        if p.exists():
            shared_reads += read_names(p.read_text(encoding="utf-8"))
    defined = set(shared_reads)
    for i, line in enumerate(lines):
        code, _ = code_and_comment(line)
        for _, toks in calls_in(code, ("ui_read",)):
            if toks:
                defined.add(toks[0])
        for name, toks in calls_in(code, JUDGE_CALLS):
            where = f"{Path(script_path).name}:{i + 1}"
            if not toks or not toks[0].startswith("@"):
                errs.append(f"{where}: `{name}`에 항목(@ID)이 없음")
                continue
            ids = [x for x in toks[0][1:].split(",") if x]
            for x in ids:
                if x not in md_items:
                    errs.append(f"{where}: 각본에 없는 항목 ID @{x}(문구나 단계가 바뀌었으면 각본을 다시 승인하고 ID를 새로 받는다)")
                    continue
                n, it = md_items[x]
                if line_step.get(i) != n:
                    errs.append(f"{where}: @{x}({it['display']})는 {n}단계 항목인데 {line_step.get(i)}단계에 있음")
                covered.setdefault(x, []).append(name)
            if name == "skip":
                if len(toks) < 2 or not toks[1].strip():
                    errs.append(f"{where}: 사유 없는 건너뜀(skip @ID \"사유\")")
                continue
            if name in CHECK_CALLS:
                ops = toks[2:]
                need = CHECK_ARITY.get(name, 2)
                if len(ops) != need:
                    errs.append(f"{where}: `{name}`는 피연산자 {need}개(받은 것 {len(ops)}개)")
                    continue
                reads = [o for o in ops if not o.startswith("=")]
                if not reads:
                    errs.append(f"{where}: 상수만으로 된 판정(화면에서 읽은 값이 없음)")
                for o in reads:
                    if o not in defined:
                        errs.append(f"{where}: 피연산자 `{o}`가 출처 있는 읽기(ui_read)가 아님")
                if len(reads) >= 2 and len(set(reads)) < len(reads):
                    errs.append(f"{where}: 같은 읽기끼리 비교(항상 같은 결과)")
    for x, (n, it) in md_items.items():
        if x not in covered:
            errs.append(f"{cid}: {it['display']} '{it['text']}'를 덮는 판정이 없음(@{x})")

    for s in case["steps"]:
        if s["external"]:
            for it in s["items"]:
                if re.search(r"\d{2,}", it["text"]):
                    warns.append(f"{cid}: [외부] {s['n']}단계 자동 확인 '{it['text']}'에 외부 결과 값이 들어 있을 수 있음")

    md_path = Path(qa_dir) / "cases" / case["file"]
    level, msgs = approve.approval_status(qa_dir, cid, str(md_path), str(script_path))
    {"block": errs, "pending": pending, "ok": warns}[level].extend(msgs)
    for g in approve.gaps_for(qa_dir, cid):
        if g.get("case") == cid and not g.get("answer"):
            (pending if g.get("blocking") else warns).append(f"{cid}: 답 없는 {'blocking ' if g.get('blocking') else ''}질문 {g['id']}: {g['question']}")
    return errs, warns, pending


def gaps_scan(case):
    out = []
    for s in case["steps"]:
        for it in s["items"]:
            if any(v in it["text"] for v in VAGUE):
                out.append({"step": s["n"], "item": it["id"], "text": it["text"], "reason": "unclear-expectation"})
    return out


def evidence_mac(key, line):
    """근거 한 줄의 서명(실행별 키로 HMAC-SHA256). mac 필드는 빼고 정렬한 JSON에 건다"""
    body = json.dumps({k: v for k, v in line.items() if k != "mac"}, ensure_ascii=False, sort_keys=True)
    return hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()


def read_evidence(evidence_path, key=None):
    """(서명이 맞는 줄, 버린 줄 수: 형식 오류·서명 불일치). key가 없으면 서명을 보지 않는다"""
    good, bad = [], 0
    if evidence_path and os.path.exists(evidence_path):
        for l in open(evidence_path, encoding="utf-8"):
            if not l.strip():
                continue
            try:
                e = json.loads(l)
            except json.JSONDecodeError:
                bad += 1
                continue
            if key is not None and not hmac.compare_digest(str(e.get("mac", "")), evidence_mac(key, e)):
                bad += 1
                continue
            good.append(e)
    return good, bad


def coverage(case, evidence_path, key=None):
    lines, bad = read_evidence(evidence_path, key)
    rows = []
    for s in case["steps"]:
        for it in s["items"]:
            ev = [e for e in lines if e.get("item") == it["id"]]
            judged = [e for e in ev if e.get("fn") != "skip"]
            skips = [e for e in ev if e.get("fn") == "skip"]
            if judged:
                res = "fail" if any(e["result"] != "pass" for e in judged) else "pass"
                rows.append(dict(it, step=s["n"], status="executed", result=res, checks=[e["check_id"] for e in judged]))
            elif skips:
                rows.append(dict(it, step=s["n"], status="skipped", reason=skips[-1].get("reason", "")))
            else:
                rows.append(dict(it, step=s["n"], status="not-run"))
    summary = {k: sum(r["status"] == k for r in rows) for k in ("executed", "skipped", "not-run")}
    summary["rejected_lines"] = bad
    return {"case": case["id"], "items": rows, "summary": summary}


def to_env(case):
    out = [f"QA_CASE_ID={shlex.quote(case['id'])}", f"QA_CASE_TITLE={shlex.quote(case['title'])}",
           f"QA_CASE_STATE={shlex.quote(case['header']['준비'])}",
           f"QA_CASE_INPUT={shlex.quote(case['input_mode'])}",
           f"QA_STEP_COUNT={len(case['steps'])}",
           f"QA_ITEMS={shlex.quote(' '.join(it['id'] for it in all_items(case)))}"]
    for s in case["steps"]:
        out.append(f"QA_STEP_ACTION_{s['n']}={shlex.quote(s['action'])}")
        out.append(f"QA_STEP_AUTO_{s['n']}={shlex.quote(s.get('auto', s.get('check', '')))}")
        out.append(f"QA_STEP_EXTERNAL_{s['n']}={1 if s['external'] else 0}")
    return "\n".join(out) + "\n"


def list_cases(folder, condition=None, kind=None, ids=()):
    picked = []
    for p in sorted(Path(folder).glob("QA-*.md")):
        c = parse(p)
        if kind == "auto" and c["manual"]:
            continue
        if kind == "manual" and not c["manual"]:
            continue
        if condition and condition not in c["header"]["조건"]:
            continue
        if ids and not any(c["id"] == i or c["id"].endswith("-" + i) or c["id"] == "QA-" + i for i in ids):
            continue
        picked.append((c["id"], p.name))
    return picked


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "parse":
        c = parse(args[0])
        import approve
        c["hash"] = approve.case_hash(args[0])
        print(json.dumps(c, ensure_ascii=False, indent=1))
    elif cmd == "env":
        print(to_env(parse(args[0])), end="")
    elif cmd == "ids":
        c = parse(args[0])
        for s in c["steps"]:
            for it in s["items"]:
                print(f"{s['n']}단계  @{it['id']}  {it['text']}")
    elif cmd in ("check", "check-shared"):
        import approve
        if cmd == "check":
            errs, warns, pending = check_script(parse(args[0]), args[1], args[2])
        else:
            errs, warns, pending = [], [], []
            for f in ("flows.sh", "states.sh"):
                p = Path(args[0]) / f
                if p.exists():
                    e, w, pn = shared_checks(args[0], p.read_text(encoding="utf-8"), f)
                    errs += e
                    warns += w
                    pending += pn
            problems, diff = approve.gaps_store(args[0]).integrity()
            errs += [f"질문 기록: {x}" for x in problems] + ([f"바뀐 부분:\n{diff}"] if diff else [])
        for e in errs:
            print("차단\t" + e)
        for x in pending:
            print("대기\t" + x)
        for w in warns:
            print("경고\t" + w)
        return 1 if errs else 5 if pending else 0
    elif cmd == "verdict":
        import approve
        s = json.load(open(args[0], encoding="utf-8"))["summary"]
        if args[1] != "0":
            print("fail")
        elif s["not-run"] or s.get("rejected_lines"):
            print("incomplete")
        elif s["skipped"]:
            print("pass" if approve.human_approved(args[2], parse(args[3])["id"], args[3], args[4]) else "skipped")
        else:
            print("pass")
    elif cmd == "uses":
        print(json.dumps(selector_uses(args[0]), ensure_ascii=False, indent=1))
    elif cmd == "gaps-scan":
        print(json.dumps(gaps_scan(parse(args[0])), ensure_ascii=False))
    elif cmd == "coverage":
        case = json.load(open(args[0], encoding="utf-8"))
        cov = coverage(case, args[1], os.environ.get("QA_EVID_KEY"))
        if "--out" in args:
            json.dump(cov, open(args[args.index("--out") + 1], "w"), ensure_ascii=False, indent=1)
        s = cov["summary"]
        print(f"실행됨 {s['executed']} · 건너뜀 {s['skipped']} · 미실행 {s['not-run']}"
              + (f" · 서명이 맞지 않아 버린 근거 {s['rejected_lines']}줄" if s["rejected_lines"] else ""))
        return 0 if s["not-run"] == 0 and not s["rejected_lines"] else 1
    elif cmd == "list":
        folder, condition, kind, ids = args[0], None, None, []
        it = iter(args[1:])
        for a in it:
            if a == "--condition":
                condition = next(it)
            elif a == "--auto":
                kind = "auto"
            elif a == "--manual":
                kind = "manual"
            else:
                ids.append(a)
        for cid, name in list_cases(folder, condition, kind, ids):
            print(f"{cid}\t{name}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
