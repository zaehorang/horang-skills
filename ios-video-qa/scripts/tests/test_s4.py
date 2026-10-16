"""실행 전 검사(S4): 막아야 할 스크립트가 실제로 막히는가(음성 사례)와, 예시가 승인 대기 말고는 통과하는가."""

import json
import os
import shutil
import unittest

from helpers import append_script, casefile, check, copy_example, human_approve, quiet


class S4(unittest.TestCase):
    def setUp(self):
        self.tmp, self.qa = copy_example()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def assertBlocked(self, snippet, needle):
        append_script(self.qa, snippet)
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(rc, 1, f"막혀야 함: {snippet!r}")
        self.assertTrue(any(needle in e for e in errs), f"{needle!r} 없음: {errs}")

    def test_example_waits_only_for_human(self):
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual(errs, [])
        self.assertEqual(rc, 5)
        self.assertTrue(all("승인" in p for p in pending), pending)

    def test_example_passes_after_human_approval(self):
        human_approve(self.qa)
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual((rc, errs, pending), (0, [], []))

    # 출처·판정
    def test_constant_compare(self):
        self.assertBlocked('  check_eq @f846bbb7#3.1 "x" =a =a', "상수만으로 된 판정")

    def test_shell_expression(self):
        self.assertBlocked('  ui_check "1 == 1"', "옛 어휘")

    def test_same_read_twice(self):
        self.assertBlocked('  check_eq @42437205#3.1 "x" count_after count_after', "같은 읽기끼리")

    def test_operand_without_read(self):
        self.assertBlocked('  check_eq @42437205#3.1 "x" made_up =1', "출처 있는 읽기")

    def test_judgment_without_item(self):
        self.assertBlocked('  expect_present "x" --label a', "항목(@ID)이 없음")

    def test_item_of_other_step(self):
        self.assertBlocked('  expect_present @55145252#1.1 "x" --label a', "1단계 항목인데 3단계")

    def test_skip_without_reason(self):
        self.assertBlocked('  skip @42437205#3.1', "사유 없는 건너뜀")

    def test_uncovered_item(self):
        p = os.path.join(self.qa, "steps", "QA-01.sh")
        s = open(p, encoding="utf-8").read().replace('  check_delta_eq @2ac57bd3#3.2 "메모 수가 1 늘어남" count_after count_before =1\n', "")
        open(p, "w", encoding="utf-8").write(s)
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(rc, 1)
        self.assertTrue(any("덮는 판정이 없음" in e for e in errs), errs)

    # 금지 어휘(근거 위조·판정 우회)
    def test_forbidden_vocabulary(self):
        cases = [
            ('  print "{}" >> $EVID', "근거"),
            ('  QARJ_body=\'{"value":"장보기"}\'', "근거·읽기 기록"),
            ('  _pass "가짜 통과"', "엔진 내부"),
            ('  rm -f $OUT/.failed', "판정기·근거 파일"),
            ('  python3 judge.py check eq', "판정기"),
            ('  eval "ui_tap --label a"', "셸 우회"),
            ('  print x > result.txt', "파일로 내보냄"),
            ('  typeset -g QAR_body=장보기', "근거·읽기 기록"),
            ('  KEYBOARD=hardware', "엔진 변수"),
            ('  unset -f fail', "셸 우회"),
            ('  print $_QA_KEY', "근거·읽기 기록"),
        ]
        for snippet, needle in cases:
            with self.subTest(snippet=snippet):
                self.tearDown(); self.setUp()
                self.assertBlocked(snippet, needle)

    def test_engine_function_redefinition(self):
        p = os.path.join(self.qa, "flows.sh")
        open(p, "a", encoding="utf-8").write('fail() { :; }\n')
        r = casefile("check-shared", self.qa)
        rc, errs = r.returncode, [l for l in r.stdout.splitlines() if l.startswith("차단")]
        self.assertEqual(rc, 1)
        self.assertTrue(any("엔진 함수 `fail`" in e for e in errs), errs)

    def test_allowed_vocabulary_not_blocked(self):
        append_script(self.qa, '  ui_wait --label "x" >/dev/null || fail "없음"\n  if (( 2 > 1 )); then ui_info "a > b"; fi\n  [[ a > b ]] && _sleep 0.1')
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(errs, [])

    def test_fixed_wait_without_reason(self):
        self.assertBlocked('  ui_tap --label a\n  ui_pause 2', "근거 없는 고정 대기")

    def test_numeric_coordinates(self):
        self.assertBlocked('  ui_tap_xy 120 300', "숫자 좌표")


class Selection(unittest.TestCase):
    """선택 규칙: 규칙 없는 --first, 답 없는 규칙, 다른 각본의 규칙, 승인 범위 밖 질의"""

    def setUp(self):
        self.tmp, self.qa = copy_example()
        human_approve(self.qa)
        import approve
        self.approve = approve
        quiet(approve.gap_add, self.qa, type("A", (), dict(case="QA-01", item="", reason="multiple-candidates", question="버튼이 둘",
                                                     step=3, origin="code", blocking=True, options="첫 번째|마지막",
                                                     candidates=None, where="QA-01 3단계", query='{"label": "저장"}'))())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add_line(self, line):
        append_script(self.qa, line)
        human_approve(self.qa)   # 스크립트 승인은 따로 시험한다(여기서는 규칙만 본다)
        return check(self.qa)

    def answer(self, uses, case=None):
        data = self.approve.gaps_store(self.qa).load()
        if case:
            data["gaps"][0]["case"] = case
            self.approve.gaps_store(self.qa).save(data, {"test": "case"})
        quiet(self.approve.do_answer, self.qa, "G1", "마지막", "tty", "tester", uses)

    def test_selector_without_rule_blocks(self):
        rc, errs, _, _ = self.add_line('  ui_tap --label "저장" --last')
        self.assertEqual(rc, 1)
        self.assertTrue(any("선택 규칙이 없음" in e for e in errs), errs)

    def test_unanswered_rule_waits(self):
        rc, errs, pending, _ = self.add_line('  ui_tap --label "저장" --last   # 규칙: G1')
        self.assertEqual((rc, errs), (5, []))
        self.assertTrue(any("답이 없음" in p for p in pending), pending)

    def test_bound_rule_passes_and_other_query_waits(self):
        self.answer([{"query": {"label": "저장"}, "selector": "last", "where": "t"}])
        rc, errs, pending, _ = self.add_line('  ui_tap --label "저장" --last   # 규칙: G1')
        self.assertEqual((rc, errs, pending), (0, [], []))
        rc, errs, pending, _ = self.add_line('  ui_tap --label "새 메모" --first   # 규칙: G1')
        self.assertEqual(rc, 5)
        self.assertTrue(any("승인 범위 밖" in p for p in pending), pending)

    def test_rule_of_other_case_blocks(self):
        self.answer([{"query": {"label": "저장"}, "selector": "last", "where": "t"}], case="QA-09")
        rc, errs, _, _ = self.add_line('  ui_tap --label "저장" --last   # 규칙: G1')
        self.assertEqual(rc, 1)
        self.assertTrue(any("QA-09의 규칙" in e for e in errs), errs)

    def test_fallback_choice_without_rule(self):
        rc, errs, _, _ = self.add_line('  ui_tap --label "저장" || ui_tap --label "완료"')
        self.assertTrue(any("대체 선택" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
