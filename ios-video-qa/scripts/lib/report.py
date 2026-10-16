"""실행 결과 폴더를 읽어 index.html과 REPORT.md를 만든다.

    report.py <results/시각-조건>

실행이 사람 승인 전(QA_ALLOW_UNAPPROVED=1)이었으면 맨 위에 크게 표시하고, 각본마다 "사람 승인 전"을 붙인다.
각본 카드마다: 승인 상태, 실행 대조(실행됨/건너뜀·사유/미실행), 승인본과 달라진 스크립트(diff), 영상,
단계별로 행동 · 항목별 판정(결과·근거 사진) · 눈으로 확인 · 단계 사진 · ⚠ 노트.
근거 사진은 원본을 그대로 두고, 확인한 요소에 상자를 그린 사본(-box.png)을 따로 만든다.
사용자용 문구와 개발자 상세(실패 상세·소스 위치·탭 좌표·질의)는 나눈다. 개발자 상세는 접힌 영역에만.
"""

import html
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

run = Path(sys.argv[1])
meta = json.loads((run / "run.json").read_text()) if (run / "run.json").exists() else {}
approvals = json.loads((run / "approvals.json").read_text()) if (run / "approvals.json").exists() else {}
verify = json.loads((run / "verify.json").read_text()) if (run / "verify.json").exists() else None
metrics = json.loads((run / "metrics.json").read_text()) if (run / "metrics.json").exists() else None
KB = {"software": "화면 키보드", "hardware": "블루투스 키보드", "none": "입력 없음"}
STATUS = {"pass": ("PASS", "pass"), "fail": ("FAIL", "fail"), "incomplete": ("불완전", "fail"), "skipped": ("건너뜀 있음", "fail")}
E = html.escape
UNAPPROVED = meta.get("unapproved") == "1"
PENDING = [x for x in (meta.get("pending") or "").splitlines() if x.strip()]
SHARED_PENDING = any(x.startswith(("flows.sh:", "states.sh:")) for x in PENDING)
BROKEN = []   # 읽지 못한 기록 줄(조용히 버리지 않고 보고서에 남긴다)


def jload(p, default):
    try:
        return json.loads(p.read_text()) if p.exists() else default
    except json.JSONDecodeError:
        return default


def jlines(p):
    out = []
    if p.exists():
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                BROKEN.append(f"{p.parent.name}/{p.name}:{i}")
    return out


def boxed(d, ev):
    """근거 사진에 확인한 요소의 상자를 그린 사본. 원본은 그대로 둔다"""
    shot = ev.get("shot")
    if not shot or not shutil.which("ffmpeg"):
        return None
    src = d / shot
    dst = src.with_name(src.stem + "-box.png")
    if dst.exists():
        return str(dst.relative_to(run))
    boxes = []
    for inp in ev.get("inputs") or []:
        r = inp.get("read") or {}
        if r.get("frame") and r.get("screen"):
            boxes.append((r["frame"], r["screen"]))
    if not boxes or not src.exists():
        return None
    try:
        w = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width",
                                "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip())
    except ValueError:
        return None
    color = "0x12a150" if ev.get("result") == "pass" else "0xd93a3a"
    filters = []
    for (x, y, bw, bh), scr in boxes:
        k = w / scr[2]
        filters.append(f"drawbox=x={int(x * k)}:y={int(y * k)}:w={max(int(bw * k), 4)}:h={max(int(bh * k), 4)}:color={color}@0.95:t={max(int(3 * k), 3)}")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", ",".join(filters), str(dst)])
    return str(dst.relative_to(run)) if r.returncode == 0 else None


