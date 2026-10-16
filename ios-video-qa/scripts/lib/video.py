"""영상 후처리. 지금은 faststart(브라우저가 바로 재생하도록 메타데이터를 앞으로)만.

    video.py faststart <mp4>      제자리에서 faststart로 다시 묶는다(재인코딩 없음)

자막·탭 표시·구간 자르기·전/후 나란히는 다음 단계(PLAN 4단계)에서 여기에 더한다.
"""

import os
import shutil
import subprocess
import sys
import tempfile


def faststart(path):
    if not shutil.which("ffmpeg"):
        return False
    fd, tmp = tempfile.mkstemp(suffix=".mp4", dir=os.path.dirname(path) or ".")
    os.close(fd)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c", "copy", "-movflags", "+faststart", tmp])
    if r.returncode == 0:
        os.replace(tmp, path)
        return True
    os.unlink(tmp)
    return False


if __name__ == "__main__":
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "faststart":
        sys.exit(0 if faststart(arg) else 1)
