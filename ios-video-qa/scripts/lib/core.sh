# 동작 어휘. 각본 스크립트(steps/*.sh)와 프로젝트의 flows.sh·states.sh가 쓴다. run.sh가 source한다.
# 실행 도구는 직접 부르지 않고 driver/*.sh의 drv_* 함수만 쓴다. 앱 문구는 없다.
#
# run.sh가 정하는 변수
#   ENGINE(스킬 폴더), LIB(scripts/lib), QA_DIR, UDID, APP_PATH, BUNDLE_ID, OUT(이 각본의 결과 폴더), FIXTURES(앱 상태 스냅샷 폴더)
#   _QA_KEY(실행별 근거 서명 키. 내보내지 않고 판정기 호출에만 넘긴다. 스크립트는 읽을 수 없다: 실행 전 검사가 막는다)
#   KEYBOARD(software|hardware), QA_INPUT_LANG, QA_LAUNCH_ARGS(배열), QA_PHASE(prep|scenario)
#   QA_CASE_ID, QA_ITEMS, QA_STEP_*(각본 md에서)
#
# ── 판정 어휘(합격 기준을 확인하는 유일한 방법) ──
#   expect_present  @ID[,ID] "<설명>" [-t 초] <질의>      있어야 한다
#   expect_gone     @ID "<설명>" [-t 초] <질의>            없어야 한다(읽기 실패는 '없음'이 아니다)
#   expect_visible  @ID "<설명>" [-t 초] [--keyboard] <질의>  영역이 화면 안·잘림 없음·키보드에 안 가림(--keyboard: 키보드가 떠 있어야)
#   expect_tappable @ID "<설명>" [-t 초] <질의>            visible + 활성
#   check_eq|ne|gt|lt|ge|le|contains @ID "<설명>" <a> <b>   a·b는 ui_read 이름, 상수는 =값. 하나는 반드시 읽은 값
#   check_delta_eq  @ID "<설명>" <뒤> <앞> =<차이>          뒤 − 앞 = 차이
#   skip            @ID "<사유>"                           건너뜀(사유 필수, 보고서에 따로 표시)
# ── 읽기(출처 기록) ──
#   ui_read <이름> label|value|number|frame|count [-t 초] <질의>   값은 $(rv 이름)
#   ui_locate <변수> [-t 초] <질의>                                변수에 "x y"
#
# 질의 옵션: --label, --contains, --id, --type, --value, --enabled/--disabled, --below/--above, --after, --any
#            --first/--last/--nth N(후보가 여럿일 때. 승인된 선택 규칙 `# 규칙: G번호`가 있어야 한다)
# 후보가 여럿인데 고르는 방법이 없으면(암묵 선택) 코드가 질문을 만들고 멈춘다.

setopt noequals   # 상수 피연산자 `=값`을 zsh가 명령 경로(=cmd)로 바꾸지 않게
source $LIB/sim.sh
source $LIB/driver/${QA_DRIVER:-axe}.sh
JUDGE=$LIB/judge.py
UI_TIMEOUT=${UI_TIMEOUT:-10}
UI_TAP_SETTLE=${UI_TAP_SETTLE:-0.6}
UI_READ_RETRIES=${UI_READ_RETRIES:-4}
QA_EVIDENCE_SHOTS=${QA_EVIDENCE_SHOTS:-1}
KEYBOARD=${KEYBOARD:-software}
QA_PHASE=${QA_PHASE:-prep}
QA_STEP_CUR=0
_REC_ON=0; _REC_T0=0; _STEP_SHOT=0; _CHECK_N=0
EVID=$OUT/evidence.jsonl; TREES=$OUT/evidence/trees; SHOTS=$OUT/evidence/shots