def diagnose(fj, fail_step):
    if not fj:
        return ""
    kind, phase = fj.get("kind"), fj.get("phase")
    if phase == "prep":
        return "준비 실패(환경). 각본이 시작되기 전 준비 상태를 만들지 못함. 다시 실행해 보세요"
    if kind == "gap":
        return "질문 대기. 같은 조건의 화면 요소가 여럿이라 사람이 어느 것인지 정해야 함(qa status로 질문 확인)"
    if kind == "env":
        return "환경 문제(화면 정보 읽기·도구 오류). 다시 실행해 보세요"
    if kind == "script":
        return "스크립트 문제(비교할 값을 읽지 못했거나 식이 잘못됨). 앱 버그가 아니라 스크립트를 고칠 차례"
    if kind == "undecidable":
        return "판정 불가(화면 정보에 영역·활성 같은 속성이 없음). 사람이 단계 사진으로 판단"
    if fail_step and fail_step.get("external"):
        return "환경 문제로 추정(외부 API에 좌우되는 단계). 다시 실행해 보세요"
    return "앱 버그 또는 각본이 낡음. 실패 화면을 보고 판단하세요"


cases = []
for d in sorted(p for p in run.iterdir() if p.is_dir() and not p.name.startswith("_")):
    case = jload(d / "case.json", None)
    if not case:
        continue
    result = jload(d / "result.json", {"status": "fail", "seconds": 0, "keyboard": "software"})
    events = jlines(d / "events.jsonl")
    evidence = jlines(d / "evidence.jsonl")
    cov = jload(d / "coverage.json", {"items": [], "summary": {}})
    fj = jload(d / "failure.json", None)
    covmap = {r["id"]: r for r in cov.get("items", [])}
    steps = []
    for s in case["steps"]:
        n = s["n"]
        ev = [e for e in events if int(e.get("step", 0)) == n]
        started = next((e for e in ev if e["kind"] == "step"), None)
        items = []
        for it in s.get("items", []):
            lines = [e for e in evidence if e.get("item") == it["id"]]
            rows = []
            for e in lines:
                rows.append(dict(e, boxed=boxed(d, e) if e.get("fn") != "skip" else None))
            items.append(dict(it, cov=covmap.get(it["id"], {"status": "not-run"}), evidence=rows))
        steps.append(dict(s, started=started is not None, t=float(started["t"]) if started else None, items=items,
                          notes=[(e["text"], e.get("dev", "")) for e in ev if e["kind"] == "note"],
                          infos=[e["text"] for e in ev if e["kind"] == "info"],
                          taps=[e for e in ev if e["kind"] == "tap" and not e.get("key")],
                          failed=bool(fj) and fj.get("step") == n and fj.get("phase") == "scenario",
                          shot=f"{d.name}/steps/{n}.png" if (d / "steps" / f"{n}.png").exists() else None))
    fail_step = next((s for s in steps if s["failed"]), None)
    appr = dict(approvals.get(case["id"], {}))
    cid = case["id"]
    appr["pending"] = (appr.get("via") not in ("tty", "page") or SHARED_PENDING
                       or any(x.startswith((cid + ":", cid + ".sh:")) for x in PENDING))
    sdiff = (d / "script.diff").read_text() if (d / "script.diff").exists() else ""
    cases.append(dict(name=d.name, case=case, result=result, steps=steps, fj=fj, cov=cov.get("summary", {}),
                      diagnosis=diagnose(fj, fail_step), approval=appr,
                      prep_notes=[(e["text"], e.get("dev", "")) for e in events if e["kind"] == "note" and int(e.get("step", 0)) == 0],
                      notes=[(e["text"], e.get("dev", "")) for e in events if e["kind"] == "note"],
                      video=(d / "video.mp4").exists(), has_tree=(d / "failure-tree.txt").exists(), script_diff=sdiff,
                      verify=(verify or {}).get("cases", {}).get(case["id"])))

passed = sum(c["result"]["status"] == "pass" for c in cases)
noted = sum(bool(c["notes"]) for c in cases)
boot = [c["case"]["id"] for c in cases if c["approval"].get("pending")]
title = f"{meta.get('condition', '')} · {meta.get('device', '')}".strip(" ·")
COV = {"executed": "실행됨", "skipped": "건너뜀", "not-run": "미실행"}


