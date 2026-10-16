# QA-01 메모 쓰기. 단계 이름·기대는 cases/QA-01-write-memo.md. 항목 ID는 `qa ids QA-01`
scenario() {
  step 1
  ui_read count_before number --contains "메모 " --type StaticText   # 목록 아래의 '메모 N개'
  open_new_memo
  expect_present @55145252#1.1 "편집 화면 제목 '새 메모'" --label "새 메모" --type Heading

  step 2
  ui_type "장보기"
  ui_read body value --type TextView
  check_eq @f846bbb7#2.1 "입력칸에 \"장보기\"" body =장보기
  expect_visible @51adb221#2.2 "'저장'이 키보드 위에 보임" --keyboard --label "저장" --type Button

  step 3
  ui_tap --label "저장" --type Button
  expect_present @42437205#3.1 "목록에 \"장보기\"" --label "장보기" --type StaticText
  ui_read count_after number --contains "메모 " --type StaticText
  check_delta_eq @2ac57bd3#3.2 "메모 수가 1 늘어남" count_after count_before =1
}
