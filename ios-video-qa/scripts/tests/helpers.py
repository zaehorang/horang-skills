"""시험 공용: 예시 qa 폴더를 임시 폴더에 복사하고, 엔진 모듈을 불러오고, 판정기를 부른다."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.dirname(os.path.dirname(HERE))
LIB = os.path.join(ENGINE, "scripts", "lib")
EXAMPLE = os.path.join(ENGINE, "examples", "memo-app", "qa")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, LIB)
sys.path.insert(0, os.path.join(LIB, "driver"))
PY = [sys.executable, "-I", "-B"]
CLEAN_ENV = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "CODEX", "CURSOR", "AIDER", "GEMINI", "OPENCODE", "AMP_"))}
CLEAN_ENV["PYTHONDONTWRITEBYTECODE"] = "1"


def copy_example():
    d = tempfile.mkdtemp(prefix="qa-test-")
    qa = os.path.join(d, "qa")
    shutil.copytree(EXAMPLE, qa)
    return d, qa


def run(args, env=None, stdin=None, cwd=None):
    return subprocess.run(args, capture_output=True, text=True, env=env or CLEAN_ENV, input=stdin, cwd=cwd)


def casefile(*args, env=None):
    return run(PY + [os.path.join(LIB, "casefile.py"), *args], env=env)


def check(qa, cid="QA-01"):
    """(rc, 차단, 대기, 경고)"""
    md = next(os.path.join(qa, "cases", f) for f in os.listdir(os.path.join(qa, "cases")) if f.startswith(cid + "-"))
    r = casefile("check", md, os.path.join(qa, "steps", cid + ".sh"), qa)
    rows = [l.split("\t", 1) for l in r.stdout.splitlines() if "\t" in l]
    pick = lambda k: [v for kk, v in rows if kk == k]
    return r.returncode, pick("차단"), pick("대기"), pick("경고")


def quiet(fn, *a, **k):
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def human_approve(qa, cid="QA-01"):
    """사람 승인 경로를 거치지 않고 기록만 만든다(시험 전용: 대화형 터미널을 흉내 내지 않고 라이브러리 함수를 직접 부른다)"""
    import approve
    quiet(approve.do_approve, qa, [cid], "tty", "tester")


def judge(args, tree=None, key="k" * 32):
    env = dict(CLEAN_ENV, QA_EVID_KEY=key) if key else CLEAN_ENV
    r = run(PY + [os.path.join(LIB, "judge.py"), *args], env=env, stdin=json.dumps(tree) if tree is not None else None)
    out = {}
    for line in r.stdout.splitlines():
        if line.startswith("P_") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = shlex.split(v)[0] if v else ""
    return r.returncode, out


def load_tree(name):
    return json.load(open(os.path.join(FIXTURES, name), encoding="utf-8"))


def append_script(qa, text, cid="QA-01"):
    p = os.path.join(qa, "steps", cid + ".sh")
    s = open(p, encoding="utf-8").read().rstrip()
    assert s.endswith("}")
    open(p, "w", encoding="utf-8").write(s[:-1] + text.rstrip() + "\n}\n")
