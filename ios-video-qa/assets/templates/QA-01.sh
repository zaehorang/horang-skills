# QA-01 첫 실행. 단계 이름과 기대는 cases/QA-01-first-launch.md에서 온다. 항목 ID는 `qa ids QA-01`
scenario() {
  step 1
  app_launch
  dismiss_system_alerts
  expect_present @3d5630eb#1.1 "첫 화면의 문구" -t 15 --label "첫 화면의 문구"
}