# ── 시간·기록 ──
_now() { perl -MTime::HiRes=time -e 'printf "%.3f", time'; }
_t() { (( _REC_ON )) && printf "%.2f" $(( $(_now) - _REC_T0 )) || print -n -- "-1"; }
_stamp() { (( _REC_ON )) && printf "[%.1fs]" $(( $(_now) - _REC_T0 )) || print -n "[준비]"; }
_log() { print -r -- "$*" >> "$OUT/steps.log"; print -r -- "$*"; }
_json() {   # JSON 문자열. 제어 문자는 모두 이스케이프한다(깨진 줄이 보고서에서 사라지지 않게)
  local s=$1 out c
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\t'/\\t}; s=${s//$'\r'/\\r}
  if [[ $s == *[[:cntrl:]]* ]]; then
    out=""
    for c in ${(s::)s}; do
      if [[ $c == [[:cntrl:]] ]]; then out+=$(printf '\\u%04x' "'$c"); else out+=$c; fi
    done
    s=$out
  fi
  print -rn -- "\"$s\""
}
_event() {   # _event <종류> [키=값 …] → events.jsonl
  local kind=$1 out kv; shift
  out="{\"t\":$(_t),\"kind\":\"$kind\",\"step\":$QA_STEP_CUR,\"phase\":\"$QA_PHASE\""
  for kv in "$@"; do out+=",\"${kv%%=*}\":$(_json "${kv#*=}")"; done
  print -r -- "$out}" >> "$OUT/events.jsonl"
}
_split_dev() { _TEXT=$1; _DEV=""; [[ ${2:-} == --dev ]] && _DEV=${3:-}; }

# ── 실패 처리 ──
# 종류: app(앱 또는 각본) · env(환경: 화면 정보 읽기·도구) · script(스크립트: 값을 못 읽음·식 오류)
#       undecidable(판정 불가: 화면 정보에 필요한 속성이 없음) · gap(질문 대기: 사람이 정해야 함)
# 서브셸($(…)) 안에서 실패해도 .failed 표식이 남아, 다음 엔진 호출(_guard)에서 각본이 멈춘다.
_fail_with() {
  local kind=$1; shift
  _split_dev "$@"
  [[ -f $OUT/.failed ]] && exit 1
  : > $OUT/.failed
  _log "$(_stamp) ✗ FAIL: $_TEXT${_DEV:+  [$_DEV]}"
  drv_screenshot "$OUT/failure.png"
  drv_q dump > "$OUT/failure-tree.txt" 2>/dev/null
  [[ -f $OUT/steps/$QA_STEP_CUR.png ]] || (( QA_STEP_CUR == 0 )) || cp "$OUT/failure.png" "$OUT/steps/$QA_STEP_CUR.png" 2>/dev/null
  printf '{"text":%s,"dev":%s,"kind":"%s","phase":"%s","step":%d}\n' "$(_json "$_TEXT")" "$(_json "$_DEV")" $kind $QA_PHASE $QA_STEP_CUR > "$OUT/failure.json"
  _event fail text="$_TEXT" dev="$_DEV" kind=$kind
  exit 1
}
fail() { _fail_with app "$@"; }
fail_env() { _fail_with env "$@"; }
fail_script() { _fail_with script "$@"; }
fail_undecidable() { _fail_with undecidable "$@"; }
fail_gap() { _fail_with gap "$@"; }
_guard() { [[ -f $OUT/.failed ]] && exit 1; return 0; }

# ── 화면 읽기 층 ──
# _tree_get: 화면 정보를 _TREE에. 읽기 실패는 다시 읽고, 계속 실패하면 환경 문제
_tree_get() {
  _guard
  local try
  for try in {1..$UI_READ_RETRIES}; do
    _TREE=$(drv_tree)
    if [[ -n $_TREE && $_TREE != "[]" ]]; then _TREE_T=$(_t); _TREE_RETRIES=$(( try - 1 )); return 0; fi
    _sleep 0.4
  done
  fail_env "화면 정보를 읽지 못함(연속 ${UI_READ_RETRIES}번)" --dev "describe-ui 결과가 비어 있음"
}
# _pick <judge pick 인자…>: 새로 읽은 화면에서 고른다. P_* 변수. 0 찾음 · 1 없음
_pick() {
  local out rc try
  for try in {1..$UI_READ_RETRIES}; do
    _tree_get
    out=$(print -r -- "$_TREE" | python3 -I -B $JUDGE pick --t $_TREE_T --retries $_TREE_RETRIES "$@" 2>/dev/null); rc=$?
    if (( rc != 2 )); then eval "$out"; return $rc; fi
    _sleep 0.4
  done
  fail_env "화면 정보를 읽지 못함" --dev "pick 읽기 실패: $*"
}
# _pick_cached <인자…>: 마지막으로 읽은 화면(_TREE)에서 다시 고른다(읽기 없이). 근거 저장용
_pick_cached() {
  local out rc
  out=$(print -r -- "$_TREE" | python3 -I -B $JUDGE pick --t $_TREE_T --retries $_TREE_RETRIES "$@" 2>/dev/null); rc=$?
  (( rc == 2 )) && fail_env "화면 정보를 읽지 못함" --dev "pick(cached) 읽기 실패: $*"
  eval "$out"; return $rc
}
_wait_pick() {   # _wait_pick <초> <질의…>: 나타날 때까지
  local t=$1; shift
  local end=$(( SECONDS + t ))
  while true; do
    _pick "$@" && return 0
    (( SECONDS >= end )) && return 1
    _sleep 0.3
  done
}
# 후보가 여럿인데 고르는 방법이 없으면 코드가 질문(gap)을 만들고 멈춘다. 질문에는 그 질의를 남긴다(규칙의 쓰임과 맞춰 본다)
_ambiguous() {
  [[ $P_SEL == implicit ]] || return 0
  _event ambiguous n=$P_N query="$*" path=$P_PATH
  local gid qj
  qj=$(python3 -I -B $JUDGE qjson "$@" 2>/dev/null)
  gid=$(python3 -I -B $LIB/approve.py gap-add $QA_DIR --case ${QA_CASE_ID:-*} --step $QA_STEP_CUR --item "" --origin code \
    --reason multiple-candidates --blocking --question "같은 조건의 후보가 ${P_N}개다. 어느 것을 골라야 하나? (질의: $*)" \
    --options "첫 번째|마지막|다른 규칙" --where "${QA_CASE_ID:-준비} ${QA_STEP_CUR}단계" ${qj:+--query "$qj"})
  fail_gap "같은 조건의 화면 요소가 ${P_N}개라 어느 것인지 사람이 정해야 함(질문 $gid)" --dev "질의: $*"
}

# ── 화면 크기(좌표는 모두 비율로) ──
# 밀기(ui_swipe)와 화면 키보드 키 찾기(_kb_lower)의 비율은 세로 iPhone 화면을 가정한다(references/keyboard-packs.md)
SCREEN_W=0; SCREEN_H=0
screen_size_refresh() {
  local wh try
  for try in 1 2 3 4 5 6; do
    _tree_get
    wh=$(print -r -- "$_TREE" | python3 -I -B $JUDGE screen 2>/dev/null) && [[ ${wh% *} -gt 0 ]] && { SCREEN_W=${wh% *}; SCREEN_H=${wh#* }; return 0; }
    _sleep 0.5
  done
  fail_env "화면 크기를 읽지 못함" --dev "Application 영역이 없음"
}
px() { (( SCREEN_W > 0 )) || screen_size_refresh; local v=$(( $1 * ${(P)${:-SCREEN_$2}} )); print ${v%.*}; }

# ── 읽기(출처 기록) ──
ui_find() { _guard; _pick "$@"; }   # 지금 있나(0/1). 후보가 여럿이어도 '있음'은 같다
ui_wait() {   # ui_wait [-t 초] <질의>: 나타날 때까지(0/1). 위치가 필요하면 ui_locate
  _guard
  local t=$UI_TIMEOUT; [[ $1 == -t ]] && { t=$2; shift 2; }
  _wait_pick $t "$@"
}
ui_wait_gone() {   # 사라질 때까지(0/1). 읽기 실패는 사라짐이 아니다(_tree_get이 환경 실패로 끝낸다)
  _guard
  local t=$UI_TIMEOUT; [[ $1 == -t ]] && { t=$2; shift 2; }
  local end=$(( SECONDS + t ))
  while true; do
    _pick "$@" || return 0
    (( SECONDS >= end )) && return 1
    _sleep 0.3
  done
}
ui_locate() {   # ui_locate <변수> [-t 초] <질의>: 요소 중심 "x y"를 변수에. 없으면 실패
  _guard
  local var=$1; shift
  local t=$UI_TIMEOUT; [[ $1 == -t ]] && { t=$2; shift 2; }
  _wait_pick $t "$@" || fail "화면에 없음" --dev "ui_locate $var: $*"
  _ambiguous "$@"
  typeset -g "$var=$P_X $P_Y"
}
ui_read() {   # ui_read <이름> <종류> [-t 초] <질의>: 값과 출처(질의·화면 정보·위치·시각)를 기록. 못 찾으면 값이 비고 출처에 남는다
  _guard
  local name=$1 kind=$2; shift 2
  [[ $name =~ '^[A-Za-z_][A-Za-z0-9_]*$' ]] || fail_script "읽기 이름이 잘못됨" --dev "ui_read '$name'"
  local t=$UI_TIMEOUT; [[ $1 == -t ]] && { t=$2; shift 2; }
  if [[ $kind == count ]]; then _tree_get; else _wait_pick $t "$@"; fi
  _pick_cached --save $TREES --kind $kind "$@"
  [[ $kind != count && $P_FOUND == 1 ]] && _ambiguous "$@"
  typeset -g "QAR_$name=$P_VALUE"
  typeset -g "QARJ_$name=$P_READ"
  _event read name=$name read_kind=$kind value="$P_VALUE" tree=$P_TREE path=$P_PATH
}
rv() { print -r -- "${(P)${:-QAR_$1}}"; }   # 읽은 값

# ── 판정 ──
_items_ok() {
  [[ ${1:-} == @* ]] || fail_script "판정에 항목(@ID)이 없음" --dev "$*"
  _ITEMS=${1#@}
  local x
  for x in ${(s:,:)_ITEMS}; do
    [[ " $QA_ITEMS " == *" $x "* ]] || fail_script "각본에 없는 항목" --dev "@$x"
    [[ ${x##*\#} == ${QA_STEP_CUR}.* ]] || fail_script "다른 단계의 항목" --dev "@$x (지금 ${QA_STEP_CUR}단계)"
  done
}
# 판정 하나마다: 고유 ID, 그 순간의 스크린샷(원본), 비용 측정 시작
_record_prep() {
  (( _CHECK_N += 1 ))
  _CID=${QA_CASE_ID:-prep}-c$(printf %03d $_CHECK_N)
  local t0=$(_now) shot="" tshot=""
  if (( QA_EVIDENCE_SHOTS )); then
    mkdir -p $SHOTS
    drv_screenshot $SHOTS/$_CID.png && { shot=evidence/shots/$_CID.png; tshot=$(_t); }
  fi
  local errs="[]"; [[ $QA_EVIDENCE_SHOTS == 1 && -z $shot ]] && errs='["판정 순간 스크린샷 실패"]'
  _REC=(--evidence $EVID --check-id $_CID --items $1 --step $QA_STEP_CUR --desc "$2" --phase $QA_PHASE --cost-start $t0 --errors "$errs")
  [[ -n $shot ]] && _REC+=(--shot $shot --t-shot $tshot)
}
_pass() { _event check ok=1 desc="$1" check_id=$_CID; _log "$(_stamp)   ✓ $1"; }
_expect() {
  _guard
  local fn=$1; shift
  _items_ok "$1"; local items=$_ITEMS desc=$2; shift 2
  local t=$UI_TIMEOUT kb=() pre="" out rc end
  [[ $1 == -t ]] && { t=$2; shift 2; }
  [[ $1 == --keyboard ]] && { kb=(--keyboard); shift; }
  local common=(--kb-ids "$KB_IDS" --kb-labels "$KB_LABELS" $kb)
  end=$(( SECONDS + t ))
  while true; do
    _tree_get
    [[ $fn == gone && -z $pre ]] && pre=$(print -r -- "$_TREE" | python3 -I -B $JUDGE treesave $TREES 2>/dev/null)
    out=$(print -r -- "$_TREE" | python3 -I -B $JUDGE expect $fn $common "$@" 2>/dev/null); rc=$?
    if (( rc == 0 || rc == 3 )); then break; fi
    (( SECONDS >= end )) && break
    _sleep 0.3
  done
  (( rc == 2 )) && fail_env "화면 정보를 읽지 못함" --dev "expect_$fn: $*"
  _record_prep $items "$desc"
  local prearg=(); [[ -n $pre ]] && prearg=(--pre-tree $pre)
  out=$(print -r -- "$_TREE" | QA_EVID_KEY=${_QA_KEY:-} python3 -I -B $JUDGE expect $fn $common --save $TREES --t $_TREE_T \
        --retries $_TREE_RETRIES $prearg $_REC "$@"); rc=$?
  eval "$out"
  [[ $fn == visible || $fn == tappable ]] && (( rc == 0 )) && _ambiguous "$@"
  case $rc in
    0) _pass "$desc" ;;
    1) fail "$desc" --dev "$P_REASON (expect_$fn $*)" ;;
    3) fail_undecidable "$desc: 판정 불가" --dev "$P_REASON (expect_$fn $*)" ;;
    *) fail_script "판정을 하지 못함(엔진·스크립트 인자 오류)" --dev "judge expect rc=$rc: $*" ;;
  esac
}
expect_present() { _expect present "$@"; }
expect_gone() { _expect gone "$@"; }
expect_visible() { _expect visible "$@"; }
expect_tappable() { _expect tappable "$@"; }
_check() {
  _guard
  local fn=$1; shift
  _items_ok "$1"; local items=$_ITEMS desc=$2; shift 2
  local ins=() o j out rc
  for o in "$@"; do
    if [[ $o == =* ]]; then
      ins+=(--in "{\"name\":$(_json "$o"),\"value\":$(_json "${o#=}"),\"read\":{\"const\":true}}")
    else
      (( ${+parameters[QARJ_$o]} )) || fail_script "$desc: 비교할 값 '$o'가 출처 있는 읽기가 아님" --dev "ui_read $o …가 먼저 있어야 함"
      j=${(P)${:-QARJ_$o}}
      ins+=(--in "{\"name\":$(_json "$o"),${j:1}")
    fi
  done
  _record_prep $items "$desc"
  out=$(QA_EVID_KEY=${_QA_KEY:-} python3 -I -B $JUDGE check $fn $ins $_REC); rc=$?
  eval "$out"
  case $rc in
    0) _pass "$desc ($P_REASON)" ;;
    1) fail "$desc" --dev "$P_REASON (check_$fn $*)" ;;
    3) fail_script "$desc: 비교할 값을 읽지 못함" --dev "$P_REASON (check_$fn $*)" ;;
    *) fail_script "판정을 하지 못함(엔진·스크립트 인자 오류)" --dev "judge check rc=$rc: $*" ;;
  esac
}
for _f in eq ne gt lt ge le contains delta_eq; do eval "check_$_f() { _check $_f \"\$@\"; }"; done; unset _f
skip() {
  _guard
  _items_ok "$1"; local items=$_ITEMS reason=${2:-}
  [[ -n ${reason// /} ]] || fail_script "사유 없는 건너뜀" --dev "skip $1"
  (( _CHECK_N += 1 )); _CID=${QA_CASE_ID}-c$(printf %03d $_CHECK_N)
  QA_EVID_KEY=${_QA_KEY:-} python3 -I -B $JUDGE skip --reason "$reason" --evidence $EVID --check-id $_CID --items $items --step $QA_STEP_CUR --phase $QA_PHASE >/dev/null
  _event skip items=$items reason="$reason"
  _log "$(_stamp)   ↷ 건너뜀: $reason"
}

# ── 단계 ──
step() {
  _guard
  local n=$1 name
  _step_close
  (( n == QA_STEP_CUR + 1 )) || fail_script "단계 번호 순서가 어긋남" --dev "step $n (앞 단계 $QA_STEP_CUR)"
  (( n <= QA_STEP_COUNT )) || fail_script "각본에 없는 단계" --dev "step $n (각본은 ${QA_STEP_COUNT}단계)"
  QA_STEP_CUR=$n; _STEP_SHOT=0
  name=${(P)${:-QA_STEP_ACTION_$n}}
  _KB_TREE=""
  _event step name="$name"
  _log "$(_stamp) ▶ $n. $name"
}
_step_close() {
  (( QA_STEP_CUR > 0 )) || return 0
  (( _STEP_SHOT )) && return 0
  ui_wait_stable
  drv_screenshot "$OUT/steps/$QA_STEP_CUR.png"
  _STEP_SHOT=1
  _event step_end shot="steps/$QA_STEP_CUR.png"
}
ui_shot_here() {   # 지금 화면을 이 단계의 대표 스크린샷으로(잠깐 뜨는 안내를 확인한 직후)
  _guard
  local f
  if (( _STEP_SHOT )); then f=steps/$QA_STEP_CUR-$(( $(ls $OUT/steps/$QA_STEP_CUR-*.png 2>/dev/null | wc -l) + 2 )).png
  else f=steps/$QA_STEP_CUR.png; _STEP_SHOT=1; fi
  drv_screenshot "$OUT/$f"
  _event shot shot="$f" what="${1:-}"
}
steps_finish() {
  _guard
  _step_close
  (( QA_STEP_CUR == QA_STEP_COUNT )) || fail_script "각본의 단계를 다 돌지 않음" --dev "각본 ${QA_STEP_COUNT}단계, 스크립트는 ${QA_STEP_CUR}단계에서 끝남"
}
# ui_wait_stable [간격]: 연속 두 스크린샷이 같을 때까지(커서 깜빡임은 무시). 결과는 events.jsonl
ui_wait_stable() {
  local a=$OUT/.stable-a.png b=$OUT/.stable-b.png i verdict
  drv_screenshot $a
  for i in 1 2 3 4; do
    _sleep ${1:-0.3}; drv_screenshot $b
    verdict=$(python3 -I -B $LIB/diff.py stable $a $b 2>/dev/null)
    if [[ $verdict == stable* ]]; then rm -f $a $b; _event stable ok=1 tries=$i detail="$verdict"; return 0; fi
    mv -f $b $a
  done
  rm -f $a $b
  _event stable ok=0 tries=$i detail="$verdict"
  _log "$(_stamp)   (화면이 계속 움직여 안정 대기를 끝냄: $verdict)"
  return 1
}

# ── 조작 ──
_tap_at() {
  _guard
  drv_tap $1 $2 || fail_env "탭을 보내지 못함" --dev "($1,$2) ${3:-}"
  _event tap x=$1 y=$2 what="${3:-}"
  _sleep $UI_TAP_SETTLE
}
ui_tap() {   # ui_tap [-t 초] <질의>: 기다렸다가 요소 중심을 탭
  _guard
  local t=$UI_TIMEOUT; [[ $1 == -t ]] && { t=$2; shift 2; }
  _KB_TREE=""
  _wait_pick $t "$@" || fail "탭할 것이 화면에 없음" --dev "$*"
  _ambiguous "$@"
  _tap_at $P_X $P_Y "$*"
}
ui_tap_xy() { _KB_TREE=""; _tap_at $1 $2 "${3:-}"; }
ui_press() {   # 눌렀다 잠깐 뒤 뗀다(짧은 탭이 안 먹는 스위치)
  _guard
  _KB_TREE=""
  _wait_pick $UI_TIMEOUT "$@" || fail "누를 것이 화면에 없음" --dev "$*"
  _ambiguous "$@"
  drv_press $P_X $P_Y 0.15 || fail_env "누르기를 보내지 못함" --dev "$*"
  _event tap x=$P_X y=$P_Y what="$*" press=1
  _sleep $UI_TAP_SETTLE
}
ui_swipe() {   # ui_swipe up|down|left|right [y]
  _guard
  local cx=$(px 0.5 W) y=${2:-$(px 0.46 H)}
  case $1 in
    up)    drv_swipe $cx $(px 0.74 H) $cx $(px 0.29 H) ;;
    down)  drv_swipe $cx $(px 0.29 H) $cx $(px 0.74 H) ;;
    left)  drv_swipe $(px 0.85 W) $y $(px 0.15 W) $y ;;
    right) drv_swipe $(px 0.15 W) $y $(px 0.85 W) $y ;;
  esac || fail_env "밀기를 보내지 못함" --dev "ui_swipe $1"
  _event swipe dir=$1
  _sleep 0.8
}
ui_drag() { _guard; drv_swipe $1 $2 $3 $4 ${5:-1.0} || fail_env "밀기를 보내지 못함" --dev "($1,$2)→($3,$4)"; _event swipe dir=drag; }
ui_pause() { _sleep ${1:-1}; }   # 영상 속도 조절용. 화면 변화를 기다리는 데 쓰지 않는다(실행 전 검사가 막는다)

