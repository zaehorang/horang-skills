# herdr-dispatch

herdr로 다른 pane에 일을 넘길 때 **모델 · 추론 강도 · 권한** 세 축을 의식적으로 골라서 띄운다.

## 왜 만들었나

기본값으로 아무 에이전트나 띄우면 세 가지가 반복됐다. 간단한 일에 큰 모델을 쓰고, 권한을 안 정해서 pane이 승인 대기(blocked)로 멈추고, codex가 fast 티어로 돌아 한도를 2.5배로 태운다. 매번 플래그를 기억에서 꺼내다 틀리니 role table로 굳혀야 했다.

## 무엇을 해주나

- 에이전트가 **필요한지부터 묻는다.** 명령 하나 돌리고 출력만 읽으면 되는 일은 에이전트 없이 `pane run`으로 끝낸다.
- 일을 역할로 쪼개고, `references/roles.md`의 role table에서 세 축을 고르고, 근거를 남긴다.
- 벤더별 플래그 문법 · 권한 모드 · 모델명은 `references/claude-cli.md`, `references/codex-cli.md`에 있다.
- 표는 낡는다. `scripts/doctor.py`가 설치된 CLI · 모델 캐시 · 전역 설정과 표를 몇 초 안에 대조하고, "모델 업데이트 확인해"라고 하면 `references/verify.md` 절차대로 claude pane과 codex pane이 각자 자기 벤더 문서를 공식 출처와 교차 확인한다.

## 어떻게 쓰나

`dev` bundle에 있다 → [설치](../docs/install.md). herdr pane 안(`HERDR_ENV=1`)에서만 동작한다.

> 옆 pane에서 리뷰어 띄워줘
> codex한테 시켜줘
> 디스패치 표 갱신해

절차는 [SKILL.md](SKILL.md)에 있다.

## 설계에서 정한 것

- **vendor 이름 규칙의 예외.** 이 repo는 본문에 도구 이름을 쓰지 않지만, 이 스킬은 herdr · claude · codex를 제어하는 것 자체가 목적이라 추상화하면 할 일이 없어진다 → [원칙](../docs/principles.md).
- **herdr CLI 사용법은 담지 않는다.** 그건 herdr 공식 스킬이 정본이다. 이 스킬은 그 위에 "무엇을 어떤 설정으로 띄울지"만 얹는다. 시작할 때 공식 스킬이 바이너리와 같은지 먼저 확인한다.
- **표를 믿지 않는다.** 모델명과 플래그는 몇 주면 낡는다. 그래서 검증을 스크립트(doctor)와 절차(verify)로 따로 두었고, 벤더별 pane이 자기 쪽만 재검증하게 했다.
- **사용자가 모델을 지정했으면 다시 고르지 않는다.** 승인 대기 화면에 대신 답하지 않고, 사용자가 만들지 않은 pane은 닫지 않는다.

## 한계

- herdr 밖에서는 쓸 수 없다.
- role table는 사용자가 쓰는 작업 유형을 기준으로 만든 것이라 다른 사람에게는 줄이 더 필요할 수 있다.
