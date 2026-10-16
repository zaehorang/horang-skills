"""자판 팩 인터페이스, 각본 별칭, 문자열 이스케이프, qa init, 새 각본 제목, 누출 검사."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import CLEAN_ENV, ENGINE, LIB, PY, casefile, check, run

REQUIRED_LABELS = ("KB_SHIFTED", "KB_PROBE_KEYS", "KB_GLOBE_LABEL", "KB_OTHER_LANG_LABEL", "KB_DELETE_LABEL", "KB_RETURN_ID",
                   "KB_DELETE_ID", "KB_SHIFT_ID", "KB_MORE_ID", "KB_SPACE_ID", "KB_ASSISTANT_ID", "KB_MORE_TO_LETTERS", "KB_LANG_NAME")


class Keyboard(unittest.TestCase):
    def pack(self, lang, *args):
        return run(PY + [os.path.join(LIB, "keyboard", lang + ".py"), *args]).stdout

    def test_every_pack_has_interface(self):
        for f in os.listdir(os.path.join(LIB, "keyboard")):
            if f.endswith(".py"):
                with self.subTest(pack=f):
                    out = self.pack(f[:-3], "--labels")
                    names = re.findall(r"^(\w+)=", out, re.M)
                    self.assertEqual(sorted(names), sorted(REQUIRED_LABELS))

    def test_ko(self):
        self.assertEqual(self.pack("ko", "안녕").strip(), "dkssud")
        self.assertEqual(self.pack("ko", "--keys", "가").split(), ["ㄱ", "ㅏ"])

    def test_en(self):
        self.assertEqual(self.pack("en", "Hi").strip(), "Hi")
        self.assertEqual(self.pack("en", "--keys", "Hi").split(), ["H", "i"])


class CaseFormat(unittest.TestCase):
    def test_english_aliases(self):
        d = tempfile.mkdtemp()
        md = os.path.join(d, "QA-05-x.md")
        open(md, "w").write("# QA-05 x\n\ns\n\n- Prep: 빈 목록\n- Run: auto\n- Input: hardware keyboard\n- Conditions: 기본\n\n"
                            "| # | 행동 | 자동 확인 | 눈으로 확인 |\n|---|---|---|---|\n| 1 | [external] a | b | c |\n\n## Notes\n- n\n")
        c = json.loads(casefile("parse", md).stdout)
        shutil.rmtree(d)
        self.assertEqual((c["header"]["준비"], c["header"]["실행"], c["input_mode"], c["steps"][0]["external"], c["notes"]),
                         ("빈 목록", "자동", "hardware", True, ["n"]))


class Shell(unittest.TestCase):
    def test_json_escapes_control_chars(self):
        script = ('source <(sed -n "/^_json()/,/^}/p" %s/core.sh); _json $\'a"b\\\\c\\r\\x01d\\n\\te\'' % LIB)
        out = subprocess.run(["zsh", "-c", script], capture_output=True, text=True).stdout
        self.assertEqual(json.loads(out), 'a"b\\c\r\x01d\n\te')


class Init(unittest.TestCase):
    def test_init_creates_qa_that_waits_only_for_human(self):
        d = tempfile.mkdtemp(prefix="qa-init-")
        os.makedirs(os.path.join(d, "Memo", "Memo.xcodeproj"))
        r = run(PY + [os.path.join(LIB, "init.py"), ENGINE, d])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        qa = os.path.join(d, "qa")
        cfg = open(os.path.join(qa, "qa.config")).read()
        self.assertIn('QA_PROJECT="Memo/Memo.xcodeproj"', cfg)
        self.assertIn('QA_SCHEME="Memo"', cfg)
        self.assertNotIn("__", cfg)
        rc, errs, pending, _ = check(qa)
        self.assertEqual((rc, errs), (5, []))
        r2 = run(PY + [os.path.join(LIB, "init.py"), ENGINE, d])
        self.assertEqual(r2.returncode, 1)   # 이미 있으면 바꾸지 않는다
        shutil.rmtree(d)

    def test_new_case_title_with_special_chars(self):
        d = tempfile.mkdtemp(prefix="qa-new-")
        qa = os.path.join(d, "qa")
        os.makedirs(os.path.join(qa, "cases"))
        r = subprocess.run(["zsh", os.path.join(LIB, "pipeline.sh"), "new", qa, "QA-07", "a/b & c\\d", "x/../y"],
                           capture_output=True, text=True, env=CLEAN_ENV)
        files = os.listdir(os.path.join(qa, "cases"))
        self.assertEqual(files, ["QA-07-x----y.md"], r.stdout + r.stderr)
        self.assertTrue(open(os.path.join(qa, "cases", files[0])).read().startswith("# QA-07 a/b & c\\d\n"))
        shutil.rmtree(d)


class Leaks(unittest.TestCase):
    """공개 전 누출 검사: 사용자 경로·특정 앱 이름이 엔진 어디에도 없어야 한다(검사 문자열은 코드 포인트로 둔다)"""
    WORDS = [[47, 85, 115, 101, 114, 115, 47], [47, 112, 114, 105, 118, 97, 116, 101, 47, 116, 109, 112],
             [122, 97, 101, 104, 111, 114, 97, 110, 103], [54620, 51077, 46021, 49436], [70, 105, 118, 101, 71, 117, 121, 101, 115],
             [54644, 47532], [50756, 46021], [99, 111, 109, 46, 70, 105, 118, 101, 78, 111, 114, 109, 115], [48, 52, 49884]]

    def test_no_leaks(self):
        words = ["".join(map(chr, w)) for w in self.WORDS]
        hits = []
        for root, dirs, files in os.walk(ENGINE):
            dirs[:] = [x for x in dirs if x != ".git"]
            for f in files:
                p = os.path.join(root, f)
                try:
                    text = open(p, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                hits += [f"{os.path.relpath(p, ENGINE)}: {w}" for w in words if w in text]
        self.assertEqual(hits, [])

    def test_no_bytecode(self):
        found = [os.path.join(r, x) for r, ds, fs in os.walk(ENGINE) for x in ds + fs if x == "__pycache__" or x.endswith(".pyc")]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
