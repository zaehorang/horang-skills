# 이 앱의 동작 묶음. 여러 각본이 같이 쓰는 흐름을 함수로 둔다. 화면 문구가 바뀌면 여기만 고친다.
# 엔진 어휘(ui_*, app_*, state_*, 판정 함수)만 쓴다. 실행 도구를 직접 부르지 않는다(references/script-vocabulary.md).

# 시스템 팝업(권한 등)이 뜨면 정해진 응답을 한다. 응답은 이 앱이 정한다
dismiss_system_alerts() {
  :   # 예) ui_find --label "<허용하지 않는 버튼 문구>" --type Button && ui_tap --label "<허용하지 않는 버튼 문구>" --type Button
}

# 예)
# open_settings() { ui_tap --label "<설정 버튼 문구>" --type Button; ui_wait --label "<설정 화면 제목>" || fail "설정 화면이 아님"; }
