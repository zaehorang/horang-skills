#!/bin/zsh
# 각본을 시뮬레이터에서 돌리고 각본마다 영상·단계별 스크린샷·기록을 남긴다. 앱 정보는 qa/qa.config에서만 읽는다.
#
#   run.sh                              # 현재 폴더(또는 상위)의 qa/ : 빌드 → '기본' 조건의 자동 각본 전부 → 보고서
#   run.sh 02 05                        # QA-02, QA-05만
#   run.sh --condition "작은 기기"       # 그 조건이 적힌 각본만, 조건에 맞는 기기로
#   run.sh --no-build --device "iPhone 17 Pro"
#   run.sh --check                      # 실행하지 않고 각본–스크립트 검사만
#   run.sh --project <앱 레포>/qa
#
# 사람 승인 전(승인 없음·bootstrap·승인 뒤 바뀜·규칙 범위 밖)이면 실행하지 않는다(exit 5).
# QA_ALLOW_UNAPPROVED=1이면 엔진 시험용으로 실행하되, 결과는 "사람 승인 전"으로 표시되고 통과로 끝나지 않는다(exit 5).
# 중단(Ctrl+C)해도 전역 설정·잠금·글씨 크기를 되돌린다. 비정상 종료로 남은 잠금은 다음 실행이 회수한다.
#
# 결과: qa/results/<시각>-<조건>/index.html (results/latest가 가장 최근)
# 종료 코드: 0 전부 통과 · 1 실패·불완전·건너뜀·재현 검증 차단 · 2 실행 전 검사 차단 · 3 다른 실행이 잠금 · 5 사람 승인 대기
# 요구: xcrun(Xcode), 실행 도구(driver 참고), python3, perl, ffmpeg(선택). `qa doctor`로 확인

set -u
ENGINE=${0:A:h:h}
LIB=$ENGINE/scripts/lib
export ENGINE LIB PYTHONDONTWRITEBYTECODE=1
CONDITION="기본"; DEVICE_NAME=""; BUILD=1; CHECK_ONLY=0; IDS=(); QA_DIR=${QA_DIR:-}; EXPLORE=""; EXPLORE_CASE=""

while (( $# )); do
  case $1 in
    --no-build) BUILD=0 ;;
    --check) CHECK_ONLY=1 ;;
    --condition) CONDITION=$2; shift ;;
    --device) DEVICE_NAME=$2; shift ;;
    --project) QA_DIR=${2:A}; shift ;;
    --explore) EXPLORE=${2:A}; shift ;;
    --explore-case) EXPLORE_CASE=$2; shift ;;
    -h|--help) sed -n '2,17p' $0; exit 0 ;;
    *) IDS+=$1 ;;
  esac
  shift
done

# ── 프로젝트 ──
if [[ -z $QA_DIR ]]; then
  d=$PWD
  while [[ $d != / ]]; do [[ -f $d/qa/qa.config ]] && { QA_DIR=$d/qa; break; }; [[ -f $d/qa.config ]] && { QA_DIR=$d; break; }; d=${d:h}; done
fi
[[ -n $QA_DIR && -f $QA_DIR/qa.config ]] || { print "qa/qa.config를 찾지 못했습니다(--project <qa 폴더>)"; exit 1; }
REPO=${QA_DIR:h}
typeset -A QA_CONDITIONS
QA_LAUNCH_ARGS=(); QA_REQUIRED_FILES=()
source $QA_DIR/qa.config
export QA_DIR REPO QA_INPUT_LANG=${QA_INPUT_LANG:-ko} QA_LAUNCH_ARGS QA_DRIVER=${QA_DRIVER:-axe}

# ── 각본 고르기와 검사(실행 전) ──
if [[ -n $EXPLORE ]]; then   # 탐색 모드(S1): 각본 검사·녹화 없이 엔진 어휘로 앱을 조작해 본다
  CASES=("$EXPLORE_CASE"$'\t'"$(basename $(print -l $QA_DIR/cases/$EXPLORE_CASE-*.md(N) | head -1))")
