# 준비 상태(예시 메모 앱)
typeset -A QA_STATES=(
  "빈 목록" state_empty_list
)

# 새로 설치하고 첫 실행 → 메모가 없는 목록
state_empty_list() {
  app_reset
  app_launch
  ui_wait -t 15 --label "메모" --type Heading || fail "메모 목록이 뜨지 않음"
}
