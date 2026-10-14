# 재검증 절차

> `roles.md`·`claude-cli.md`·`codex-cli.md`의 모델명·추론 단계·기본값·권한 플래그, 그리고 이 스킬이 기대는 herdr CLI 문법이 아직 맞는지 확인하고 갱신한다.
> 마지막 수행: **2026-10-09** (약 30분) · herdr 0.9.3. 주기적으로 돌리지 않는다 — `agent start`가 실패했거나 사용자가 요청했을 때만.

원칙 하나: **claude 쪽은 claude pane이, codex 쪽은 codex pane이 검증한다.** 자기 CLI의 도움말·설정·문서를 가장 잘 읽고, 자기 세션의 상태 표시줄로 실제 값을 확인할 수 있기 때문이다. 이 절차를 돌리는 쪽이 이미 claude라면 claude 쪽은 직접 해도 되지만, 두 pane을 나란히 띄워 병렬로 돌리는 편이 빠르다. herdr 쪽(0번)은 pane이 필요 없고, 조율하는 쪽이 직접 보고 결과를 받아 파일을 고친다.

## 시작: doctor를 돌린다

```bash
python3 -I scripts/doctor.py
```

0번과 1번의 결정적인 부분(herdr 상태·문법·동기화·최신 릴리스, CLI 플래그 존재, 캐시 대 역할표, 은퇴일, 전역 설정, 확인일)을 한 번에 본다. WARN/FAIL 줄이 어디를 먼저 볼지 알려준다. 아래 절들은 doctor가 **못 보는 것** — 문서의 의미 변화, 공식 문서, 실측 — 을 위한 것이므로 doctor가 전부 OK여도 건너뛰지 않는다.

## 0. herdr부터 본다

이 스킬은 herdr의 세 가지에 기댄다. 셋 다 `herdr update`나 세션 시작 훅으로 조용히 바뀐다.

**바이너리와 서버.** 클라이언트와 서버 버전이 어긋나면 새 플래그가 서버에서 거부된다.

```bash
herdr status            # restart_needed / server_binary_stale 가 yes면 사용자에게 재시작을 요청
```

**CLI 문법.** 이 스킬이 쓰는 형태가 그대로 있는지 도움말에서 확인한다:

```bash
herdr agent | grep -E 'agent (start|prompt|read)'   # `-- <agent-args...>` 통과, kinds에 claude|codex, --wait --timeout, --source
herdr pane  | grep -E 'pane (split|run|close)'        # --cwd, --no-focus
```

실제로 띄웠을 때 인자가 그대로 전달되는지는 `agent start` 응답의 `.result.argv`로 본다 — herdr가 자기 플래그를 끼워 넣지 않는다는 뜻이다 (2026-10-09 확인: codex에 준 인자가 1:1로 나옴).

**herdr 공식 스킬.** 세션 시작 훅(`herdr-setup/sync-skill.sh`)이 `herdr --skill` 출력과 `~/.agents/skills/herdr/SKILL.md`를 맞추고, 바뀌면 `.bak.<timestamp>`를 남긴다. 이 스킬의 SKILL.md가 "herdr 스킬에서 읽는다"고 미룬 규칙이 바뀌었는지 최신 백업과 diff로 본다:

```bash
diff -q <(herdr --skill) ~/.agents/skills/herdr/SKILL.md || echo "훅이 안 돌았다 — sync-skill.sh 먼저"
diff ~/.agents/skills/herdr/SKILL.md.bak.$(ls ~/.agents/skills/herdr/ | grep -o 'bak\.[0-9]*' | sort | tail -1 | cut -d. -f2) ~/.agents/skills/herdr/SKILL.md
```

diff에서 볼 것: `--no-focus`·`--cwd` 미상속 규칙, `blocked` UI에 에이전트가 답하면 안 된다는 규칙, agent 상태 어휘(`idle`/`working`/`blocked`/`done`/`unknown`), `agent prompt --wait`의 대기 의미, 읽기 `--source` 종류. 바뀌었으면 SKILL.md 3·4절과 이 파일의 2번 명령을 맞춘다. 2026-10-04 갱신분은 `machine` 명령만 바뀌어 이 스킬과 무관했다.

**공식 문서와 릴리스 노트.** 로컬 도움말은 "지금 깔린 버전"만 말한다. 더 새 버전이 있는지, 그 버전이 claude·codex 감지나 `blocked` 판정을 바꿨는지는 릴리스 노트에만 적힌다.

```bash
gh api repos/herdrdev/herdr/releases --paginate -q '.[] | select(.prerelease|not) | "\(.tag_name)\t\(.published_at)"' | head -5
gh api repos/herdrdev/herdr/releases/latest -q '.body'    # 설치본보다 새 버전이 있으면 본문을 읽는다
```

