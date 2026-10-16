# 명령·종료 코드·설정

명령은 `<엔진>/scripts/qa <명령>`. 앱 레포(또는 그 아래)에서 부르면 `qa/qa.config`를 찾는다. 다른 곳에서는 `--project <qa 폴더>`.

## 명령

| 명령 | 하는 일 | 누가 |
|---|---|---|
| `init [--project <앱 레포>]` | `qa/` 만들기(qa.config, states.sh, flows.sh, .gitignore, 첫 각본·스크립트). 이미 있으면 바꾸지 않음 | 누구나 |
| `doctor` | 도구·전역 상태·qa.config·기기·각본의 준비 상태·승인 요약 점검. 읽기만 | 누구나 |
| `test [-v] [이름]` | 엔진 시험(시뮬레이터 없이) | 누구나 |
| `check [ID…] [--condition 이름]` | 실행 전 검사(S4)만 | 누구나 |
| `run [ID…] [--condition 이름] [--no-build] [--device 이름]` | S4 → 빌드 → 실행(S5) → 재현 검증(S6)·비용 측정 → 보고서 | 누구나 |
| `status` | 각본별 승인 상태(승인됨·사람 승인 대기·차단과 이유), 질문·규칙 상태 | 누구나 |
| `ids <ID>` | 단계별 확인 항목 ID(스크립트의 `@ID`) | 누구나 |
| `verify [결과 폴더]` | 재현 검증만 다시 | 누구나 |
| `review [결과 폴더] [--out html]` | 로컬 리뷰 페이지 | 누구나 |
| `share [결과 폴더] --adapter <이름> [--out 폴더] [--asset-map map.json]` | 공유 묶음 만들기(발행은 하지 않음) | 누구나 |
| `new <ID> "<제목>" <영문-요약>`, `stage <ID> [Sn \| --rerun Sn]`, `sim <ID> <탐색 스크립트>` | 새 각본 파이프라인 S0~S7 | 누구나 |
| `prune` | 결과 보존 규칙 적용 | 누구나 |
| `approve <ID…>` / `approve --from <파일>` | 각본+스크립트 승인 | **사람만**(대화형 터미널) |
| `answer <G> <답>` / `answer <G> --bind` / `answer --from <파일>` | 질문 답, 규칙의 쓰임 승인 | **사람만** |
| `judgments --from <파일>` | 리뷰 페이지의 "눈으로 확인" 판단 반영 | **사람만** |

## 종료 코드

| 코드 | `run` | `check` |
|---|---|---|
| 0 | 전부 통과(사람 승인 상태에서) | 통과 |
| 1 | 실패·불완전·건너뜀이 있거나 재현 검증이 막음 | — |
| 2 | 실행 전 검사 차단(실행 안 함) | 차단 |
| 3 | 다른 실행이 전역 설정 잠금을 잡고 있음 | — |
| 5 | 사람 승인 대기. 실행 안 함, 또는 `QA_ALLOW_UNAPPROVED=1`로 실행해 판정은 모두 통과 | 사람 승인 대기 |

각본 결과: `pass` · `fail` · `incomplete`(미실행 항목·서명 불일치 근거) · `skipped`(건너뛴 항목이 있고 스크립트가 사람 승인 상태가 아님).

## qa.config

zsh로 source한다. 경로는 앱 레포 루트 기준.

| 키 | 뜻 | 기본 |
|---|---|---|
| `QA_PROJECT` / `QA_WORKSPACE` | 빌드할 프로젝트 또는 워크스페이스(하나) | — |
| `QA_SCHEME`, `QA_CONFIGURATION` | 스킴, 빌드 구성 | —, Debug |
| `QA_APP_NAME`, `QA_BUNDLE_ID` | 결과물 .app 이름, 번들 ID(비우면 Info.plist) | 스킴 이름, 자동 |
| `QA_REQUIRED_FILES` | 빌드 전에 있어야 하는 파일(값은 읽지 않음) | () |
| `QA_CONDITIONS` | 조건 이름 → `"기기 이름[;글씨 크기]"` | — |
| `QA_INPUT_LANG` | 화면 키보드 자판 팩(`scripts/lib/keyboard/<언어>.py`) | ko |
| `QA_LAUNCH_ARGS` | 앱 실행 인자 | () |
| `QA_STATUS_BAR_TIME` | 상태 표시줄 시각 고정 | 9:41 |
| `QA_DAY_BOUNDARY_HOUR` | 앱의 하루가 바뀌는 시각(시). 그 전에 돌리면 경고 | 없음 |
| `QA_KEEP_RUNS`, `QA_KEEP_DAYS` | 결과 보존: 최근 N회 또는 D일 | 10, 14 |
| `QA_UNVERIFIABLE_CASE_MAX`, `QA_UNVERIFIABLE_RUN_MAX` | 재현 검증의 검증 불가 비율 상한(%). 넘으면 막음 | 30, 20 |
| `QA_DRIVER` | 실행 도구 어댑터(`scripts/lib/driver/<이름>.sh`) | axe |

환경 변수: `QA_ALLOW_UNAPPROVED=1`(엔진 시험용, 위 참고), `UI_TIMEOUT`(기다림 기본 초, 10).

## 폴더(앱 레포의 qa/)

```
qa.config  states.sh  flows.sh          설정, 준비 상태, 동작 묶음
cases/QA-NN-*.md                        각본(합격 기준). cases/.approved*  승인 기록
steps/QA-NN.sh                          스크립트. steps/.changes/  스크립트 변경 diff
gaps.json gaps.log gaps.snapshot        질문·답·규칙의 쓰임
results/<시각>-<조건>/                    실행 결과(index.html, REPORT.md, 각본별 영상·근거). results/latest
work/<ID>/                              새 각본 파이프라인 상태(pipeline.json, locate.json)
judgments/                              반영된 눈으로 확인 판단
```
