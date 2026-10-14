#!/usr/bin/env python3
"""슬라이드의 텍스트 숫자를 JSON/CSV 근거와 대조한다 (표준 라이브러리만).

사용: deck_numbers.py deck.html evidence.json [data.csv ...]
      [--ignore-pages] [--ignore-years] [--ignore-times] [--ignore-regex PATTERN] [--json]
이미지·생성 콘텐츠·실행 후 삽입되는 숫자는 읽지 못한다. 값의 존재만 확인하며
주장, 단위, 분모, 계산식의 타당성은 사람이 확인한다. 개수 정수는 정확히 대조하고,
소수는 화면의 자릿수로 근거를 반올림한다. % 표시는 비율 근거도 허용한다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from html.parser import HTMLParser
from pathlib import Path

NUMBER = re.compile(r'(?<![\d.])(?:(?<![A-Za-z0-9])[+−-])?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?\s*%?(?!\.?\d)')
SCALAR = re.compile(r'[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?%?')


def decimal(text: str) -> Decimal:
    return Decimal(text.strip().rstrip('%').strip().replace(',', '').replace('−', '-'))


class DeckText(HTMLParser):
    """정적 HTML의 slide별 텍스트. 주석·style·script·명시적 숨김을 제외한다."""
    def __init__(self, ignore_pages: bool = False):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.slides = []
        self.current = None
        self.ignore_pages = ignore_pages

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        hidden = (tag in {'script', 'style', 'template'} or 'hidden' in attrs
                  or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', attrs.get('style', ''), re.I))
                  or (self.ignore_pages and 'page' in classes))
        if tag == 'section' and 'slide' in classes:
            self.slides.append([])
            self.current = len(self.slides) - 1
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append((tag, hidden, tag == 'footer' or 'foot' in classes))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag == 'section' and not any(t == 'section' for t, _, _ in self.stack):
            self.current = None

    def handle_data(self, data):
        if self.current is not None and not any(hidden for _, hidden, _ in self.stack):
            # 슬래시 비율은 본문 데이터일 수 있다. 푸터 안의 독립된 정수 N / M만
            # 페이지 표기로 취급한다 (.page 요소는 위에서 통째로 제외).
            if (self.ignore_pages and any(location for _, _, location in self.stack)
                    and re.fullmatch(r'\s*\d+\s*/\s*\d+\s*', data)):
                return
            self.slides[self.current].append(data)


def load_evidence(paths: list[Path]) -> set[Decimal]:
    values = set()
    def add(value):
        if isinstance(value, dict):
            for item in value.values():
                add(item)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif not isinstance(value, bool) and value is not None:
            token = str(value).strip()
            if SCALAR.fullmatch(token):
                num = decimal(token)
                if num.is_finite():
                    values.add(num)
                    if token.endswith('%'):
                        values.add(num / 100)
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            if path.suffix.lower() == '.json':
                add(json.load(stream, parse_float=Decimal, parse_int=Decimal))
            elif path.suffix.lower() == '.csv':
                for row in csv.reader(stream):
                    add(row)
            else:
                raise ValueError(f'JSON 또는 CSV가 필요하다: {path}')
    return values


def supported(token: str, evidence: set[Decimal]) -> bool:
    value = decimal(token)
    candidates = evidence | {n * 100 for n in evidence} if token.strip().endswith('%') else evidence
    if value in candidates:
        return True
    if '.' not in token and 'e' not in token.lower() and not token.strip().endswith('%'):
        return False  # 정수 개수를 반올림으로 정당화하지 않는다.
    with localcontext() as context:
        context.prec = max(50, len(value.as_tuple().digits) + abs(value.as_tuple().exponent) + 10)
        for num in candidates:
            try:
                if num.quantize(Decimal(1).scaleb(value.as_tuple().exponent), rounding=ROUND_HALF_UP) == value:
                    return True
            except InvalidOperation:
                continue
    return False


def audit(src: str, evidence: set[Decimal], *, ignore_pages=False, ignore_years=False,
          ignore_times=False, ignore_regex=None) -> list[dict]:
    parser = DeckText(ignore_pages)
    parser.feed(src)
    output = []
    for page, chunks in enumerate(parser.slides, 1):
        text = ' '.join(chunks)
        patterns = []
        if ignore_pages:
            patterns += [r'(?<![\w.])\d+(?:\s*[·,~-]\s*\d+)*\s*(?:쪽|장|페이지)']
        if ignore_years:
            patterns += [r'\b(?:19|20)\d{2}(?:년도|년)?(?!\w)']
        if ignore_times:
            patterns += [r'\b\d{1,2}:\d{2}(?::\d{2})?\b', r'(?:오전|오후)?\s*\d+(?:\.\d+)?\s*(?:시간|시|분|초)(?!\w)']
        if ignore_regex:
            patterns += [ignore_regex]
        for pattern in patterns:
            text = re.sub(pattern, ' ', text)
        numbers = list(dict.fromkeys(m.group().strip() for m in NUMBER.finditer(text)))
        missing = [n for n in numbers if not supported(n, evidence)]
        output.append({'slide': page, 'numbers': numbers, 'unsupported': missing})
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('deck', type=Path)
    ap.add_argument('evidence', nargs='+', type=Path)
    for option in ('pages', 'years', 'times'):
        ap.add_argument('--ignore-' + option, action='store_true')
    ap.add_argument('--ignore-regex', help='비데이터 텍스트를 제외할 정규식')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    try:
        rows = audit(args.deck.read_text(encoding='utf-8'), load_evidence(args.evidence),
                     ignore_pages=args.ignore_pages, ignore_years=args.ignore_years,
                     ignore_times=args.ignore_times, ignore_regex=args.ignore_regex)
    except (OSError, ValueError, InvalidOperation, re.error) as exc:
        print(f'실행 불가: {exc}', file=sys.stderr)
        return 2
    if not rows:
        print('실행 불가: .slide 슬라이드가 없다', file=sys.stderr)
        return 2
    count = sum(len(row['unsupported']) for row in rows)
    if args.json:
        print(json.dumps({'slides': rows, 'unsupported_count': count}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['slide']}장: 근거에 없는 숫자 " + (', '.join(row['unsupported']) or '없음'))
        print(f'총 {len(rows)}장 · 근거에 없는 숫자 {count}개 (값 존재 검사; 이미지 숫자는 별도 확인)')
    return 1 if count else 0


if __name__ == '__main__':
    raise SystemExit(main())
