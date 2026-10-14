#!/usr/bin/env python3
"""herdr-dispatch 표가 아직 맞는지 로컬에서 몇 초 안에 점검한다.

    python3 -I scripts/doctor.py          # 사람이 읽는 출력
    python3 -I scripts/doctor.py --json   # 기계용

결정적으로 확인할 수 있는 것만 본다 — 설치된 CLI의 도움말, codex 모델 캐시, 전역 설정,
herdr 상태, 문서의 확인일. 공식 문서 대조와 벤더별 pane 교차 확인은 references/verify.md의
사람·에이전트 몫이다. 종료 코드: FAIL이 하나라도 있으면 1.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
REFS = SKILL / "references"
HOME = Path.home()
TODAY = date.today()

results: list[tuple[str, str, str]] = []  # (level, area, message)


def ok(area, msg):
    results.append(("OK", area, msg))


def warn(area, msg):
    results.append(("WARN", area, msg))


def fail(area, msg):
    results.append(("FAIL", area, msg))


def run(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""


def read(p: Path) -> str:
    return p.read_text() if p.exists() else ""


# ---------------------------------------------------------------- herdr
def check_herdr():
    area = "herdr"
    if os.environ.get("HERDR_ENV") != "1":
        warn(area, "HERDR_ENV != 1 — herdr pane 밖이다. pane 교차 확인은 못 한다")
    rc, out = run(["herdr", "--version"])
    if rc != 0:
        fail(area, "herdr 바이너리를 못 찾음")
        return
    ver = out.strip().split()[-1]
    ok(area, f"herdr {ver}")

    rc, status = run(["herdr", "status"])
    if rc == 0:
        for key in ("restart_needed", "server_binary_stale"):
            m = re.search(rf"{key}:\s*(\w+)", status)
            if m and m.group(1) != "no":
                warn(area, f"herdr status: {key}={m.group(1)} — 서버 재시작이 필요하다")
        m = re.search(r"endpoint_compatible:\s*(\w+)", status)
        if m and m.group(1) != "yes":
            fail(area, "herdr status: 클라이언트와 서버가 호환되지 않음")
    else:
        warn(area, "herdr status 실패 — 서버가 안 떠 있나")

    # 이 스킬이 쓰는 CLI 문법이 도움말에 그대로 있는가
    _, agent_help = run(["herdr", "agent"])
    _, pane_help = run(["herdr", "pane"])
    need = {
        "agent start -- 통과": (agent_help, r"agent start .*\[-- <agent-args\.\.\.>\]"),
        "kinds에 claude": (agent_help, r"kinds:.*\bclaude\b"),
        "kinds에 codex": (agent_help, r"kinds:.*\bcodex\b"),
        "agent prompt --wait --timeout": (agent_help, r"agent prompt .*--wait.*--timeout"),
        "agent read --source recent-unwrapped": (agent_help, r"agent read .*recent-unwrapped"),
        "pane split --cwd --no-focus": (pane_help, r"pane split .*--cwd.*--no-focus"),
        "pane run": (pane_help, r"pane run <pane_id>"),
    }
    missing = [k for k, (text, pat) in need.items() if not re.search(pat, text)]
    if missing:
        fail(area, "도움말에서 사라진 문법: " + ", ".join(missing))
    else:
        ok(area, "이 스킬이 쓰는 agent/pane 문법 전부 있음")

    # 공식 스킬 동기화
    dest = HOME / ".agents/skills/herdr/SKILL.md"
    rc, latest = run(["herdr", "--skill"])
    if rc == 0 and dest.exists():
        if latest.strip() != dest.read_text().strip():
            warn(area, "herdr --skill 과 ~/.agents/skills/herdr/SKILL.md 가 다름 — herdr-setup/sync-skill.sh")
        else:
            ok(area, "herdr 공식 스킬 동기화됨")
    else:
        warn(area, "herdr 공식 스킬 파일이 없거나 --skill 실패")

    # 최신 릴리스 (네트워크, gh 있을 때만)
    rc, tag = run(["gh", "api", "repos/herdrdev/herdr/releases/latest", "-q", ".tag_name"], timeout=20)
    if rc == 0 and tag.strip():
        latest_ver = tag.strip().lstrip("v")
        if latest_ver != ver:
            warn(area, f"GitHub 최신 안정판 {latest_ver} ≠ 설치본 {ver} — 릴리스 노트를 읽고 `herdr update`를 제안")
        else:
            ok(area, f"설치본이 최신 안정판 ({latest_ver})")
    else:
        warn(area, "GitHub 릴리스 조회 실패 (gh 없음 또는 오프라인) — 수동 확인")


# ---------------------------------------------------------------- claude
def check_claude():
    area = "claude"
    rc, out = run(["claude", "--version"])
    if rc != 0:
        fail(area, "claude 바이너리를 못 찾음")
        return
    ok(area, f"claude {out.strip()}")
    _, h = run(["claude", "--help"])
    h = re.sub(r"\s+", " ", h)
    for name, pat in {
        "--permission-mode auto": r"--permission-mode .*?\"auto\"",
        "--effort xhigh": r"--effort .*?xhigh",
        "--model 별칭": r"--model <model>.*?alias",
        "--disallowedTools": r"--disallowedTools",
    }.items():
        if not re.search(pat, h):
            fail(area, f"도움말에 없음: {name}")
    doc = read(REFS / "claude-cli.md")
    m = re.search(r"Claude Code (\d+\.\d+\.\d+)", doc)
    if m and m.group(1) != out.strip().split()[0]:
        warn(area, f"claude-cli.md 는 {m.group(1)} 기준, 설치본은 {out.strip().split()[0]} — effort 기본값·별칭 해석이 바뀌었을 수 있다")


# ---------------------------------------------------------------- codex
def check_codex():
    area = "codex"
    rc, out = run(["codex", "--version"])
    if rc != 0:
        fail(area, "codex 바이너리를 못 찾음")
        return
    ver = out.strip().split()[-1]
    ok(area, f"codex {ver}")
    _, h = run(["codex", "--help"])
    for flag in ("--approve-for-me", "--sandbox", "--ask-for-approval"):
        if flag not in h:
            fail(area, f"도움말에 없음: {flag}")

    doc = read(REFS / "codex-cli.md")
    m = re.search(r"codex-cli (\d+\.\d+\.\d+)", doc)
    if m and m.group(1) != ver:
        warn(area, f"codex-cli.md 는 {m.group(1)} 기준, 설치본은 {ver}")

    # 모델 캐시 vs 역할표
    cache_p = HOME / ".codex/models_cache.json"
    if not cache_p.exists():
        warn(area, "~/.codex/models_cache.json 없음 — codex를 한 번 실행하면 생긴다")
        return
    cache = json.loads(cache_p.read_text())
    models = {m["slug"]: m for m in cache["models"]}
    listed = {s for s, m in models.items() if m.get("visibility") == "list"}

    roles = read(REFS / "roles.md")
    used = set(re.findall(r"`(gpt-[0-9.]+(?:-[a-z]+)?)`", roles))
    used |= set(re.findall(r"-m (gpt-[0-9.]+(?:-[a-z]+)?)", doc + read(REFS / "verify.md")))
    gone = sorted(u for u in used if u not in models)
    hidden = sorted(u for u in used if u in models and u not in listed)
    if gone:
        fail(area, f"역할표/예시에 있지만 캐시에 없는 모델: {', '.join(gone)} — agent start 가 실패한다")
    if hidden:
        warn(area, f"역할표/예시 모델이 선택기에서 숨김 상태(은퇴 임박): {', '.join(hidden)}")
    if not gone and not hidden:
        ok(area, f"역할표/예시 모델 {len(used)}개 전부 캐시에 노출됨")

    # 캐시에 있는데 문서 모델 표에 없는 새 모델
    documented = set(re.findall(r"`(gpt-[0-9.]+(?:-[a-z]+)?)`", doc))
    new = sorted(s for s in listed if s.startswith("gpt-") and s not in documented)
    if new:
        warn(area, f"캐시에 새로 보이는 모델 (codex-cli.md 표에 없음): {', '.join(new)}")

    # 문서가 적은 추론 단계·기본값이 캐시와 같은가 (역할표 모델만)
    for slug in sorted(used & set(models)):
        levels = [l["effort"] for l in models[slug].get("supported_reasoning_levels", [])]
        row = re.search(rf"\| `{re.escape(slug)}`[^\n]*\|\s*`low`~`(\w+)`[^\n]*\(`(\w+)`\)", doc)
        if row:
            top, default = row.groups()
            if levels and levels[-1] != top:
                warn(area, f"{slug}: 문서 최고 단계 {top} ≠ 캐시 {levels[-1]}")
            if models[slug].get("default_reasoning_level") != default:
                warn(area, f"{slug}: 문서 기본값 {default} ≠ 캐시 {models[slug].get('default_reasoning_level')}")

    # 은퇴일
    for mm in re.finditer(r"\| (`[^|]+`) \|[^\n]*\*\*(\d{4}-\d{2}-\d{2})\*\*", doc):
        names, d = mm.group(1), date.fromisoformat(mm.group(2))
        days = (d - TODAY).days
        touches_roles = any(n.strip("` ") in used for n in names.split(","))
        msg = f"{names} 은퇴 {d} ({'지남' if days < 0 else f'{days}일 남음'})"
        if touches_roles and days <= 30:
            fail(area, msg + " — 역할표에서 빼야 한다")
        elif days <= 14:
            warn(area, msg)

    # 전역 설정이 켜 둔 함정
    cfg = read(HOME / ".codex/config.toml")
    if re.search(r'^service_tier\s*=\s*"', cfg, re.M):
        ok(area, "config.toml 에 service_tier 있음 → -c features.fast_mode=false 필수 (문서대로)")
    else:
        warn(area, "config.toml 에 service_tier 없음 — fast 설명(codex-cli.md)이 더는 맞지 않을 수 있다")
    if 'approvals_reviewer = "auto_review"' in cfg:
        ok(area, "config.toml 에 auto_review 켜짐 → 읽기 전용에 -a never 필수 (문서대로)")
    else:
        warn(area, "config.toml 에 auto_review 없음 — -a never 경고의 전제가 바뀌었다")
    if re.search(r'approval_policy\s*=\s*"(untrusted|on-failure)"', cfg):
        fail(area, "config.toml 의 approval_policy 가 폐기된 값 — codex 가 시작을 거부할 수 있다")


# ---------------------------------------------------------------- 문서 나이
def check_docs():
    area = "docs"
    for f in ("roles.md", "claude-cli.md", "codex-cli.md"):
        m = re.search(r"확인일: (\d{4}-\d{2}-\d{2})", read(REFS / f))
        if not m:
            warn(area, f"{f}: 확인일 없음")
            continue
        age = (TODAY - date.fromisoformat(m.group(1))).days
        (warn if age > 60 else ok)(area, f"{f}: 확인일 {m.group(1)} ({age}일 전)")

    # claude 읽기 전용이 plan 모드로 되돌아갔나 (2026-10-14 사고). 백틱으로 인용한 설명은 제외
    for f in (SKILL / "SKILL.md", *REFS.glob("*.md")):
        if re.search(r"(?<!`)--permission-mode[ =][\"']?plan\b", read(f)):
            fail(area, f"{f.name}: claude를 --permission-mode plan 으로 띄우는 예시 — 읽기 전용은 auto + --disallowedTools")


def main():
    check_herdr()
    check_claude()
    check_codex()
    check_docs()
    if "--json" in sys.argv:
        print(json.dumps([{"level": l, "area": a, "message": m} for l, a, m in results], ensure_ascii=False, indent=1))
    else:
        width = max(len(a) for _, a, _ in results)
        for level, area, msg in results:
            print(f"{level:<4} {area:<{width}}  {msg}")
        n = {k: sum(1 for l, _, _ in results if l == k) for k in ("OK", "WARN", "FAIL")}
        print(f"\n{n['OK']} ok · {n['WARN']} warn · {n['FAIL']} fail · {datetime.now():%Y-%m-%d %H:%M}")
        print("WARN/FAIL 이 있으면 references/verify.md 로 간다. 이 스크립트는 공식 문서와 pane 교차 확인을 대신하지 않는다.")
    sys.exit(1 if any(l == "FAIL" for l, _, _ in results) else 0)


if __name__ == "__main__":
    main()
