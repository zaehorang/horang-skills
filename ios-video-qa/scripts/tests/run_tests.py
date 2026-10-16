"""엔진 시험. 시뮬레이터·전역 설정·네트워크 없이 돈다(qa test).

    run_tests.py [-v] [이름 일부]

- python: scripts/tests/test_*.py (unittest)
- zsh:    scripts/tests/test_*.sh (성공하면 exit 0, 실패 줄은 "FAIL"로 시작)
- node:   scripts/tests/test_*.js (node가 없으면 건너뜀)
시험은 임시 폴더에서만 파일을 만들고 지운다.
"""

import os
import shutil
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv):
    verbose = "-v" in argv
    pick = [a for a in argv if not a.startswith("-")]
    want = lambda name: not pick or any(p in name for p in pick)
    sys.path.insert(0, HERE)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for f in sorted(os.listdir(HERE)):
        if f.startswith("test_") and f.endswith(".py") and want(f):
            suite.addTests(loader.loadTestsFromName(f[:-3]))
    r = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    failed = len(r.failures) + len(r.errors)
    total = r.testsRun
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for f in sorted(os.listdir(HERE)):
        if not want(f) or not f.startswith("test_"):
            continue
        if f.endswith(".sh"):
            cmd = ["zsh", os.path.join(HERE, f)]
        elif f.endswith(".js"):
            if not shutil.which("node"):
                print(f"건너뜀: {f} (node 없음)")
                continue
            cmd = ["node", os.path.join(HERE, f)]
        else:
            continue
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        lines = [l for l in p.stdout.splitlines() if l.strip()]
        n_ok = sum(l.startswith("ok") for l in lines)
        bad = [l for l in lines if l.startswith("FAIL")]
        total += n_ok + len(bad)
        if p.returncode or bad:
            failed += max(len(bad), 1)
            print(f"✗ {f}\n" + "\n".join(bad or lines[-5:]) + ("\n" + p.stderr[-800:] if p.stderr else ""))
        elif verbose:
            print(f"✓ {f}: {n_ok}개")
    print(f"\n엔진 시험: {total - failed}/{total} 통과" + (f", 실패 {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
