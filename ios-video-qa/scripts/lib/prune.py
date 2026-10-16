"""결과 보존: 최근 N회 실행 또는 D일 이내 실행만 남긴다(둘 중 하나라도 해당하면 남김).

    prune.py <qa/results> [--dry]

N·D는 qa.config의 QA_KEEP_RUNS·QA_KEEP_DAYS(환경 변수로 넘어온다). 기본 10회·14일.

기준본(qa/baseline/)은 results 밖에 있어 건드리지 않는다. results/latest가 가리키는 실행도 남긴다.
"""

import os
import shutil
import sys
import time

KEEP_RUNS = int(os.environ.get("QA_KEEP_RUNS") or 10)
KEEP_DAYS = float(os.environ.get("QA_KEEP_DAYS") or 14)


def main(results, dry=False):
    if not os.path.isdir(results):
        return
    latest = os.path.realpath(os.path.join(results, "latest"))
    runs = sorted((p for p in (os.path.join(results, n) for n in os.listdir(results))
                   if os.path.isdir(p) and not os.path.islink(p)), key=os.path.getmtime, reverse=True)
    now = time.time()
    removed = []
    for i, p in enumerate(runs):
        young = now - os.path.getmtime(p) < KEEP_DAYS * 86400
        if i < KEEP_RUNS or young or os.path.realpath(p) == latest:
            continue
        removed.append(os.path.basename(p))
        if not dry:
            shutil.rmtree(p)
    print(f"결과 보존: {len(runs) - len(removed)}개 남김, {len(removed)}개 지움" + (" (시험)" if dry else "") + (": " + ", ".join(removed) if removed else ""))


if __name__ == "__main__":
    main(sys.argv[1], "--dry" in sys.argv)