릴리스 노트에서 볼 것: `agent`·`pane` 명령과 플래그 변경, **Breaking changes** 절, "Claude Code"·"Codex" 감지 변경(`working`/`idle`/`blocked` 판정이 바뀌면 `--wait`의 결과가 달라진다). 설치본이 뒤처져 있으면 사용자에게 `herdr update`를 제안하되 직접 돌리지 않는다 — 서버 재시작이 따라오고 pane 프로세스에 영향을 준다.

WebFetch로 볼 문서 (사이트에 CLI 레퍼런스 페이지는 따로 없다):

| 문서 | 확인할 것 |
|---|---|
| https://herdr.dev/docs/agent-automation/ | `agent start`·`pane split`·`agent prompt --wait`·`agent read --source`의 의미, `blocked` 에이전트에 대한 규칙, 새로 생기거나 폐기된 항목 |
| https://herdr.dev/docs/agents/ | 지원 에이전트 목록에 `claude`·`codex`가 있는지, 상태 어휘, codex의 `unknown` 폴백 |
| https://github.com/herdrdev/herdr/releases | 위 `gh api`와 같은 내용. 브라우저로 볼 때 |

2026-10-09 확인: 설치본 0.9.3 = 최신 안정판(2026-09-29). 0.9.0~0.9.3 노트에서 이 스킬이 쓰는 명령·플래그 변경 없음. codex 감지 수정(출력 중 idle 오판, 인용된 확인 문구를 blocked로 오판)은 전부 `--wait` 정확도를 높이는 쪽이라 반영할 것 없음.

## 1. 로컬 CLI부터 본다 (가장 싸고 정확)

```bash
claude --version; codex --version
claude --help | grep -A3 -E 'model|effort|permission-mode'   # 별칭 예시, effort 단계, 권한 모드 선택지
codex --help  | grep -A3 -E 'sandbox|ask-for-approval|approve-for-me'
python3 -I scripts/codex-models.py                            # codex 모델 목록·추론 단계·기본값·tier
grep -nE 'service_tier|approval|model' ~/.codex/config.toml   # 전역 설정이 뭘 켜 두었는지
```

codex 모델별 추론 단계와 기본값은 로컬 캐시가 공식 문서보다 정확하다 (문서는 UI 라벨만 쓴다). `visibility: hide`는 선택기에서 숨긴 모델(은퇴 임박 또는 내부용)이다.

## 2. 벤더별 pane을 띄운다

둘 다 읽기 전용 역할 설정이다 (claude는 편집 도구 차단 — bash 쓰기는 열려 있다. codex는 샌드박스). 웹 검색은 서버 측이라 읽기 전용 권한과 무관하다.

```bash
herdr pane split --current --direction right --cwd "$PWD" --no-focus            # → <claude-pane>
herdr pane split --pane <claude-pane> --direction down --cwd "$PWD" --no-focus   # → <codex-pane>

herdr agent start claude-verify --kind claude --pane <claude-pane> \
  -- --model sonnet --effort medium --permission-mode auto --disallowedTools "Edit,Write,NotebookEdit,ExitPlanMode"
herdr agent start codex-verify --kind codex --pane <codex-pane> \
  -- -m gpt-6.1-sol -c model_reasoning_effort=medium -s read-only -a never --search -c features.fast_mode=false

herdr agent prompt claude-verify "<claude 질문>" --wait --timeout 600000
herdr agent prompt codex-verify  "<codex 질문>"  --wait --timeout 600000
herdr agent read claude-verify --source recent-unwrapped --lines 400
herdr agent read codex-verify  --source recent-unwrapped --lines 400
```

프롬프트 공통 문구: "읽기 전용. 외부 게시(gh/git push/코멘트) 금지. 주장마다 URL. 검증 못 하면 추측 말고 그렇다고 써라." 그리고 각자 자기 파일(`references/claude-cli.md` / `references/codex-cli.md`)의 경로를 주고 **"이 파일에서 틀린 줄을 찾아라"** 고 시킨다. 백지에서 다시 쓰게 하는 것보다 diff가 정확하다.

**claude pane에 물어볼 것** — `claude-cli.md`의 각 표:
- `--model` 별칭(`haiku`/`sonnet`/`opus`/`fable`/`best`)이 지금 가리키는 버전. model-config 문서 맨 아래 "Version history" 표가 정답이다 (페이지가 길어 `offset`으로 이어 읽어야 한다)
- effort 단계와 **모델별 기본값**
- `--permission-mode` 선택지 이름, auto 모드 지원 모델, 분류기 기본 차단 목록
- 자기 세션의 `/model`·`/effort` 현재값