# ── 글자 입력 ──
_KB=$LIB/keyboard/${QA_INPUT_LANG:-ko}.py
[[ -f $_KB ]] || fail_env "자판 팩이 없음" --dev "QA_INPUT_LANG=${QA_INPUT_LANG:-ko}: $_KB (references/keyboard-packs.md)"
eval "$(python3 -I -B $_KB --labels)"   # KB_SHIFTED, KB_PROBE_KEYS, KB_GLOBE_LABEL, KB_OTHER_LANG_LABEL, KB_DELETE_LABEL, KB_*_ID
KB_IDS="$KB_ASSISTANT_ID,$KB_RETURN_ID,$KB_DELETE_ID,$KB_SHIFT_ID,$KB_MORE_ID,$KB_SPACE_ID"
KB_LABELS="${KB_PROBE_KEYS// /,},1,$KB_DELETE_LABEL"

ui_type() {
  _guard
  if [[ $KEYBOARD == software ]]; then _kb_type "$1" 0.1; return; fi
  local keys chunk; keys=$(python3 -I -B $_KB "$1")
  for chunk in "${(@f)$(python3 -I -B -c '
import sys; s = sys.argv[1]; out = [s[:1]]
for a, b in zip(s, s[1:]):
    out.append(b) if a == b else out.__setitem__(-1, out[-1] + b)
print("\n".join(out))' "$keys")}"; do
    drv_type "$chunk" || fail_env "키 입력을 보내지 못함" --dev "하드웨어 입력: $1"
  done
  _event type text="$1"
  _sleep 0.4
}
ui_type_slow() {
  _guard
  if [[ $KEYBOARD == software ]]; then _kb_type "$1" 0.3; return; fi
  local keys i; keys=$(python3 -I -B $_KB "$1")
  for (( i = 1; i <= ${#keys}; i++ )); do drv_type "${keys[i]}" || fail_env "키 입력을 보내지 못함" --dev "하드웨어 입력: $1"; _sleep 0.3; done
  _event type text="$1"
  _sleep 0.3
}
ui_backspace() {
  _guard
  local i keys=()
  if [[ $KEYBOARD == software ]]; then
    _kb_wait || fail "화면 키보드가 뜨지 않음(지우기)" --dev "입력칸에 초점이 없거나 하드웨어 입력이 섞임"
    for i in {1..${1:-1}}; do _kb_tap_key delete 0.1; done
    return
  fi
  for i in {1..${1:-1}}; do keys+=42; done
  drv_key_seq ${(j:,:)keys}
}
ui_submit() {
  _guard
  if [[ $KEYBOARD == software ]]; then _kb_wait || fail "화면 키보드가 뜨지 않음(Return)" --dev "입력칸에 초점이 없거나 하드웨어 입력이 섞임"; _kb_tap_key return 0.3
  else drv_key 40 || fail_env "Return 키를 보내지 못함"; _sleep 0.3; fi
}
ui_clear_field() { ui_tap_xy $1 $2 "입력칸"; ui_backspace ${3:-6}; }

# ── 화면 키보드(엔진 내부: 자판 팩의 키 이름으로 찾는다. 후보 선택 질문 대상이 아님) ──
_KB_TREE=""
_kb_refresh() {
  local try
  for try in {1..$UI_READ_RETRIES}; do _KB_TREE=$(drv_tree); [[ -n $_KB_TREE ]] && return 0; _sleep 0.4; done
  fail_env "화면 정보를 읽지 못함(키보드)" --dev "describe-ui 비어 있음 ${UI_READ_RETRIES}번"
}
_kb_find() { [[ -n $_KB_TREE ]] || _kb_refresh; drv_q_in "$_KB_TREE" find --type Button --last "$@" 2>/dev/null; }
_kb_label() { drv_q_in "$_KB_TREE" label --type Button --last "$@" 2>/dev/null; }
_kb_visible() { _kb_find --id $KB_RETURN_ID >/dev/null || _kb_find --id $KB_DELETE_ID >/dev/null || _kb_find --label "$KB_DELETE_LABEL" >/dev/null; }
_kb_wait() {
  local end=$(( SECONDS + 5 ))
  while true; do _kb_refresh; _kb_visible && return 0; (( SECONDS >= end )) && return 1; _sleep 0.3; done
}
_kb_lower() { print $(px 0.45 H); }
_kb_find_key() {
  case $1 in
    delete) _kb_find --id $KB_DELETE_ID || _kb_find --label "$KB_DELETE_LABEL" ;;
    return) _kb_find --id $KB_RETURN_ID ;;
    shift)  _kb_find --id $KB_SHIFT_ID ;;
    more)   _kb_find --id $KB_MORE_ID ;;
    globe)  _kb_find --label "$KB_GLOBE_LABEL" ;;
    " ")    _kb_find --id $KB_SPACE_ID ;;
    *)      _kb_find --label "$1" --below $(_kb_lower) ;;
  esac
}
_kb_lang_visible() { local k; for k in ${=KB_PROBE_KEYS}; do _kb_find --label $k --below $(_kb_lower) >/dev/null && return 0; done; return 1; }
_kb_lang_menu() {   # 언어 전환 키를 길게 눌러 뜬 목록에서 이 자판(KB_LANG_NAME)을 고른다. 성공 0
  local g m
  g=$(_kb_find --label "$KB_GLOBE_LABEL") || return 1
  drv_press ${g% *} ${g#* } 1.2; _sleep 0.6
  m=$(drv_q find --label "$KB_LANG_NAME" --type StaticText 2>/dev/null) || return 1
  drv_tap ${m% *} ${m#* }; _event tap x=${m% *} y=${m#* } what="자판 목록: ${KB_LANG_NAME}" key=1; _sleep 0.5
  _log "$(_stamp)   (다른 언어 자판이 떠 있어 자판 목록에서 ${KB_LANG_NAME}을 고름)"
  return 0
}
_kb_numbers_layout() {   # 숫자·기호 자판인가('more' 키가 글자 자판으로 가는 이름)
  local l; l=$(drv_q_in "$_KB_TREE" label --type Button --last --id $KB_MORE_ID 2>/dev/null)
  [[ -n $l && " $KB_MORE_TO_LETTERS " == *" $l "* ]]
}
_kb_other_lang() {
  [[ $(_kb_label --label "$KB_GLOBE_LABEL") == "$KB_OTHER_LANG_LABEL" ]] && return 0
  [[ $(drv_q_in "$_KB_TREE" value --type Button --last --label "$KB_GLOBE_LABEL" 2>/dev/null) == "$KB_OTHER_LANG_LABEL" ]]
}
_kb_tap_key() {
  _guard
  local key=$1 settle=${2:-0.1} xy switch try
  if ! xy=$(_kb_find_key "$key"); then
    _kb_wait || fail "화면 키보드가 없음" --dev "키 '$key'를 누르려 했음. 하드웨어 입력이 섞였거나 입력칸에 초점이 없다"
    for try in 1 2 3 4 5 6; do
      xy=$(_kb_find_key "$key") && break
      if [[ $key == [0-9] ]]; then switch=more                                   # 글자 자판 → 숫자 자판
      elif _kb_numbers_layout; then switch=more                                  # 숫자 자판 → 글자 자판
      elif _kb_other_lang || ! _kb_lang_visible; then                            # 다른 언어·이모지 자판
        _kb_lang_menu && { xy=""; _kb_refresh; continue; }                        # 언어 전환 키를 길게 눌러 목록에서 고른다
        switch=globe                                                             # 목록이 없으면 다음 자판으로(순환)
      elif [[ -n $key && $KB_SHIFTED == *$key* ]]; then switch=shift
      else fail "키보드에서 키를 못 찾음" --dev "키 '$key'"; fi
      xy=$(_kb_find_key $switch) || fail "키보드에서 키를 못 찾음" --dev "'$key'도 전환 키($switch)도 없음"
      [[ $switch == globe ]] && _log "$(_stamp)   (다른 언어 자판이 떠 있어 전환 키로 바꿈)"
      drv_tap ${xy% *} ${xy#* }; _event tap x=${xy% *} y=${xy#* } what="키 $switch" key=1; _sleep 0.4; _kb_refresh
      xy=""
    done
    [[ -n $xy ]] || fail "키보드에서 키를 못 찾음" --dev "키 '$key' (레이아웃 전환 뒤에도 없음)"
  fi
  drv_tap ${xy% *} ${xy#* } || fail_env "키 탭을 보내지 못함" --dev "키 '$key'"
  _event tap x=${xy% *} y=${xy#* } what="키 $key" key=1
  _sleep $settle
  [[ $key == shift || $key == more || $KB_SHIFTED == *$key* ]] && _KB_TREE=""
  return 0
}
_kb_type() {
  local k
  _kb_wait || fail "화면 키보드가 뜨지 않음" --dev "입력칸에 초점이 없거나 하드웨어 입력이 섞임"
  for k in "${(@f)$(python3 -I -B $_KB --keys "$1")}"; do _kb_tap_key "$k" $2; done
  _event type text="$1"
  _sleep 0.3
}
# kb_top: 화면 키보드 윗변 y(판정이 아닌 참고용. 판정은 expect_visible이 영역으로 한다)
kb_top() { _tree_get; print -r -- "$_TREE" | python3 -I -B $JUDGE kbtop --kb-ids "$KB_IDS" --kb-labels "$KB_LABELS"; }

# ── 기록(판정 아님) ──
ui_note() { _split_dev "$@"; _log "$(_stamp)   ⚠ $_TEXT"; _event note text="$_TEXT" dev="$_DEV"; }
ui_info() { _log "$(_stamp)   · $*"; _event info text="$*"; }
ui_shot() { drv_screenshot "$OUT/$1.png"; }

# ── 앱 수명 ──
app_kill() { sim_terminate $BUNDLE_ID; _sleep 0.5; }
app_reset() { app_kill; sim_uninstall $BUNDLE_ID; sim_install "$APP_PATH" || fail_env "앱을 설치하지 못함" --dev "$APP_PATH"; }
app_launch() { sim_launch $BUNDLE_ID "${QA_LAUNCH_ARGS[@]}" || fail_env "앱을 실행하지 못함" --dev "$BUNDLE_ID"; }
app_relaunch() { app_kill; app_launch; }

# ── 앱 상태 스냅샷 ──
state_exists() { [[ -d $FIXTURES/$1 ]]; }
state_save() { app_kill; mkdir -p $FIXTURES/$1; rsync -a --delete "$(sim_container $BUNDLE_ID)/" $FIXTURES/$1/ || fail_env "앱 상태를 저장하지 못함" --dev "$1"; }
state_load() { app_reset; local c; c=$(sim_container $BUNDLE_ID) || fail_env "앱 데이터 폴더가 없음"; rsync -a --delete $FIXTURES/$1/ "$c/" || fail_env "앱 상태를 복원하지 못함" --dev "$1"; }

# ── 녹화 ──
rec_start() { drv_record_start "$OUT/video.mp4" ${REC_FPS:-30} ${REC_SCALE:-0.5}; _REC_T0=$(_now); _REC_ON=1; _event rec_start; _sleep 1; }
rec_stop() { (( _REC_ON )) || return 0; _sleep 1.5; drv_record_stop; _REC_ON=0; }
