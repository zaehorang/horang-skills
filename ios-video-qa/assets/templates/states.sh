# 준비 상태. 각본의 '준비:' 이름 → 함수. 녹화 전에 실행되며 영상에 남지 않는다.
# 엔진 어휘(app_reset, app_launch, state_save/state_load, ui_*)와 flows.sh의 흐름만 쓴다.

typeset -A QA_STATES=(
  "새 설치" state_fresh_install
  "첫 화면" state_first_screen
)

state_fresh_install() { app_reset; }

state_first_screen() {
  app_reset
  app_launch
  dismiss_system_alerts
  ui_wait -t 15 --label "첫 화면의 문구" || fail "첫 화면이 뜨지 않음"
}