**codex pane에 물어볼 것** — `codex-cli.md`의 각 표:
- 현재 모델 ID 전체와 포지셔닝, 은퇴 공지 **원문 인용**
- 모델별 effort 단계와 기본값, `ultra`의 의미
- `-s`·`-a`·`--approve-for-me` 변경점, 폐기된 값
- `~/.codex/config.toml`이 켜 둔 것(`service_tier`, `approvals_reviewer`)과 그걸 끄는 플래그

에이전트가 **자기 모델을 모를 수 있다** (codex는 2026-10-09에 "알 수 없다"고 답했다). 상태 표시줄(`herdr pane read --source visible`)의 `GPT-x medium fast` 같은 줄로 확인한다.

## 3. 공식 문서는 WebFetch로 직접도 본다

pane의 답은 교차 확인이지 정본이 아니다. 각 벤더 파일 맨 아래 "출처" URL을 WebFetch로 열어 핵심 표를 직접 대조한다. 이 페이지들에는 "최종 수정일"이 없어서 "오늘 서빙되는 내용"까지만 보장된다. 10만 자가 넘는 페이지는 `offset`으로 이어 읽는다.

## 4. 플래그는 실제로 띄워서 검증한다

문서가 "된다"고 해도 전역 설정과 충돌하면 다르게 동작한다. 의심스러운 플래그는 pane에서 `agent start` 후 상태 표시줄을 읽는다. 프롬프트를 보내지 않으면 토큰은 거의 안 든다.

```bash
herdr agent start t --kind codex --pane <pane-id> -- -m gpt-6.1-sol -c features.fast_mode=false
herdr pane read <pane-id> --source visible --lines 40 | grep -iE 'GPT-|fast'
```

claude 읽기 전용 플래그는 같은 방식으로 띄운 뒤, 닫기 전에 세 가지를 시킨다. 신뢰 확인 화면을 피하려면 이 레포 안에서 띄운다.

1. Edit → 거부여야 한다
2. `herdr pane send-keys <pane-id> shift+tab`을 상태 표시줄이 `accept edits`가 될 때까지 보낸 뒤 Edit → 여전히 거부여야 한다
3. WebFetch → 승인 없이 실행돼야 한다

bash `sed -i`는 실행된다 — 알려진 한계이고 `claude-cli.md` 표에 적혀 있다. 이게 막히기 시작했으면 표를 고친다.

```bash
herdr agent prompt t "/exit"; herdr pane close <pane-id>
```

## 5. 파일을 고친다

- `claude-cli.md`, `codex-cli.md`: 표 내용과 맨 위 **확인일**·CLI 버전
- `roles.md`: 역할표의 codex 모델명, claude "기본"이 뜻하는 effort 값, 확인일
- `SKILL.md` 3절 예시의 모델명. herdr 규칙이 바뀌었으면 3·4절
- 이 파일의 "마지막 수행" 날짜·herdr 버전과 아래 변경 기록
- 마지막으로 `scripts/doctor.py`를 다시 돌려 전부 OK인지 본다. 문서 표의 형식을 바꿨다면 doctor의 정규식도 같이 고친다 (모델 표의 `` `low`~`max` (`medium`) `` 꼴과 `**YYYY-MM-DD**` 은퇴일을 읽는다)

은퇴일이 없는 모델은 "미정"으로 두고 지어내지 않는다. 띄운 pane은 닫는다.

## 변경 기록

| 날짜 | 바뀐 것 |
|---|---|
| 2026-10-14 | doctor + 로컬 확인 (모델·플래그 표의 pane 교차 확인·공식 문서 대조는 안 함). claude 2.1.299·codex 0.162.1에서 플래그·모델 캐시 변화 없음. `gpt-5.5`는 은퇴 공지일이지만 캐시에 숨김으로 남아 은퇴 미확인. herdr 0.9.4 릴리스 노트에 이 스킬이 쓰는 명령·감지 변경 없음. claude 읽기 전용을 `plan` → `auto` + `--disallowedTools`로 (plan 리뷰어가 계획 승인 후 문서 6개를 편집한 사고, pane을 띄워 실측, 근거는 claude-cli.md). 처음 보는 폴더의 신뢰 확인 함정 추가 |
| 2026-10-09 | codex gpt-5.6 → gpt-6 세대 (`gpt-6.1-sol`, `gpt-6-luna` 신규). claude 5.5 세대 effort 기본값 `high`→`medium`. auto 모드에 Haiku 5.5 추가. `--permission-mode` 플래그명 `default`→`manual`. codex `-a on-failure` 폐기, `untrusted` 은퇴. fast 모드 끄기 규칙 추가. 파일을 벤더별로 분리. herdr 점검 절(0번) 추가 — herdr 0.9.3 기준 이 스킬이 쓰는 문법 전부 유효 |
| 2026-09-28 | codex 읽기 전용에 `-a never` 필수 (auto_review가 샌드박스 이탈을 승인한 사고) |
| 2026-09-20 | 최초 작성 |
