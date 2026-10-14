# codex 플래그

> **확인일: 2026-10-14** (doctor·로컬 실측만. 공식 문서·pane 교차 확인은 2026-10-09) · codex-cli 0.162.1 · 출처: 맨 아래 URL + `codex --help` + `~/.codex/models_cache.json` + codex 에이전트 교차 확인
> 재검증 절차는 `verify.md`. 이 파일은 codex pane이 검증한다. 모델 목록은 `scripts/codex-models.py`로 언제든 덤프할 수 있다.

`herdr agent start ... --kind codex -- <여기>`에 넣는 인자.

| | |
|---|---|
| 모델 | `-m <이름>` — 아래 모델 표의 실제 모델명 |
| 추론 | `-c model_reasoning_effort=low\|medium\|high\|xhigh\|max\|ultra` — **항상 명시** (기본값이 모델별, 아래 표) |
| 권한 | `-s read-only -a never` (읽기 전용 — **`-a never` 필수**, 아래 경고) · `--approve-for-me` (편집 + 리뷰어 검토) |
| 속도 | `-c features.fast_mode=false` — **항상 붙인다**, 아래 설명 |

```bash
# 읽기 전용
herdr agent start reviewer --kind codex --pane <pane-id> \
  -- -m gpt-6.1-sol -c model_reasoning_effort=high -s read-only -a never -c features.fast_mode=false

# 편집
herdr agent start impl --kind codex --pane <pane-id> \
  -- -m gpt-6.1-sol -c model_reasoning_effort=medium --approve-for-me -c features.fast_mode=false
```

웹 검색이 필요하면 `--search`를 더한다. 검색은 서버 측이라 `read-only` 샌드박스와 무관하다.

## fast 모드를 끈다

`~/.codex/config.toml`에 `service_tier = "priority"`가 전역으로 켜져 있어서, 아무것도 안 주면 위임한 에이전트가 Fast 티어로 돈다 (상태 표시줄에 `fast`). Fast는 구독 한도를 **2.5배** 속도로 소모한다 (크레딧·PAYG는 2배). 위임 작업은 사람이 기다리지 않으니 속도 프리미엄을 낼 이유가 없다.

모델이 광고하는 tier는 `priority` 하나뿐이라 "표준"을 고르는 값은 없고, 기능을 끄는 `-c features.fast_mode=false`가 전역 설정을 이긴다. 2026-10-09에 실제로 띄워 확인: 플래그 없이 → `GPT-6.1-Sol medium fast`, 플래그 있으면 → `GPT-6.1-Sol medium`.

## 권한은 축이 두 개다

무엇에 닿을 수 있나(`-s`)와 언제 멈추나(`-a`).

| `-s` 샌드박스 | | `-a` 승인 정책 | |
|---|---|---|---|
| `read-only` | 수정·네트워크 불가 | `on-request` (기본) | 워크스페이스 밖 편집·네트워크는 승인 요청 |
| `workspace-write` | 워크스페이스 안 편집. 네트워크 기본 차단, `.git`·`.agents`·`.codex`는 읽기 전용 | `never` | 안 물어보고 실패로 반환 |
| `danger-full-access` | 샌드박스 없음 | (`granular` 테이블) | 프롬프트 종류별 설정. config.toml 전용, CLI 플래그로는 못 줌 |

`on-failure`는 폐기(deprecated), `untrusted`는 은퇴됐다 — 설정에 남아 있으면 codex가 시작을 거부할 수 있다.

> **⚠ `-s read-only`만으로는 읽기 전용이 아니다** (2026-09-28 실제 사고). `~/.codex/config.toml`에 `approvals_reviewer = "auto_review"`가 전역으로 켜져 있으면, 승인 정책이 기본 `on-request`로 남아 샌드박스 이탈 요청을 **자동 리뷰어가 승인**한다. PR #215 리뷰어가 이 경로로 네트워크를 쓰고 `gh api -X POST`로 사용자 계정 이름의 PR 리뷰 코멘트를 게시했다. 읽기 전용 역할은 반드시 `-a never`를 같이 줘서 이탈 요청이 승인 대신 실패로 돌아오게 한다. 프롬프트에도 "외부 게시(gh/git push/코멘트) 금지"를 명시한다.

`-s workspace-write`만 주면 `-a`가 기본 `on-request`로 남아 계속 물어본다. 편집 역할은 대신 **`--approve-for-me`** 를 쓴다 — `on-request` + `workspace-write` + 리뷰어 자동 검토를 한 번에 세팅한다.

**`--approve-for-me`는 `-s`·`-a`와 함께 못 쓴다.** 같이 주면 `agent start`가 파싱 에러로 죽는다:

```
error: the argument '--approve-for-me' cannot be used with '--sandbox <SANDBOX_MODE>'
```

리뷰어는 승인이 이미 필요한 것만 본다 — 샌드박스 이탈, 차단된 네트워크, `request_permissions`, 부작용 있는 앱·MCP 툴 호출. 데이터 유출·자격증명 탐색·보안 약화·파괴적 행위를 기준으로 판정한다. 모델 호출이 추가로 들고, **리뷰어가 샌드박스 이탈도 승인할 수 있다** — 사람이 없으니 경계는 리뷰어 판단에 달린다.

## 모델 표 — 실제 모델명이라 낡는다

| 모델 | 위치 | 추론 단계 (기본) | 은퇴 |
|---|---|---|---|
| `gpt-6-astra` | 가장 어려운 작업. 최상위 | `low`~`ultra` (`low`) | — |
| `gpt-6.1-sol` | 최신 워크호스. Astra에 가까운 성능을 더 싸게, 반복적인 장시간 작업에 권장 | `low`~`ultra` (`low`) | — |
| `gpt-6-sol` | 이전 세대 워크호스. 5.4/5.5의 공식 대체 | `low`~`ultra` (`medium`) | — |
| `gpt-6-luna` | 고volume·단순 작업용 효율 모델. 문서는 `high`에서 시작하라고 권함 | `low`~`max`, **`ultra` 없음** (`medium`) | — |
| `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` | 구세대. "롤아웃 동안 유지" | 위와 동일 | **미정** — 날짜 발표 안 됨 |
| `gpt-5.5` | 레거시. 은퇴일 당일(2026-10-14)에도 캐시에 숨김 상태로 남아 있었다 — 공식 문서로 은퇴 확인 전 | `low`~`xhigh` | **2026-10-14** (공지) |
| `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark` | 은퇴 | — | 지남 |

오늘 날짜가 은퇴일에 가깝거나 지났으면 사용자에게 알린다. gpt-5.6 계열은 날짜 없이 사라질 수 있으니 `agent start`가 모델명으로 실패하면 `scripts/codex-models.py`로 현재 목록을 보고 gpt-6 열로 옮긴다.

## 출처

- https://learn.chatgpt.com/docs/models — 라인업, 포지셔닝, 은퇴 공지
- https://learn.chatgpt.com/docs/agent-approvals-security — `-s`·`-a`, 자동 리뷰어
- https://learn.chatgpt.com/docs/config-file/config-reference — `service_tier`, `features.fast_mode`, `approval_policy`, `model_reasoning_effort`
- https://learn.chatgpt.com/docs/agent-configuration/speed — fast 모드 비용 배수
- https://learn.chatgpt.com/docs/agent-configuration/subagents — `ultra`와 자동 위임
- https://learn.chatgpt.com/docs/learn/best-practices — 가장 낮은 추론 강도부터 (roles.md의 원칙)
