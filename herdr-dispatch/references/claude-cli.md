# claude 플래그

> **확인일: 2026-10-14** (doctor·로컬 실측만. 공식 문서·pane 교차 확인은 2026-10-09) · Claude Code 2.1.299 · 출처: 맨 아래 URL + `claude --help`
> 재검증 절차는 `verify.md`. 이 파일은 claude pane이 검증한다.

`herdr agent start ... --kind claude -- <여기>`에 넣는 인자.

| | |
|---|---|
| 모델 | `--model haiku\|sonnet\|opus\|fable\|best\|opusplan` |
| 추론 | `--effort low\|medium\|high\|xhigh\|max` (기본은 모델별 — 현재 `opus`·`sonnet`·`haiku`가 가리키는 5.5 세대는 `medium`, 그 이전 세대는 `high`) |
| 권한 | `--permission-mode auto --disallowedTools "Edit,Write,NotebookEdit,ExitPlanMode"` (읽기 전용 — **`plan` 아님**, 아래 경고) · `--permission-mode auto` (편집 + 분류기 검토) |

```bash
herdr agent start reviewer --kind claude --pane <pane-id> \
  -- --model sonnet --effort high --permission-mode auto \
     --disallowedTools "Edit,Write,NotebookEdit,ExitPlanMode"
```

## 모델 별칭은 낡지 않는다

`sonnet`은 항상 최신 Sonnet을 가리킨다. 버전 번호를 쓰지 말 것. 다만 **가리키는 버전과 그 버전의 기본 effort**는 바뀌므로, 아래 표는 재검증 대상이다.

| 별칭 | 지금 가리키는 것 (Anthropic API 기준) |
|---|---|
| `haiku` | Haiku 5.5 (v2.1.293+) |
| `sonnet` | Sonnet 5.5 (v2.1.284+) |
| `opus` | Opus 5.5 (v2.1.280+) |
| `fable` | Fable 5.1 (v2.1.257+) |
| `best` | `fable`이 있으면 그것, 없으면 `opus` |
| `opusplan` | 계획은 `opus`, 실행은 `sonnet` |

## 권한 모드

여섯 개이고, 우리가 쓰는 건 `auto` 하나다 (읽기 전용은 여기에 도구 차단을 더한다):

| 모드 | 안 묻고 실행되는 것 |
|---|---|
| `manual` (설정 파일에서는 `default`) | 읽기만 |
| `plan` | 읽기와 읽기용 bash만. 웹 조회·쓰기 bash는 묻는다. 끝에 계획이 승인되면 편집이 풀린다 |
| `acceptEdits` | 편집 + `mkdir/touch/rm/mv/cp/sed`. **그 외 bash는 전부 물어본다** |
| `auto` | 전부. 분류기가 사람 대신 심사하고, 위험 판정일 때만 멈춘다 |
| `dontAsk` | 읽기 + `allow` 규칙. 물어보는 대신 **거부**한다 |
| `bypassPermissions` | 전부. 격리된 컨테이너 전용 |

`acceptEdits`를 "편집 허용"으로 쓰면 안 된다 — bash에서 멈춘다. 편집 역할은 `auto`다.

**읽기 전용은 `plan`이 아니라 `auto` + 편집 도구 차단이다.** `plan`은 "편집하기 전에 계획을 세우는 단계"이지 읽기 전용 모드가 아니다.

> **⚠ plan 모드 리뷰어가 문서를 고쳤다** (2026-10-14 실제 사고). plan으로 띄운 리뷰어가 리뷰 결과를 수정 계획으로 만들어 `ExitPlanMode`로 승인을 요청했고, pane 화면에서 승인되자 auto 모드로 바뀌어 문서 6개를 편집했다. 이와 별개로 plan은 WebFetch·WebSearch마다 승인을 물어 pane이 자주 `blocked`가 된다.

`--disallowedTools`의 차단은 모드와 무관하게 세션 내내 유지된다. 2026-10-14 실측 (Claude Code 2.1.299, sonnet):

| 시도 | 결과 |
|---|---|
| Edit·Write | 거부 — `No such tool available: Edit. Edit is disabled for this session, in subagents as well as here.` |
| shift+tab으로 `acceptEdits`로 바꾼 뒤 Edit | 여전히 거부 |
| WebFetch·WebSearch | 승인 없이 실행 |
| bash `sed -i` | **실행됨** — 막히지 않는다 |

bash로 파일을 쓰는 길은 남는다. 읽기 전용 역할의 프롬프트에는 "파일 수정·외부 게시(gh/git push/코멘트) 금지"를 반드시 적는다.

**`auto`는 모델 제약이 있다**: Opus 4.6+ / Sonnet 4.6+ / Haiku 5.5 / Fable만 지원한다. 현재 별칭은 전부 통과한다. 읽기 전용 역할도 `auto`로 띄우므로 이 제약은 모든 역할에 걸린다 — 4.6 미만 모델은 리뷰어로도 못 쓴다.

**`bypassPermissions`는 시작할 때만 켤 수 있다.** 나중에 올릴 수 없으니 `agent start` 시점에 정해야 한다.

auto 모드에서도 분류기가 기본 차단하는 것들이 있다 — force push, `git reset --hard`, `git clean -fd`, `curl | bash`, 프로덕션 배포, `terraform destroy` 류. 걸리면 pane이 `blocked`가 된다. **프롬프트를 0으로 만드는 모드는 없다.**

## 처음 보는 폴더는 시작부터 멈춘다

claude가 한 번도 연 적 없는 경로를 `--cwd`로 주면 "Is this a project you created or one you trust?" 신뢰 확인 화면에서 시작한다. herdr는 `agent_not_ready` ("blocked during startup")를 돌려준다 (2026-10-14 확인). 이 화면도 사용자 몫이다 — 이미 연 적 있는 레포 안에서 띄우거나, 사용자에게 한 번 열어 달라고 한다.

## 출처

- https://code.claude.com/docs/en/model-config — 별칭 해석, effort 단계와 기본값, 맨 아래 "Version history" 표
- https://code.claude.com/docs/en/permission-modes — 권한 모드, auto 지원 모델, 분류기 차단 목록
- https://claude.com/blog/claude-model-and-effort-level-in-claude-code — 어느 축을 올릴지 (roles.md의 원칙)
