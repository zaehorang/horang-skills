"""영어(US QWERTY) 자판 팩. 인터페이스는 ko.py와 같다(references/keyboard-packs.md).

    en.py "Hello"             → Hello                (하드웨어 키보드 키 문자열: 글자 그대로)
    en.py --keys "Hello"      → H e l l o            (한 줄에 하나. 화면 키보드 키 label)
    en.py --labels            → 화면 키보드의 특수 키·전환 규칙(zsh 변수)

대문자는 shift 뒤에 나오는 키로 본다(KB_SHIFTED). 특수 키 label 일부는 시뮬레이터의 UI 언어를 따른다. 여기 값은 영어 UI 기준이다.
"""

import string
import sys

LABELS = {
    "KB_SHIFTED": string.ascii_uppercase,  # shift 뒤에만 나오는 키
    "KB_PROBE_KEYS": "q w",                # 이 키가 보이면 이 언어 자판이 떠 있는 것
    "KB_GLOBE_LABEL": "Next keyboard",     # 언어 전환 키
    "KB_OTHER_LANG_LABEL": "English",      # 다른 언어 자판이 떠 있을 때 전환 키의 label
    "KB_DELETE_LABEL": "Delete",
    "KB_RETURN_ID": "Return",
    "KB_DELETE_ID": "delete",
    "KB_SHIFT_ID": "shift",
    "KB_MORE_ID": "more",
    "KB_SPACE_ID": "space",
    "KB_ASSISTANT_ID": "SystemInputAssistantView",   # 예상 단어 막대(키보드 윗변)
    "KB_MORE_TO_LETTERS": "letters ABC",             # 숫자·기호 자판의 'more' 키 label(누르면 글자 자판으로)
    "KB_LANG_NAME": "English",                       # 언어 전환 키를 길게 눌렀을 때 목록에 보이는 이 자판의 이름
}


def to_keys(text):
    return text


def to_key_labels(text):
    return list(text)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--keys"]:
        print("\n".join(to_key_labels(" ".join(sys.argv[2:]))))
    elif sys.argv[1:2] == ["--labels"]:
        for k, v in LABELS.items():
            print(f"{k}='{v}'")
    else:
        print(to_keys(" ".join(sys.argv[1:])))
