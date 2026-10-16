"""재현 검증(S6)과 가림 판정: 화면을 보지 않는 판정은 결함으로 막히고, 시트에 가린 요소는 보이지 않는다."""

import json
import os
import shutil
import tempfile
import unittest

from helpers import CLEAN_ENV, EXAMPLE, LIB, PY, casefile, judge, load_tree, run

KEY = "c" * 32
CASE_MD = os.path.join(EXAMPLE, "cases", "QA-01-write-memo.md")


class Run:
    """합성 실행 폴더: results/<실행>/QA-01/{case.json, evidence.jsonl, evidence/trees}"""

    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="qa-verify-")
        self.run = os.path.join(self.root, "results", "20260101-000000-기본")
        self.case = os.path.join(self.run, "QA-01")
        os.makedirs(self.case)
        open(os.path.join(self.case, "case.json"), "w").write(casefile("parse", CASE_MD).stdout)
        self.items = [it["id"] for s in json.load(open(os.path.join(self.case, "case.json")))["steps"] for it in s["items"]]
        self.ev = os.path.join(self.case, "evidence.jsonl")
        self.trees = os.path.join(self.case, "evidence", "trees")
        self.n = 0

    def rec(self, item):
        self.n += 1
        return ["--evidence", self.ev, "--check-id", f"c{self.n}", "--items", item, "--step", "1", "--phase", "scenario"]

    def expect(self, item, fn, tree, *query):
        return judge(["expect", fn, "--save", self.trees, *self.rec(item), *query], load_tree(tree), key=KEY)[0]

    def check_eq_read(self, item, tree, const, *query):
        _, p = judge(["pick", "--save", self.trees, "--kind", "number", *query], load_tree(tree), key=None)
        inp = dict(json.loads(p["P_READ"]), name="count")
        c = {"name": "=" + const, "value": const, "read": {"const": True}}
        return judge(["check", "eq", "--in", json.dumps(inp, ensure_ascii=False), "--in", json.dumps(c, ensure_ascii=False),
                      *self.rec(item)], key=KEY)[0]

    def skip(self, item):
        return judge(["skip", "--reason", "해당 없음", *self.rec(item)], key=KEY)[0]

    def verify(self, key=KEY):
        env = dict(CLEAN_ENV, QA_EVID_KEY=key) if key else CLEAN_ENV
        r = run(PY + [os.path.join(LIB, "verify.py"), self.run, "--quiet"], env=env)
        return r.returncode, json.load(open(os.path.join(self.run, "verify.json")))

    def close(self):
        shutil.rmtree(self.root)


class Verify(unittest.TestCase):
    def setUp(self):
        self.r = Run()

    def tearDown(self):
        self.r.close()

    def fill_verified(self):
        r = self.r
        self.assertEqual(r.expect(r.items[0], "present", "list.json", "--label", "장보기"), 0)
        self.assertEqual(r.check_eq_read(r.items[1], "list.json", "3", "--contains", "메모 ", "--type", "StaticText"), 0)
        self.assertEqual(r.expect(r.items[2], "visible", "list.json", "--label", "새 메모", "--type", "Button"), 0)
        self.assertEqual(r.expect(r.items[3], "tappable", "list.json", "--label", "저장"), 0)
        self.assertEqual(r.expect(r.items[4], "gone", "list.json", "--label", "장보기"), 1)   # 실패한 판정도 기록된다

    def test_reacting_judgments_are_verified(self):
        self.fill_verified()
        rc, v = self.r.verify()
        st = {k: x["status"] for k, x in v["cases"]["QA-01"]["items"].items()}
        self.assertEqual([st[i] for i in self.r.items[:4]], ["verified"] * 4)
        why = v["cases"]["QA-01"]["items"][self.r.items[2]]["checks"][0]["why"]
        self.assertIn("시트가 요소를 덮게 함 → fail", why)

    def test_always_true_judgment_is_defect_and_blocks(self):
        r = self.r
        for it in r.items[:4]:
            r.expect(it, "present", "list.json", "--label", "장보기")
        self.assertEqual(r.expect(r.items[4], "gone", "list.json", "--label", "오타 난 문구"), 0)
        rc, v = r.verify()
        self.assertEqual(rc, 1)
        self.assertEqual(v["cases"]["QA-01"]["items"][r.items[4]]["status"], "defect")
        self.assertTrue(any("판정 결함" in b for b in v["blocking"]), v["blocking"])

    def test_query_matching_whole_app_is_defect(self):
        r = self.r
        r.expect(r.items[0], "present", "list.json", "--type", "Application", "--any")
        rc, v = r.verify()
        self.assertEqual(v["cases"]["QA-01"]["items"][r.items[0]]["status"], "defect")
        self.assertEqual(rc, 1)

    def test_unverifiable_over_limit_blocks(self):
        r = self.r
        r.expect(r.items[0], "present", "list.json", "--label", "장보기")
        for it in r.items[1:]:
            r.skip(it)
        rc, v = r.verify()
        self.assertEqual(rc, 1)
        self.assertEqual(v["cases"]["QA-01"]["summary"]["skipped"], 4)
        self.assertTrue(any("각본 상한" in b for b in v["blocking"]), v["blocking"])

    def test_missing_key_and_forged_lines_block(self):
        self.fill_verified()
        rc, v = self.r.verify(key=None)
        self.assertEqual(rc, 1)
        self.assertTrue(any("키가 없음" in b for b in v["blocking"]))
        rc, v = self.r.verify(key="d" * 32)
        self.assertTrue(any("위조 의심" in b for b in v["blocking"]), v["blocking"])


class Occlusion(unittest.TestCase):
    """보인다·누를 수 있다: 시트(알럿)가 덮으면 실패, 시트 안의 요소는 통과"""

    def expect(self, fn, tree, *q):
        return judge(["expect", fn, *q], load_tree(tree), key=None)

    def test_sheet_covers_element(self):
        rc, p = self.expect("visible", "alert.json", "--label", "저장")
        self.assertEqual(rc, 1)
        self.assertIn("Sheet에 가려짐", p["P_REASON"])

    def test_element_inside_sheet(self):
        self.assertEqual(self.expect("tappable", "alert.json", "--label", "삭제")[0], 0)

    def test_modal_blocks_tap_elsewhere(self):
        tree = load_tree("alert.json")
        tree[0]["children"][0]["frame"]["y"] = 600   # 시트와 겹치지 않는 곳
        rc, p = judge(["expect", "tappable", "--label", "저장"], tree, key=None)
        self.assertEqual(rc, 1)
        self.assertIn("누를 수 없음", p["P_REASON"])
        self.assertEqual(judge(["expect", "visible", "--label", "저장"], tree, key=None)[0], 0)


if __name__ == "__main__":
    unittest.main()