def item_mark(it):
    c = it["cov"]
    if c["status"] == "skipped":
        return "↷", "skip", f"건너뜀: {c.get('reason', '')}"
    if c["status"] == "not-run":
        return "·", "notrun", "미실행"
    return ("✓", "ok", "통과") if c.get("result") == "pass" else ("✗", "bad", "실패")


# ── Markdown ──
md = [f"# 영상 QA 결과 · {run.name}", "", f"{title} · 통과 {passed} / {len(cases)} · ⚠ 있는 각본 {noted}"]
if UNAPPROVED:
    md += ["", "> **⚠ 사람 승인 전 실행(QA_ALLOW_UNAPPROVED=1). 판정이 모두 통과해도 이 결과는 통과가 아니다.**"]
if boot:
    md += ["", f"> 사람 승인 전 각본: {', '.join(boot)}. 결과는 임시 기준으로 낸 것이다."]
if BROKEN:
    md += ["", f"> ⚠ 읽지 못한 기록 줄 {len(BROKEN)}개: {', '.join(BROKEN[:5])}"]
if meta.get("warning"):
    md += ["", f"> ⚠ {meta['warning']}"]
md += ["", "| 각본 | 결과 | 항목(실행됨/건너뜀/미실행) | 시간 | 입력 | 승인 |", "|---|---|---|---|---|---|"]
for c in cases:
    st = STATUS.get(c["result"]["status"], ("?", ""))[0]
    s = c["cov"]
    md.append(f"| {c['case']['id']} {c['case']['title']} | {st}{' ⚠' if c['notes'] else ''} | {s.get('executed', 0)}/{s.get('skipped', 0)}/{s.get('not-run', 0)} | "
              f"{c['result']['seconds']}s | {KB.get(c['result']['keyboard'])} | {'사람 승인 전' if c['approval'].get('pending') else '승인 v' + str(c['approval'].get('version'))} |")
for c in cases:
    md += ["", f"## {c['case']['id']} {c['case']['title']}", "", c["case"]["summary"], ""]
    if c["fj"]:
        where = "준비" if c["fj"].get("phase") == "prep" else f"{c['fj'].get('step')}단계"
        md += [f"**실패({where}):** {c['fj']['text']}", "", f"진단: {c['diagnosis']}", ""]
    md += ["| # | 행동 | 확인 항목 | 결과 | 눈으로 확인 |", "|---|---|---|---|---|"]
    for s in c["steps"]:
        its = "<br>".join(f"{i['display']} {i['text']}" for i in s["items"]) or ""
        res = "<br>".join(item_mark(i)[2] for i in s["items"]) or ("✓" if s["started"] else "·")
        md.append(f"| {s['n']} | {'[외부] ' if s['external'] else ''}{s['action']} | {its} | {res} | {s['visual']} |")
    for text, dev in c["notes"]:
        md += ["", f"> ⚠ {text}"]
    if c["script_diff"]:
        md += ["", "승인본과 달라진 스크립트:", "", "```diff", c["script_diff"].rstrip(), "```"]
    md += ["", f"- 영상: `{c['name']}/video.mp4`"]
if verify:
    v = verify["summary"]
    md += ["", "## 판정 기록 재현 검증", "", f"검증됨 {v['verified']} · 검증 불가 {v['unverifiable']} · 변형 부적합 {v['unfit']} · "
           f"건너뜀 {v.get('skipped', 0)} · 미실행 {v.get('not_run', 0)} · 판정 결함 {v['defect']} · 검증 불가 비율 {v['unverifiable_ratio']:.0%}"]
    for w in verify.get("warnings", []):
        md.append(f"- ⚠ {w}")
    for b in verify.get("blocking", []):
        md.append(f"- ✗ {b}")
(run / "REPORT.md").write_text("\n".join(md) + "\n")


# ── HTML ──
def evidence_html(i):
    out = []
    for e in i["evidence"]:
        if e.get("fn") == "skip":
            continue
        img = e.get("boxed") or (f"{e['_case']}/{e['shot']}" if e.get("shot") else None)
        orig = f"{e['_case']}/{e['shot']}" if e.get("shot") else None
        link = f' <a href="{img}" target="_blank">근거</a>' if img else ""
        if orig and img != orig:
            link += f' <a href="{orig}" target="_blank" class="muted">원본</a>'
        out.append(f'<span class="ev">{E(e.get("desc") or "")}{link}</span>')
    return " · ".join(out)


