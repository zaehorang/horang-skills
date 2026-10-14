---
name: deck-export
description: 발표 덱 HTML을 16:9 규격 PDF로 내보내고 용지 규격을 검증합니다. 사용자가 발표자료를 PDF로 만들어 달라거나 제출용 파일로 뽑아 달라고 할 때 사용합니다.
---

# deck-export

```bash
python3 <skill-dir>/scripts/deck_export.py <deck.html> [-o out.pdf]
```

출력은 **960×540pt (13.333×7.5in, 정확히 16:9)** 여야 한다. 스크립트가 확인하고,
아니면 오류로 끝난다.

## 실패하면

거의 항상 `@media print` 문제다. 먼저 진단한다.

```bash
python3 <skill-dir>/scripts/deck_verify.py <deck.html>
```

| 증상 | 원인 |
|---|---|
| 다단 레이아웃이 1열로 무너짐 | 반응형 `@media` 에 `screen` 한정이 없어 인쇄에 적용됨 |
| A4 세로로 축소·분할 | `@page{size:1280px 720px;margin:0}` 없음 |
| 배경·색이 전부 하얗게 | `print-color-adjust:exact` 없음 |
| 페이지가 작게 한쪽에 몰림 | `.deck{transform:none!important}` 없어 인라인 scale이 살아남음 |

## 결과 확인

뽑은 뒤 페이지 수와 규격을 사용자에게 보고한다. 내용이 많이 바뀐 경우에는
몇 페이지를 실제로 열어 눈으로 확인하고 이상이 없는지 말한다.

## 파일 이름 · 마지막 정상본 보존

**직전에 뽑은 PDF를 덮어쓰지 않는다.** 발표 직전의 수정은 실패할 수 있고, 그때
되돌아갈 곳이 필요하다. 실제로 "시간 안에 안 되면 그대로 발표한다" 는 상황이 생긴다.

```
presentation.pdf        ← 처음 뽑은 것
presentation_v2.pdf     ← 수정본
presentation_v3.pdf     ← 그다음
```

- 새로 뽑을 때마다 번호를 올린다. 기존 파일은 지우지 않는다
- 어느 것이 지금 발표 가능한 최신본인지 사용자에게 말한다
- 발표용과 제출용을 따로 요구하면 파일을 나눠서 뽑는다

## 여러 PDF 합치기

마지막 장을 따로 만들어 붙이는 경우, 규격이 같아야 그대로 병합된다.

```bash
"/System/Library/Automator/Combine PDF Pages.action/Contents/Resources/join.py" \
  -o 최종.pdf 본편.pdf 마지막장.pdf
```

## 경계

- 사용자가 요청할 때만 뽑는다. 덱을 고친 뒤 자동으로 재생성하지 않는다.
- PDF를 만들려고 덱의 디자인을 바꾸지 않는다. 인쇄 CSS만 손댄다.
