#!/bin/zsh
# qa doctor: 실행에 필요한 도구·설정·기기·잠금을 점검한다. 읽기만 하고 아무것도 바꾸지 않는다.
#   doctor.sh [qa 폴더]      qa 폴더가 없으면 도구만 본다. FAIL이 있으면 exit 1
QA_DIR=${1:-}
ENGINE=${ENGINE:-${0:A:h:h:h}}; LIB=${LIB:-$ENGINE/scripts/lib}
fails=0
ok()   { print "OK    $*"; }
warn() { print "WARN  $*"; }
bad()  { print "FAIL  $*"; (( fails += 1 )); }
have() { command -v $1 >/dev/null; }

print "── 도구"
have zsh && ok "zsh $ZSH_VERSION" || bad "zsh 없음"
if have python3 && python3 -I -B -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then ok "python3 $(python3 -V 2>&1 | cut -d' ' -f2)"
else bad "python3 3.9 이상 없음"; fi
have perl && ok "perl" || bad "perl 없음(시각 계산·대기에 씀)"
have xcrun && ok "xcrun" || bad "xcrun 없음(Xcode 명령줄 도구)"
have xcodebuild && ok "xcodebuild" || bad "xcodebuild 없음"
xcrun simctl help >/dev/null 2>&1 && ok "simctl" || bad "simctl을 쓸 수 없음"
have axe && ok "axe $(axe --version 2>/dev/null)" || bad "실행 도구 axe 없음(scripts/lib/driver/axe.sh 참고)"
have ffmpeg && have ffprobe && ok "ffmpeg·ffprobe" || warn "ffmpeg·ffprobe 없음: 화면 안정 판정·근거 상자·영상 faststart가 약해짐"
have node && ok "node(엔진 시험의 페이지 논리 시험용)" || warn "node 없음: qa test의 페이지 논리 시험을 건너뜀"

print "── 전역 상태"
LOCK=/tmp/ios-video-qa.lock.d
if [[ -d $LOCK ]]; then
  lpid=$(cat $LOCK/pid 2>/dev/null)
  if [[ -n $lpid ]] && kill -0 $lpid 2>/dev/null; then warn "다른 실행이 잠금을 잡고 있음(pid $lpid)"
  else warn "죽은 실행의 잠금이 남아 있음(pid ${lpid:-?}, 원래 값 $(cat $LOCK/orig 2>/dev/null || print '기록 없음')). 다음 qa run이 회수한다"; fi
else ok "잠금 없음"; fi
hw=$(defaults read com.apple.iphonesimulator ConnectHardwareKeyboard 2>/dev/null || print "없음(기본)")
ok "시뮬레이터 하드웨어 키보드 연결 설정: $hw (실행 중에만 바꾸고 끝나면 되돌린다)"

if [[ -z $QA_DIR || ! -f $QA_DIR/qa.config ]]; then
  print "── 프로젝트: qa/qa.config를 찾지 못함(앱 레포에서 실행하거나 qa init)"
  (( fails )) && exit 1 || exit 0
fi
print "── 프로젝트 $QA_DIR"
REPO=${QA_DIR:h}
typeset -A QA_CONDITIONS QA_STATES
QA_REQUIRED_FILES=(); QA_PROJECT=""; QA_WORKSPACE=""; QA_SCHEME=""
if ! source $QA_DIR/qa.config 2>/dev/null; then bad "qa.config를 읽지 못함"; fi
if [[ -n ${QA_WORKSPACE:-} ]]; then [[ -d $REPO/$QA_WORKSPACE ]] && ok "워크스페이스 $QA_WORKSPACE" || bad "워크스페이스 없음: $QA_WORKSPACE"
elif [[ -n ${QA_PROJECT:-} ]]; then [[ -d $REPO/$QA_PROJECT ]] && ok "프로젝트 $QA_PROJECT" || bad "프로젝트 없음: $QA_PROJECT"
else bad "QA_PROJECT·QA_WORKSPACE가 비어 있음"; fi
[[ -n ${QA_SCHEME:-} ]] && ok "스킴 $QA_SCHEME" || bad "QA_SCHEME이 비어 있음"
for f in $QA_REQUIRED_FILES; do [[ -e $REPO/$f ]] && ok "필요한 파일 있음: $f" || bad "필요한 파일 없음: $f"; done
kb=$LIB/keyboard/${QA_INPUT_LANG:-ko}.py
[[ -f $kb ]] && ok "자판 팩 ${QA_INPUT_LANG:-ko}" || bad "자판 팩 없음: QA_INPUT_LANG=${QA_INPUT_LANG:-ko}"
source $LIB/sim.sh
(( ${#QA_CONDITIONS} )) || bad "QA_CONDITIONS가 비어 있음"
for name val in "${(@kv)QA_CONDITIONS}"; do
  dev=${val%%;*}
  if [[ -z $dev ]]; then bad "조건 '$name'의 기기 이름이 비어 있음"; continue; fi
  [[ -n $(sim_udid "$dev") ]] && ok "조건 '$name' → 기기 '$dev'" || bad "조건 '$name'의 기기 '$dev'가 이 Mac에 없음(시뮬레이터 이름 확인)"
done
[[ -f $QA_DIR/states.sh ]] && source $QA_DIR/states.sh 2>/dev/null
# 자동 각본의 준비 상태·조건·스크립트(각본 읽기는 casefile 한 곳에서)
while IFS=$'\t' read -r level msg; do
  case $level in FAIL) bad "$msg" ;; WARN) warn "$msg" ;; *) ok "$msg" ;; esac
done < <(python3 -I -B -c '
import os, sys
sys.path.insert(0, sys.argv[1])
import casefile
qa, states, conds = sys.argv[2], set(sys.argv[3].split("\x1f")), set(sys.argv[4].split("\x1f"))
n = 0
for f in sorted(os.listdir(os.path.join(qa, "cases"))):
    if not (f.startswith("QA-") and f.endswith(".md")):
        continue
    try:
        c = casefile.parse(os.path.join(qa, "cases", f))
    except Exception as e:
        print(f"FAIL\t{f}: 각본을 읽지 못함: {e}"); continue
    if c["manual"]:
        continue
    n += 1
    for e in casefile.validate(c):
        print(f"FAIL\t{e}")
    if c["header"]["준비"] not in states:
        print(f"FAIL\t{f}: 준비 상태 {c["header"]["준비"]!r}가 states.sh의 QA_STATES에 없음")
    for x in c["header"]["조건"]:
        if x not in conds:
            print(f"FAIL\t{f}: 조건 {x!r}가 qa.config의 QA_CONDITIONS에 없음")
    if not os.path.exists(os.path.join(qa, "steps", c["id"] + ".sh")):
        print(f"WARN\t{f}: 스크립트 없음(steps/{c["id"]}.sh)")
print(f"OK\t자동 각본 {n}개의 준비 상태·조건 확인")
' $LIB $QA_DIR "${(pj:\x1f:)${(@k)QA_STATES}}" "${(pj:\x1f:)${(@k)QA_CONDITIONS}}")
print "── 승인 상태(qa status 요약)"
python3 -I -B $LIB/approve.py status $QA_DIR 2>&1 | awk -F'\t' '/^QA-/{n[$2]++} END{for(k in n) printf "      %s %d\n", k, n[k]}'
(( fails )) && { print "FAIL ${fails}개"; exit 1; }
print "점검 통과"
