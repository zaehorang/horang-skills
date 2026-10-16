"""스크린샷 비교. 지금은 "화면이 멈췄는가" 판정만. 단계별 전/후 비교(제외 영역)는 다음 단계에서 여기에 더한다.

    diff.py stable <a.png> <b.png>      → "stable" | "stable cursor <bbox>" | "moving <비율> <bbox>"

두 스크린샷을 ffmpeg로 1/3 크기 회색으로 읽어 다른 픽셀을 센다.
입력 커서 깜빡임처럼 작고 가늘게 모인 차이(너비 ≤ 2%, 높이 ≤ 6%)는 같은 화면으로 본다.
"""

import shutil
import subprocess
import sys


def gray(path, scale=3):
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", f"scale=iw/{scale}:-1,format=gray",
                        "-f", "rawvideo", "-"], capture_output=True)
    if r.returncode != 0:
        return None, 0, 0
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    w, h = (int(v) for v in p.stdout.strip().split(","))
    w //= scale
    h = len(r.stdout) // w if w else 0
    return r.stdout, w, h


def stable(a, b, tol=12):
    if not shutil.which("ffmpeg"):
        # ffmpeg가 없으면 바이트 비교로 물러난다(커서 차이를 구분하지 못한다)
        return "stable" if open(a, "rb").read() == open(b, "rb").read() else "moving ? (ffmpeg 없음)"
    ga, w, h = gray(a)
    gb, w2, h2 = gray(b)
    if ga is None or gb is None or (w, h) != (w2, h2) or not w:
        return "moving ? (읽기 실패)"
    diff = 0
    x0 = y0 = 10**9
    x1 = y1 = -1
    for y in range(h):
        row_a = ga[y * w:(y + 1) * w]
        row_b = gb[y * w:(y + 1) * w]
        if row_a == row_b:
            continue
        for x in range(w):
            if abs(row_a[x] - row_b[x]) > tol:
                diff += 1
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if diff == 0:
        return "stable"
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    bbox = f"{x0 * 3},{y0 * 3},{bw * 3}x{bh * 3}"
    if bw <= w * 0.02 + 1 and bh <= h * 0.06 + 1:
        return f"stable cursor {bbox}"
    return f"moving {diff / (w * h):.4f} {bbox}"


if __name__ == "__main__":
    if sys.argv[1:2] == ["stable"] and len(sys.argv) == 4:
        print(stable(sys.argv[2], sys.argv[3]))
    else:
        print(__doc__)
        sys.exit(2)