def step_row(c, s):
    cls = "fail" if s["failed"] else "done" if s["started"] else "skip"
    tbtn = (f'<button data-video="v-{c["name"]}" data-t="{s["t"]:.1f}">{s["t"]:.1f}s</button>'
            if s["t"] is not None and s["t"] >= 0 else '<span class="nt">—</span>')
    lis = []
    for i in s["items"]:
        for e in i["evidence"]:
            e["_case"] = c["name"]
        mark, kls, label = item_mark(i)
        ev = evidence_html(i)
        lis.append(f'<li class="{kls}"><span class="iid">{E(i["display"])}</span> {mark} {E(i["text"])}'
                   f'{" — " + E(label) if kls in ("skip", "notrun") else ""}{"<br><small>" + ev + "</small>" if ev else ""}</li>')
    lis += [f'<li class="info">· {E(x)}</li>' for x in s["infos"]]
    lis += [f'<li class="note">⚠ {E(t)}</li>' for t, _ in s["notes"]]
    if s["failed"]:
        lis.append(f'<li class="bad">✗ {E(c["fj"]["text"])}</li>')
    dev = [f"탭 ({int(float(e['x']))},{int(float(e['y']))}) {float(e['t']):.1f}s {e.get('what', '')}" for e in s["taps"]]
    dev += [f"⚠ 상세: {d}" for _, d in s["notes"] if d]
    for i in s["items"]:
        for e in i["evidence"]:
            if e.get("fn") != "skip":
                dev.append(f"{e['check_id']} {e['fn']} → {e['result']}: {e.get('reason', '')}")
    if s["failed"] and c["fj"].get("dev"):
        dev.append("실패 상세: " + c["fj"]["dev"])
    devblock = f'<details class="dev"><summary>개발자 상세</summary><pre>{E(chr(10).join(dev))}</pre></details>' if dev else ""
    shot = f'<a href="{s["shot"]}" target="_blank"><img src="{s["shot"]}" loading="lazy" alt="{s["n"]}단계 화면"></a>' if s["shot"] else '<div class="noshot">—</div>'
    ext = '<span class="ext">외부</span>' if s["external"] else ""
    return f"""<tr class="{cls}">
  <td class="n">{s['n']}<br>{tbtn}</td>
  <td class="shot">{shot}</td>
  <td class="act">{ext}{E(s['action'])}</td>
  <td class="auto"><ul>{''.join(lis)}</ul>{devblock}</td>
  <td class="vis">{E(s['visual'])}</td>
</tr>"""


