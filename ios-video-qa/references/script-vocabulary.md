# 스크립트 어휘

`steps/QA-NN.sh`는 `scenario()` 하나를 정의하고, 안에서 `step N`으로 각본의 단계를 차례로 시작한다. 단계 이름·기대는 각본에서 온다.
`flows.sh`(앱의 동작 묶음)와 `states.sh`(준비 상태)도 같은 어휘만 쓴다. 엔진이 실행 전에 세 파일을 모두 검사한다.

## 판정(합격 기준을 확인하는 유일한 방법)

```
expect_present  @ID[,ID] "<설명>" [-t 초] <질의>        있어야 한다
expect_gone     @ID "<설명>" [-t 초] <질의>              없어야 한다(읽기 실패는 '없음'이 아니다)
expect_visible  @ID "<설명>" [-t 초] [--keyboard] <질의> 영역이 화면 안, 잘리지 않음, 키보드·시트·알럿·팝오버에 안 가림
expect_tappable @ID "<설명>" [-t 초] <질의>              visible + 활성 + 다른 시트·알럿이 떠 있지 않음
check_eq|ne|gt|lt|ge|le|contains @ID "<설명>" <a> <b>     a·b는 ui_read 이름, 상수는 =값. 하나는 반드시 읽은 값
check_delta_eq  @ID "<설명>" <뒤> <앞> =<차이>            뒤 − 앞 = 차이
skip            @ID "<사유>"                             건너뜀. 사유 필수. 사람이 승인한 스크립트가 아니면 각본 결과가 skipped
```
`@ID`는 `qa ids`의 항목 ID이고, 그 항목의 단계 안에서만 쓴다. 한 판정이 여러 항목을 덮으면(`@a,b`) 항목마다 근거 줄이 따로 남는다.

## 읽기(출처 기록)

```
ui_read <이름> label|value|number|frame|count [-t 초] <질의>   값은 $(rv 이름). 질의·화면 정보·트리 경로·시각·재시도가 남는다
ui_locate <변수> [-t 초] <질의>                                변수에 "x y"
ui_find <질의> / ui_wait [-t 초] <질의> / ui_wait_gone [-t 초] <질의>   0 있음(사라짐) · 1 없음
```

## 질의

`--label 문구` `--contains 일부` `--id 식별자` `--type 종류` `--value 값` `--enabled|--disabled`
`--below y` `--above y` `--after "x,y"`(읽기 순서로 그 뒤) `--any`(화면 밖 포함, 바로 위에 `# 이유:` 주석)
`--first|--last|--nth N`: 후보가 여럿일 때 고르는 방법. 같은 줄이나 바로 윗줄에 `# 규칙: G번호`가 있어야 하고, 그 규칙의 승인된 쓰임(각본 범위·질의·선택 방법)과 맞아야 한다(`references/approvals.md`).
후보가 여럿인데 고르는 방법이 없으면 실행 중에 질문을 만들고 멈춘다.

## 조작

`ui_tap [-t 초] <질의>` `ui_press <질의>`(길게 누르지 않는 짧은 누르기) `ui_swipe up|down|left|right [y]` `ui_drag x1 y1 x2 y2`
`ui_type "글자"` `ui_type_slow "글자"` `ui_backspace [n]` `ui_submit` `ui_clear_field x y [n]`
`ui_pause [초]`: 영상 속도 조절용. 바로 앞에 화면 확인(대기·판정)이 없으면 `# 이유:`가 있어야 한다.
`app_launch` `app_relaunch` `app_kill` `app_reset` `state_save <이름>` `state_load <이름>` `state_exists <이름>`
`ui_info "<글>"` `ui_note "<글>" [--dev "<개발자 상세>"]`(⚠로 보고서에 남김) `ui_shot_here`(지금 화면을 단계 사진으로)
`fail "<사용자용 문구>" [--dev "<상세>"]`(앱·각본 문제) · `fail_env`(환경) · `fail_script`(스크립트)

## 좌표

숫자 좌표는 쓰지 않는다. 요소 질의를 쓰고, 꼭 필요하면 화면 크기 비율 `$(px 0.5 W)` `$(px 0.74 H)`.

## 금지(실행 전 검사가 막음)

- 셸 식 판정과 옛 어휘(`ui_check`, `ui_expect` …), 상수끼리 비교, 같은 읽기끼리 비교, `ui_read`가 아닌 피연산자
- 실행 도구 직접 호출(`axe`, `drv_*`, `xcrun`, `simctl`)
- 근거·판정 상태를 건드리는 어휘: `EVID`, `QAR_*`/`QARJ_*`, 근거 서명 키, `.failed`, `judge.py`, `evidence`, `python`
- `_`로 시작하는 엔진 내부 함수·변수(`_sleep`만 허용), 엔진 함수 이름으로 함수 다시 정의
- 셸 우회: `eval`, `source`, `exec`, `trap`, `unset`, `declare`, `typeset`(`typeset -A QA_STATES=`만 허용), `set`, `export`, `env`, `alias`, `builtin`, `command`
- 파일 쓰기·지우기: `>`·`>>`로 파일에 쓰기(`/dev/null`과 산술·조건 안의 비교는 허용), `rm`, `mv`, `cp`, `ln`, `tee`, 결과 폴더 변수(`$OUT` 등)
- 엔진 변수에 값 넣기(`QA_*`, `UI_*`, `KB_*`, `KEYBOARD`, `OUT` …)

검사는 정규식이다. 막히지 않았다고 허용된 것이 아니다. 위 목록의 뜻(근거와 판정을 스크립트가 만들거나 바꾸지 않는다)을 지킨다.
