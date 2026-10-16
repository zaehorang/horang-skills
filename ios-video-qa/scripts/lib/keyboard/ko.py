"""한국어(두벌식) 자판 팩. 글자를 키 입력으로 바꾸고, 화면 키보드의 키 이름을 알려 준다.
자판 팩 인터페이스는 references/keyboard-packs.md(같은 세 명령, 같은 변수 이름).

    ko.py "안녕"              → dkssud               (하드웨어 키보드 키 문자열)
    ko.py --keys "안녕"       → ㅇ ㅏ ㄴ ㄴ ㅕ ㅇ (한 줄에 하나. 화면 키보드 키 label)
    ko.py --labels            → 화면 키보드의 특수 키·전환 규칙(zsh 변수)

특수 키 label 일부(언어 전환 키 등)는 시뮬레이터의 UI 언어를 따른다. 여기 값은 한국어 UI 기준이다.

한글 음절이 아닌 문자(숫자, 공백 등)는 그대로 둔다. 로마자는 이 자판에서 입력하지 못한다.
"""

import sys

INITIALS = ["r", "R", "s", "e", "E", "f", "a", "q", "Q", "t", "T", "d", "w", "W", "c", "z", "x", "v", "g"]
VOWELS = ["k", "o", "i", "O", "j", "p", "u", "P", "h", "hk", "ho", "hl", "y", "n", "nj", "np", "nl", "b", "m", "ml", "l"]
FINALS = ["", "r", "R", "rt", "s", "sw", "sg", "e", "f", "fr", "fa", "fq", "ft", "fx", "fv", "fg",
          "a", "q", "qt", "t", "T", "d", "w", "c", "z", "x", "v", "g"]
JAMO = dict(zip("ㄱㄲㄳㄴㄵㄶㄷㄸㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅃㅄㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ",
                ["r", "R", "rt", "s", "sw", "sg", "e", "E", "f", "fr", "fa", "fq", "ft", "fx", "fv", "fg",
                 "a", "q", "Q", "qt", "t", "T", "d", "w", "W", "c", "z", "x", "v", "g"]))
JAMO.update(zip("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ", VOWELS))
KEY_LABELS = {v: k for k, v in JAMO.items() if len(v) == 1}

# 화면 키보드(iOS 한국어 자판)의 특수 키. core.sh가 source한다
LABELS = {
    "KB_SHIFTED": "ㄲㄸㅃㅆㅉㅒㅖ",      # shift 뒤에만 나오는 키
    "KB_PROBE_KEYS": "ㅂ ㅃ",            # 이 키가 보이면 이 언어 자판이 떠 있는 것
    "KB_GLOBE_LABEL": "다음 키보드",      # 언어 전환 키
    "KB_OTHER_LANG_LABEL": "한국어",      # 다른 언어 자판이 떠 있을 때 전환 키의 label
    "KB_DELETE_LABEL": "Delete",
    # 키보드 UI 요소의 식별자(iOS 내부 이름. 언어와 무관하지만 자판 팩이 한 곳에서 관리한다)
    "KB_RETURN_ID": "Return",
    "KB_DELETE_ID": "delete",
    "KB_SHIFT_ID": "shift",
    "KB_MORE_ID": "more",
    "KB_SPACE_ID": "space",
    "KB_ASSISTANT_ID": "SystemInputAssistantView",   # 예상 단어 막대(키보드 윗변)
    # 'more' 키의 label: 숫자·기호 자판일 때(누르면 글자 자판으로) — 시뮬레이터 UI 언어별
    "KB_MORE_TO_LETTERS": "letters 문자 ABC 가나다",
    "KB_LANG_NAME": "한국어",   # 언어 전환 키를 길게 눌렀을 때 목록에 보이는 이 자판의 이름
}


def to_keys(text):
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(INITIALS[code // 588] + VOWELS[(code % 588) // 28] + FINALS[code % 28])
        else:
            out.append(JAMO.get(ch, ch))
    return "".join(out)


def to_key_labels(text):
    return [KEY_LABELS.get(k, k) for k in to_keys(text)]


if __name__ == "__main__":
    if sys.argv[1:2] == ["--keys"]:
        print("\n".join(to_key_labels(" ".join(sys.argv[2:]))))
    elif sys.argv[1:2] == ["--labels"]:
        for k, v in LABELS.items():
            print(f"{k}='{v}'")
    else:
        print(to_keys(" ".join(sys.argv[1:])))