cards = []
for c in cases:
    label, kls = STATUS.get(c["result"]["status"], ("?", "fail"))
    k = c["result"]["keyboard"]
    media = (f'<video id="v-{c["name"]}" src="{c["name"]}/video.mp4" controls muted playsinline preload="metadata"></video>'
             if c["video"] else '<div class="novideo">영상 없음</div>')
    h = c["case"]["header"]
    err = ""
    if c["fj"]:
        links = f' · <a href="{c["name"]}/failure.png" target="_blank">실패 화면</a>'
        if c["has_tree"]:
            links += f' · <a href="{c["name"]}/failure-tree.txt" target="_blank">그때의 화면 정보</a>'
        where = "준비 단계(녹화 전)에서 실패" if c["fj"].get("phase") == "prep" else f"{c['fj'].get('step')}단계에서 실패"
        err = f'<p class="err">{where} · {E(c["fj"]["text"])} · {E(c["diagnosis"])}{links}</p>'
        if c["fj"].get("dev"):
            err += f'<details class="dev"><summary>개발자 상세</summary><pre>{E(c["fj"]["dev"])}</pre></details>'
    s = c["cov"]
    covline = (f'<p class="cov">확인 항목: 실행됨 <b>{s.get("executed", 0)}</b> · 건너뜀 <b>{s.get("skipped", 0)}</b> · '
               f'미실행 <b class="{"bad" if s.get("not-run") else ""}">{s.get("not-run", 0)}</b>'
               + (f' · 서명이 맞지 않아 버린 근거 <b class="bad">{s["rejected_lines"]}</b>줄' if s.get("rejected_lines") else "")
               + (" — 미실행 항목이 있어 통과로 세지 않음" if c["result"]["status"] == "incomplete" else "")
               + (" — 건너뛴 항목이 있어 통과로 세지 않음(사람이 승인한 스크립트의 건너뜀만 통과로 센다)" if c["result"]["status"] == "skipped" else "")
               + "</p>")
    appr = c["approval"]
    abadge = ('<span class="badge boot">사람 승인 전</span>' if appr.get("pending")
              else f'<span class="badge ok2">승인 v{appr.get("version")} · {E(appr.get("approved_by", ""))}</span>')
    vbadge = ""
    if c["verify"]:
        vs = c["verify"]["summary"]
        vbadge = (f'<span class="badge {"warn" if vs["defect"] else "ok2"}">재현 검증: 검증됨 {vs["verified"]} · 불가 {vs["unverifiable"]}'
                  f'{" · 결함 " + str(vs["defect"]) if vs["defect"] else ""}</span>')
    prep = "".join(f'<li>⚠ {E(t)}</li>' for t, _ in c["prep_notes"])
    cards.append(f"""
<section class="card {kls}" id="{c['name']}">
  <div class="head"><span class="badge st">{label}</span>{'<span class="badge warn">⚠ ' + str(len(c["notes"])) + '</span>' if c["notes"] else ''}
    {abadge}{vbadge}<span class="badge kb">⌨ {KB.get(k, k)}</span><code>{c['case']['id']}</code><span class="meta">명세 {E(h.get('명세', '없음'))} · 준비 {E(h.get('준비', ''))}{(' · 화면 ' + E(', '.join(h.get('화면') or []))) if h.get('화면') else ''}{(' · 비교 제외 ' + E(', '.join(h.get('비교 제외') or []))) if h.get('비교 제외') else ''}</span><span class="time">{c['result']['seconds']}s</span></div>
  <h2>{E(c['case']['title'])}</h2>
  <p class="goal">{E(c['case']['summary'])}</p>
  {err}{covline}
  {('<details class="dev" open><summary>승인본과 달라진 스크립트</summary><pre>' + E(c['script_diff']) + '</pre></details>') if c['script_diff'] else ''}
  {f'<ul class="notes">{prep}</ul>' if prep else ''}
  <div class="body">
    <div class="media">{media}</div>
    <table class="steps"><thead><tr><th>#</th><th>화면</th><th>행동</th><th>확인 항목</th><th>눈으로 확인</th></tr></thead>
    <tbody>{''.join(step_row(c, s) for s in c['steps'])}</tbody></table>
  </div>
  {('<details class="memo"><summary>메모</summary><ul>' + ''.join(f'<li>{E(n)}</li>' for n in c['case']['notes']) + '</ul></details>') if c['case']['notes'] else ''}
</section>""")

vsec = ""
if verify:
    v = verify["summary"]
    lim = verify.get("limits") or {"case": 0.3, "run": 0.2}
    vsec = (f'<section class="card"><h2>판정 기록 재현 검증</h2><p>검증됨 <b>{v["verified"]}</b> · 검증 불가 <b>{v["unverifiable"]}</b> · '
            f'변형 부적합 <b>{v["unfit"]}</b> · 건너뜀 <b>{v.get("skipped", 0)}</b> · 미실행 <b>{v.get("not_run", 0)}</b> · '
            f'판정 결함 <b>{v["defect"]}</b> · 검증 불가 비율 <b>{v["unverifiable_ratio"]:.0%}</b> '
            f'(상한: 각본별 {lim["case"]:.0%}, 전체 {lim["run"]:.0%})</p>'
            + "".join(f'<p class="warn-line">⚠ {E(w)}</p>' for w in verify.get("warnings", []))
            + "".join(f'<p class="err">✗ {E(b)}</p>' for b in verify.get("blocking", []))
            + "</section>")
