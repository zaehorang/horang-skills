"""근거 저장 비용 측정(E2). 실행 결과 폴더 → metrics.json

    metrics.py <results/시각-조건>

각본마다
  판정 수, 근거 저장 시간(판정 하나당 평균·최대 ms, 합계), 근거 용량(화면 정보·사진), 화면 정보 중복 제거율,
  녹화 프레임 공백: 영상 프레임 사이 간격 중 근거를 저장하던 구간(판정 직전 cost_ms) 안에 생긴 최대 공백
상한(넘으면 경고): 판정당 평균 400ms, 각본당 근거 25MB, 근거 저장 구간 프레임 공백 1.0초
"""

import glob
import json
import os
import subprocess
import sys

LIMITS = {"avg_cost_ms": 400, "case_mb": 25, "gap_in_save_s": 1.0}


def du(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def frame_times(mp4):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                        "-of", "csv=p=0", mp4], capture_output=True, text=True)
    ts = []
    for line in r.stdout.split():
        try:
            ts.append(float(line.strip(",")))
        except ValueError:
            pass
    return sorted(ts)


def main(run_dir):
    out = {"cases": {}, "limits": LIMITS, "warnings": []}
    for case_dir in sorted(glob.glob(os.path.join(run_dir, "QA-*"))):
        evp = os.path.join(case_dir, "evidence.jsonl")
        if not os.path.exists(evp):
            continue
        evs = [json.loads(l) for l in open(evp) if l.strip()]
        checks = {}
        for e in evs:
            if e.get("fn") != "skip":
                checks.setdefault(e["check_id"], e)
        costs = [e["cost_ms"] for e in checks.values() if e.get("cost_ms") is not None]
        refs = sum(1 for e in checks.values() if e.get("tree")) + sum(1 for e in checks.values() if e.get("pre_tree"))
        events = [json.loads(l) for l in open(os.path.join(case_dir, "events.jsonl")) if l.strip()] if os.path.exists(os.path.join(case_dir, "events.jsonl")) else []
        refs += sum(1 for e in events if e.get("name") and e.get("tree") and "path" in e)   # 읽기 기록(read)
        trees = glob.glob(os.path.join(case_dir, "evidence", "trees", "*.json"))
        c = {"checks": len(checks), "cost_ms_total": sum(costs), "cost_ms_avg": round(sum(costs) / len(costs)) if costs else 0,
             "cost_ms_max": max(costs) if costs else 0, "evidence_bytes": du(os.path.join(case_dir, "evidence")),
             "tree_files": len(trees), "tree_refs": refs,
             "tree_dedup": round(1 - len(trees) / refs, 2) if refs else 0}
        mp4 = os.path.join(case_dir, "video.mp4")
        if os.path.exists(mp4):
            ts = frame_times(mp4)
            gaps = [(b - a, a, b) for a, b in zip(ts, ts[1:])]
            c["video_max_gap_s"] = round(max((g for g, _, _ in gaps), default=0), 2)
            worst = 0.0
            for e in checks.values():
                if e.get("t_shot") is None or e.get("cost_ms") is None:
                    continue
                w0, w1 = e["t_shot"] - e["cost_ms"] / 1000 - 0.2, e["t_shot"] + 0.2   # 근거 저장 구간(앞뒤 여유)
                for g, a, b in gaps:
                    if a < w1 and b > w0:
                        worst = max(worst, g)
            c["gap_in_save_s"] = round(worst, 2)
        out["cases"][os.path.basename(case_dir)] = c
        if c["cost_ms_avg"] > LIMITS["avg_cost_ms"]:
            out["warnings"].append(f"{os.path.basename(case_dir)}: 판정당 근거 저장 평균 {c['cost_ms_avg']}ms > {LIMITS['avg_cost_ms']}ms")
        if c["evidence_bytes"] > LIMITS["case_mb"] * 1e6:
            out["warnings"].append(f"{os.path.basename(case_dir)}: 근거 {c['evidence_bytes'] / 1e6:.1f}MB > {LIMITS['case_mb']}MB")
        if c.get("gap_in_save_s", 0) > LIMITS["gap_in_save_s"]:
            out["warnings"].append(f"{os.path.basename(case_dir)}: 근거 저장 구간 프레임 공백 {c['gap_in_save_s']}s > {LIMITS['gap_in_save_s']}s")
    cs = list(out["cases"].values())
    n = sum(c["checks"] for c in cs) or 1
    out["summary"] = {"checks": sum(c["checks"] for c in cs), "cost_ms_total": sum(c["cost_ms_total"] for c in cs),
                      "cost_ms_avg": round(sum(c["cost_ms_total"] for c in cs) / n),
                      "cost_ms_max": max((c["cost_ms_max"] for c in cs), default=0),
                      "evidence_mb": round(sum(c["evidence_bytes"] for c in cs) / 1e6, 1),
                      "tree_dedup": round(1 - sum(c["tree_files"] for c in cs) / (sum(c["tree_refs"] for c in cs) or 1), 2),
                      "video_max_gap_s": max((c.get("video_max_gap_s", 0) for c in cs), default=0),
                      "gap_in_save_s": max((c.get("gap_in_save_s", 0) for c in cs), default=0)}
    json.dump(out, open(os.path.join(run_dir, "metrics.json"), "w"), ensure_ascii=False, indent=1)
    s = out["summary"]
    print(f"근거 비용: 판정 {s['checks']}개 · 저장 평균 {s['cost_ms_avg']}ms(최대 {s['cost_ms_max']}) · 합계 {s['cost_ms_total'] / 1000:.1f}s · "
          f"용량 {s['evidence_mb']}MB · 화면 정보 중복 제거 {s['tree_dedup']:.0%} · 근거 저장 구간 프레임 공백 최대 {s['gap_in_save_s']}s")
    for w in out["warnings"]:
        print("  ⚠ " + w)


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