else
CASES=("${(@f)$(python3 -I -B $LIB/casefile.py list $QA_DIR/cases --auto --condition "$CONDITION" $IDS)}")
CASES=(${CASES:#})
(( ${#CASES} )) || { print "조건 '$CONDITION'에 해당하는 자동 각본이 없습니다"; exit 1; }
errors=(); warns=(); pending=()
_collect() {   # casefile 출력의 "차단\t…" / "대기\t…" / "경고\t…"를 모은다
  local line
  for line in "${(@f)1}"; do
    [[ $line == 차단$'\t'* ]] && errors+=("${line#*$'\t'}")
    [[ $line == 대기$'\t'* ]] && pending+=("${line#*$'\t'}")
    [[ $line == 경고$'\t'* ]] && warns+=("${line#*$'\t'}")
  done
}
_collect "$(python3 -I -B $LIB/casefile.py check-shared $QA_DIR 2>&1)"
for row in $CASES; do
  id=${row%%$'\t'*}; md=$QA_DIR/cases/${row#*$'\t'}; sh=$QA_DIR/steps/$id.sh
  [[ -f $sh ]] || { errors+="$id: 스크립트 없음 ($sh)"; continue; }
  _collect "$(python3 -I -B $LIB/casefile.py check $md $sh $QA_DIR 2>&1)"
done
if (( ${#warns} )); then
  # 같은 문구는 한 번만(위치만 다른 경고를 묶는다)
  print "실행 전 검사 경고:"
  print -l -- $warns | sed -E 's/^[^ ]+:[0-9]+: //' | sort | uniq -c | sed -E 's/^ *([0-9]+) /  (\1곳) /'
fi
if (( ${#errors} )); then
  print "실행 전 검사에서 막혀 실행하지 않습니다:"
  for e in $errors; do print "  ✗ $e"; done
  exit 2
fi
UNAPPROVED=0
if (( ${#pending} )); then
  print "사람 승인 대기:"
  print -l -- $pending | sed -E 's/^[^ ]+:[0-9]+: //' | sort | uniq -c | sed -E 's/^ *([0-9]+) /  (\1곳) /'
  if [[ ${QA_ALLOW_UNAPPROVED:-0} != 1 ]]; then
    print "사람 승인 전이라 실행하지 않습니다. 사람이 터미널에서 qa approve / qa answer로 승인해야 합니다(exit 5)"
    exit 5
  fi
  UNAPPROVED=1
  print "⚠⚠ QA_ALLOW_UNAPPROVED=1: 사람 승인 전 상태로 실행합니다. 결과는 '사람 승인 전'이며 통과로 쓰지 않습니다"
fi
print "▶ 각본 ${#CASES}개 실행 전 검사 통과 (조건: $CONDITION)"
fi
if (( CHECK_ONLY )); then (( ${UNAPPROVED:-0} )) && exit 5; exit 0; fi

# ── 도구·기기 ──
source $LIB/sim.sh
DRV_DIR=$LIB/driver; source $LIB/driver/$QA_DRIVER.sh
drv_check || exit 1
for f in $QA_REQUIRED_FILES; do [[ -e $REPO/$f ]] || { print "필요한 파일이 없습니다: $f"; exit 1; }; done
cond=${QA_CONDITIONS[$CONDITION]:-}
[[ -n $DEVICE_NAME ]] || DEVICE_NAME=${cond%%;*}
[[ -n $DEVICE_NAME ]] || { print "qa.config의 QA_CONDITIONS에 '$CONDITION' 조건의 기기가 없습니다"; exit 1; }
CONTENT_SIZE=${${cond#*;}:#$cond}
UDID=$(sim_udid "$DEVICE_NAME")
[[ -n $UDID ]] || { print "시뮬레이터를 찾지 못함: $DEVICE_NAME"; exit 1; }
export UDID

# ── 빌드 ──
DERIVED=$QA_DIR/.build
if (( BUILD )); then
  print "▶ 빌드 중... ($QA_SCHEME)"
  if [[ -n ${QA_WORKSPACE:-} ]]; then xc_target=(-workspace $REPO/$QA_WORKSPACE)
  else xc_target=(-project $REPO/$QA_PROJECT); fi
  xcodebuild $xc_target -scheme $QA_SCHEME -configuration ${QA_CONFIGURATION:-Debug} \
    -destination "generic/platform=iOS Simulator" -derivedDataPath $DERIVED build > $QA_DIR/.build.log 2>&1 \
    || { tail -20 $QA_DIR/.build.log; print "빌드 실패: $QA_DIR/.build.log"; exit 1; }
fi
# 앱 선택: QA_APP_NAME → 스킴 이름 → 결과물이 하나뿐이면 그것. 여럿이면 고르지 않고 멈춘다
PRODUCTS=$DERIVED/Build/Products/${QA_CONFIGURATION:-Debug}-iphonesimulator
APP_PATH=""
for cand in ${QA_APP_NAME:+$PRODUCTS/$QA_APP_NAME.app} $PRODUCTS/$QA_SCHEME.app; do [[ -d $cand ]] && { APP_PATH=$cand; break; }; done
if [[ -z $APP_PATH ]]; then
  apps=($PRODUCTS/*.app(N))
  (( ${#apps} == 1 )) && APP_PATH=$apps[1]
  (( ${#apps} > 1 )) && { print "빌드 결과물에 앱이 여럿입니다. qa.config의 QA_APP_NAME으로 고르세요: ${apps:t}"; exit 1; }
fi
[[ -n $APP_PATH ]] || { print "빌드 결과물이 없습니다. --no-build 없이 실행하세요"; exit 1; }
BUNDLE_ID=${QA_BUNDLE_ID:-$(sim_bundle_id "$APP_PATH")}
export APP_PATH BUNDLE_ID

# ── 키보드 모드 준비 ──
# 화면 키보드는 (1) Simulator.app 창 (2) '하드웨어 키보드 연결'(전역 설정) 끔 일 때만 뜬다.
# 전역 설정이라 Mac당 동시에 한 실행만: 잠금 파일에 원래 값을 적어 두고, 끝날 때(실패해도) 되돌린다.
# 지난 실행이 비정상 종료해 잠금이 남아 있으면 그 값으로 먼저 복구한다.
case_input() { python3 -I -B $LIB/casefile.py parse $1 | python3 -I -B -c 'import json,sys; print(json.load(sys.stdin)["input_mode"])'; }
kb_mode() { case $1 in hardware) print hardware ;; *) print software ;; esac; }   # 입력 없음도 준비 과정의 입력은 화면 키보드로(하드웨어 입력은 부팅을 오염시킨다)
HWKB_DOMAIN=com.apple.iphonesimulator
LOCK=/tmp/ios-video-qa.lock.d        # mkdir로 원자적으로 잡는다. 안에 pid·orig(원래 값)·udid (lib/lock.sh)
hwkb_restore() {
  local orig=$1
  if [[ $orig == absent ]]; then defaults delete $HWKB_DOMAIN ConnectHardwareKeyboard 2>/dev/null
  else defaults write $HWKB_DOMAIN ConnectHardwareKeyboard -int $orig; fi
}
lock_restore() { hwkb_restore $1; [[ -n ${2:-} ]] && xcrun simctl ui $2 content_size medium >/dev/null 2>&1; }
source $LIB/lock.sh
LOCKED=0
cleanup() {   # 잠금을 잡은 실행만 부른다(잠금을 못 잡았으면 다른 실행의 기기·설정을 건드리지 않는다)
  trap - EXIT INT TERM HUP
  (( LOCKED )) || return 0
  sim_terminate ${BUNDLE_ID:-}
  sim_status_bar_clear
  sim_content_size medium
  [[ -n ${HWKB_ORIG:-} ]] && hwkb_restore $HWKB_ORIG
  lock_release; LOCKED=0
}
on_signal() { print "\n중단됨: 설정을 되돌립니다"; cleanup; exit 130; }
lock_acquire || exit 3
LOCKED=1
trap cleanup EXIT
trap on_signal INT TERM HUP
# 원래 값은 지난 실행의 잔여 설정을 복구한 뒤에 읽고, 바꾸기 전에 잠금에 적는다
HWKB_ORIG=$(defaults read $HWKB_DOMAIN ConnectHardwareKeyboard 2>/dev/null || print absent)
lock_set_orig $HWKB_ORIG
typeset -A INPUT_OF
needs_window=0
for row in $CASES; do
  id=${row%%$'\t'*}; INPUT_OF[$id]=$(kb_mode "$(case_input $QA_DIR/cases/${row#*$'\t'})")
  [[ $INPUT_OF[$id] == software ]] && needs_window=1
done
if (( needs_window )); then
  defaults write $HWKB_DOMAIN ConnectHardwareKeyboard -bool false
  sim_window_running && sim_window_quit     # 다른 기기 창이 열려 있으면 이 기기로 다시 연다
fi
sim_boot
sim_content_size ${CONTENT_SIZE:-medium}    # 지난 실행의 큰 글씨가 남지 않도록 매번 명시적으로
sim_status_bar_fix ${QA_STATUS_BAR_TIME:-9:41}
(( needs_window )) && { sim_window_open; print "▶ 화면 키보드: Simulator.app 창 열고 하드웨어 키보드 연결 끔(끝나면 원래대로: $HWKB_ORIG)"; }
print "▶ 기기: $DEVICE_NAME ($UDID) · 조건: $CONDITION${CONTENT_SIZE:+ · 글씨 $CONTENT_SIZE}"
WARNING=""
# 앱의 하루가 자정이 아닌 시각에 바뀌면 qa.config의 QA_DAY_BOUNDARY_HOUR(시). 그 전 시각에 돌리면 경고
if [[ -n ${QA_DAY_BOUNDARY_HOUR:-} ]] && (( $(date +%-H) < QA_DAY_BOUNDARY_HOUR )); then
  WARNING="0시~${QA_DAY_BOUNDARY_HOUR}시 실행: '오늘'을 Mac 시계로 계산하므로 앱의 하루 경계(${QA_DAY_BOUNDARY_HOUR}시)와 어긋날 수 있다"
  print "⚠ $WARNING"
fi

# ── 탐색 모드 ──
if [[ -n $EXPLORE ]]; then
  QA_WORK=$QA_DIR/work/$EXPLORE_CASE; OUT=$QA_WORK/explore; mkdir -p $OUT/steps
  FIXTURES=$OUT/_fixtures; export QA_WORK OUT FIXTURES KEYBOARD=software
  sim_reboot; sim_status_bar_fix ${QA_STATUS_BAR_TIME:-9:41}
  (
    eval "$(python3 -I -B $LIB/casefile.py env $QA_DIR/cases/${CASES[1]#*$'\t'})"
    source $LIB/core.sh; source $QA_DIR/flows.sh; source $QA_DIR/states.sh; source $LIB/explore.sh
    QA_PHASE=prep; QA_STEP_CUR=0
    screen_size_refresh
    source $EXPLORE
  )
  rc=$?
  print "탐색 끝(rc=$rc). 기록: $QA_WORK/locate.json"
  exit $rc
fi

# ── 실행 ──
QA_KEEP_RUNS=${QA_KEEP_RUNS:-10} QA_KEEP_DAYS=${QA_KEEP_DAYS:-14} python3 -I -B $LIB/prune.py $QA_DIR/results
RUN_DIR=$QA_DIR/results/$(date +%Y%m%d-%H%M%S)-${CONDITION// /_}
mkdir -p $RUN_DIR
FIXTURES=$RUN_DIR/_fixtures
export FIXTURES
# 이 실행이 기대한 승인·질문 상태(보고서가 "사람 승인 전"을 표시한다)
cp $QA_DIR/cases/.approved.json $RUN_DIR/approvals.json 2>/dev/null
cp $QA_DIR/gaps.json $RUN_DIR/gaps-before.json 2>/dev/null
python3 -I -B -c 'import json,sys; json.dump(dict(zip(sys.argv[2::2], sys.argv[3::2])), open(sys.argv[1],"w"), ensure_ascii=False)' \
  $RUN_DIR/run.json condition "$CONDITION" device "$DEVICE_NAME" udid "$UDID" content_size "$CONTENT_SIZE" \
  started "$(date +%Y-%m-%d\ %H:%M:%S)" app "${APP_PATH:t}" driver "$QA_DRIVER $(drv_version)" warning "$WARNING" \
  unapproved "$UNAPPROVED" pending "$(print -l -- $pending)"
# 실행별 근거 서명 키. 스크립트에는 내보내지 않는다(판정기 호출에만 넘긴다). 각본이 다 끝난 뒤 결과 폴더에 남긴다
_QA_KEY=$(python3 -I -B -c 'import secrets; print(secrets.token_hex(16))')
KB_STATE=unknown
passed=0; failed=0; T_ALL=$SECONDS
for row in $CASES; do
  id=${row%%$'\t'*}; md=$QA_DIR/cases/${row#*$'\t'}
  OUT=$RUN_DIR/$id; mkdir -p $OUT/steps
  KEYBOARD=$INPUT_OF[$id]
  print "\n━━ $id ($KEYBOARD)"
  if [[ $KEYBOARD == software && $KB_STATE != software ]]; then
    print "   화면 키보드를 위해 시뮬레이터 재부팅"; sim_reboot; sim_status_bar_fix ${QA_STATUS_BAR_TIME:-9:41}; KB_STATE=software
  elif [[ $KEYBOARD == hardware ]]; then KB_STATE=hardware; fi
  python3 -I -B $LIB/casefile.py parse $md > $OUT/case.json
  # 스크립트가 지난 실행과 다르면 steps/.changes에 diff. 승인본과 다르면 그 diff를 결과에 붙인다
  sdiff=$(python3 -I -B $LIB/approve.py record-change $QA_DIR $id)
  [[ -n $sdiff && -f $sdiff ]] && cp $sdiff $OUT/script.diff
  t0=$SECONDS
  (
    export OUT KEYBOARD
    eval "$(python3 -I -B $LIB/casefile.py env $md)"
    source $LIB/core.sh
    source $QA_DIR/flows.sh
    source $QA_DIR/states.sh
    source $QA_DIR/steps/$id.sh
    trap rec_stop EXIT
    trap 'rec_stop; exit 130' INT TERM HUP
    export QA_DIR
    QA_PHASE=prep
    screen_size_refresh
    fn=${QA_STATES[$QA_CASE_STATE]:-}
    [[ -n $fn ]] || fail_env "준비 상태를 모름" --dev "states.sh의 QA_STATES에 '$QA_CASE_STATE'가 없음"
    _log "[준비] $QA_CASE_STATE"
    $fn
    QA_PHASE=scenario
    rec_start
    scenario
    steps_finish
    ui_shot final
  ) 2> >(tee -a $OUT/stderr.log >&2)
  rc=$?
  # 녹화가 남아 있으면 닫는다(각본이 셸 오류로 끝난 경우)
  if [[ -f $OUT/.rec_pid ]] && kill -0 $(cat $OUT/.rec_pid) 2>/dev/null; then kill -INT $(cat $OUT/.rec_pid); sleep 2; fi
  # 엔진 판정 밖에서 끝났으면(셸 오류 등) 스크립트 문제로 남긴다
  if (( rc != 0 && rc != 130 )) && [[ ! -f $OUT/failure.json ]]; then
    print "{\"text\":\"스크립트가 엔진 판정 밖에서 멈춤(셸 오류)\",\"dev\":$(tail -3 $OUT/stderr.log 2>/dev/null | python3 -I -B -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))'),\"kind\":\"script\",\"phase\":\"scenario\",\"step\":0}" > $OUT/failure.json
  fi
  (( rc == 130 )) && { print "━━ $id: 중단"; exit 130; }
  [[ -f $OUT/.failed ]] && rc=1   # 서브셸 안에서 난 실패도 실패
  cov=$(QA_EVID_KEY=$_QA_KEY python3 -I -B $LIB/casefile.py coverage $OUT/case.json $OUT/evidence.jsonl --out $OUT/coverage.json)
  # 미실행·서명 불일치가 있으면 불완전, 건너뜀이 있으면(사람이 승인한 스크립트가 아니면) 건너뜀. 둘 다 통과가 아니다
  st=$(python3 -I -B $LIB/casefile.py verdict $OUT/coverage.json $rc $QA_DIR $md $QA_DIR/steps/$id.sh)
  [[ $st == pass ]] && (( passed += 1 )) || (( failed += 1 ))
  print "{\"status\":\"$st\",\"seconds\":$(( SECONDS - t0 )),\"keyboard\":\"$KEYBOARD\",\"script_hash\":\"$(shasum $QA_DIR/steps/$id.sh | cut -c1-12)\"}" > $OUT/result.json
  print "   항목: $cov"
  [[ -f $OUT/video.mp4 ]] && python3 -I -B $LIB/video.py faststart $OUT/video.mp4
  print "━━ $id: $st ($(( SECONDS - t0 ))s)"
done

cp $QA_DIR/gaps.json $RUN_DIR/gaps-after.json 2>/dev/null
(umask 077; print -r -- $_QA_KEY > $RUN_DIR/.evidence-key)
QA_EVID_KEY=$_QA_KEY QA_UNVERIFIABLE_CASE_MAX=${QA_UNVERIFIABLE_CASE_MAX:-30} QA_UNVERIFIABLE_RUN_MAX=${QA_UNVERIFIABLE_RUN_MAX:-20} \
  python3 -I -B $LIB/verify.py $RUN_DIR; VERIFY_RC=$?
python3 -I -B $LIB/metrics.py $RUN_DIR
python3 -I -B $LIB/report.py $RUN_DIR
ln -sfn $RUN_DIR $QA_DIR/results/latest
(( VERIFY_RC )) && print "재현 검증에서 막혀 이 실행은 통과로 보지 않습니다(verify.json)"
print "\n결과: 통과 $passed · 통과 아님 $failed · $(( SECONDS - T_ALL ))s"
print "보고서: $RUN_DIR/index.html"
(( failed == 0 && VERIFY_RC == 0 )) || exit 1
if (( UNAPPROVED )); then print "⚠⚠ 판정은 모두 통과했지만 사람 승인 전이라 통과가 아닙니다(exit 5)"; exit 5; fi
exit 0