msec = ""
if metrics:
    m = metrics["summary"]
    msec = (f'<details class="card dev"><summary>근거 저장 비용</summary><pre>{E(json.dumps(metrics, ensure_ascii=False, indent=1))}</pre></details>')

toc = "".join(f'<a href="#{c["name"]}" class="{STATUS.get(c["result"]["status"], ("", "fail"))[1]}">● {E(c["case"]["id"])} {E(c["case"]["title"])}</a>' for c in cases)
bootline = f'<p class="warn-line">사람 승인 전 각본 {len(boot)}개: {E(", ".join(boot))}. 결과는 임시 기준으로 낸 것이다.</p>' if boot else ""
if UNAPPROVED:
    bootline = ('<div class="unapproved"><b>⚠ 사람 승인 전 실행</b><br>QA_ALLOW_UNAPPROVED=1로 돌린 엔진 시험 결과다. '
                '판정이 모두 통과해도 이 결과는 통과가 아니다. 사람이 각본·스크립트·선택 규칙을 승인한 뒤 다시 실행한다.'
                + (f'<details><summary>승인 대기 {len(PENDING)}곳</summary><pre>{E(chr(10).join(PENDING))}</pre></details>' if PENDING else '')
                + '</div>' + bootline)
if BROKEN:
    bootline += f'<p class="warn-line">⚠ 읽지 못한 기록 줄 {len(BROKEN)}개: {E(", ".join(BROKEN[:5]))}</p>'

page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>영상 QA 결과</title>
<style>
:root {{ --bg:#f6f7f5; --card:#fff; --ink:#1c1f1d; --muted:#6b726d; --line:#e3e6e3; --pass:#12a150; --fail:#d93a3a; --warn:#c27c0e; --accent:#14c27a; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121413; --card:#1b1e1c; --ink:#e8ebe9; --muted:#9aa29d; --line:#2b302d; }} }}
:root[data-theme="dark"] {{ --bg:#121413; --card:#1b1e1c; --ink:#e8ebe9; --muted:#9aa29d; --line:#2b302d; }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system, "Apple SD Gothic Neo", sans-serif; }}
header {{ padding:28px 16px 8px; max-width:1240px; margin:auto }}
h1 {{ margin:0 0 4px; font-size:24px }}
.summary {{ color:var(--muted) }} .summary b {{ color:var(--ink) }}
nav {{ display:flex; flex-wrap:wrap; gap:6px 14px; margin:14px 0 0 }}
nav a {{ color:var(--ink); text-decoration:none; font-size:14px }} nav a::first-letter {{ color:var(--pass) }} nav a.fail {{ color:var(--fail) }}
main {{ max-width:1240px; margin:auto; padding:8px 16px 48px; display:grid; gap:18px }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:16px; padding:18px 20px; overflow:hidden }}
.card.fail {{ border-color:var(--fail) }}
.head {{ display:flex; gap:8px; align-items:center; font-size:13px; color:var(--muted); flex-wrap:wrap }}
.badge {{ font-weight:700; color:#fff; background:var(--pass); border-radius:6px; padding:1px 7px; font-size:12px }}
.fail .badge.st {{ background:var(--fail) }} .badge.warn {{ background:var(--warn) }} .badge.kb {{ background:#5b6b9e; font-weight:600 }}
.badge.boot {{ background:#8a5cc2 }} .badge.ok2 {{ background:#3d7f63; font-weight:600 }}
.time {{ margin-left:auto }}
h2 {{ margin:6px 0 2px; font-size:19px }} .goal {{ margin:0 0 10px; color:var(--muted) }}
.err {{ color:var(--fail); font-weight:600 }} .err a {{ color:var(--fail) }}
.cov {{ margin:0 0 10px; font-size:13px; color:var(--muted) }} .cov b {{ color:var(--ink) }} .cov b.bad {{ color:var(--fail) }}
.warn-line {{ color:var(--warn); font-weight:600 }}
.unapproved {{ margin:12px 0; padding:14px 16px; border:3px solid #8a5cc2; border-radius:12px; background:color-mix(in srgb, #8a5cc2 10%, transparent); font-size:16px }}
.unapproved b {{ font-size:20px; color:#8a5cc2 }} .unapproved pre {{ white-space:pre-wrap; font-size:12px }}
.notes {{ margin:0 0 10px; padding-left:0; list-style:none; color:var(--warn); font-weight:600 }}
.body {{ display:grid; grid-template-columns:230px 1fr; gap:16px; align-items:start }}
.media {{ background:#000; border-radius:10px; overflow:hidden }} video {{ width:100%; display:block }} .novideo {{ color:#aaa; padding:40px; text-align:center }}
table.steps {{ width:100%; border-collapse:collapse; font-size:14px }}
.steps th {{ text-align:left; color:var(--muted); font-weight:600; border-bottom:1px solid var(--line); padding:4px 6px; font-size:12px }}
.steps td {{ vertical-align:top; padding:8px 6px; border-bottom:1px solid var(--line) }}
.steps tr.fail td {{ background:color-mix(in srgb, var(--fail) 8%, transparent) }}
.steps tr.skip td {{ color:var(--muted) }}
td.n {{ width:52px; color:var(--muted); font-weight:700 }} td.shot {{ width:96px }} td.shot img {{ width:84px; border-radius:6px; border:1px solid var(--line); display:block }}
.noshot {{ color:var(--muted) }}
td.auto ul {{ margin:0; padding-left:0; list-style:none; font-size:13px }} td.auto li {{ margin-bottom:3px }}
.iid {{ font:11px ui-monospace, monospace; color:var(--muted) }}
li.ok {{ color:var(--pass) }} li.bad {{ color:var(--fail); font-weight:600 }} li.note {{ color:var(--warn); font-weight:600 }} li.info {{ color:var(--muted) }}
li.skip {{ color:var(--warn) }} li.notrun {{ color:var(--fail) }}
.ev a {{ color:var(--accent) }} a.muted {{ color:var(--muted) !important }} small {{ color:var(--muted) }}
.ext {{ display:inline-block; font-size:11px; background:#5b6b9e; color:#fff; border-radius:4px; padding:0 5px; margin-right:6px; vertical-align:middle }}
.steps button {{ font:12px ui-monospace, monospace; border:1px solid var(--line); background:transparent; color:var(--muted); border-radius:6px; padding:0 6px; cursor:pointer }}
.steps button:hover {{ border-color:var(--accent); color:var(--ink) }} .nt {{ color:var(--muted); font-size:12px }}
details.dev, details.memo {{ margin-top:6px; font-size:12px; color:var(--muted) }} details pre {{ white-space:pre-wrap; margin:4px 0 0 }}
@media (max-width:760px) {{ .body {{ grid-template-columns:1fr }} .media video {{ max-height:60vh; width:auto; max-width:100%; margin:auto }} td.vis {{ display:none }} }}
</style></head>
<body>
<header>
  <h1>영상 QA 결과</h1>
  <div class="summary">{E(run.name)} · {E(title)} · 통과 <b>{passed}</b> / {len(cases)} · ⚠ {noted}건 · 단계 시각을 누르면 영상이 그 지점으로 이동합니다</div>
  {bootline}
  {f'<p class="warn-line">⚠ {E(meta["warning"])}</p>' if meta.get("warning") else ''}
  <nav>{toc}</nav>
</header>
<main>{vsec}{''.join(cards)}{msec}</main>
<script>
document.addEventListener('click', e => {{
  const b = e.target.closest('button[data-video]'); if (!b) return;
  const v = document.getElementById(b.dataset.video); if (!v) return;
  v.currentTime = parseFloat(b.dataset.t); v.play();
}});
</script>
</body></html>"""
(run / "index.html").write_text(page)
print(run / "index.html")
