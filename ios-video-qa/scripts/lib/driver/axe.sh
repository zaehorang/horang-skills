# 실행 도구 어댑터: AXe. 엔진에서 AXe를 부르는 유일한 파일이다.
# core.sh와 각본 스크립트는 여기의 drv_* 함수만 쓴다. 다른 도구로 바꾸려면 이 파일만 같은 이름으로 다시 쓴다.
#
# 필요한 변수: UDID(대상 시뮬레이터), DRV_DIR(이 파일의 폴더)
# 좌표는 포인트(앱 화면 좌표)다.

DRV_DIR=${DRV_DIR:-${LIB}/driver}
_AXQ=$DRV_DIR/axq.py

drv_check() { command -v axe >/dev/null || { print "실행 도구 axe가 없습니다: brew install cameroncooke/axe/axe"; return 1; }; }
drv_version() { axe --version 2>/dev/null; }

# ── 화면 읽기 ──
drv_tree() { axe describe-ui --udid $UDID 2>/dev/null; }
# drv_q <명령> <옵션…>: 지금 화면에서 요소를 찾는다(axq.py 옵션). 성공 0, 요소 없음 1, 화면 정보 읽기 실패 2
drv_q() {
  local tree
  tree=$(axe describe-ui --udid $UDID 2>/dev/null) || return 2
  [[ -n $tree ]] || return 2
  print -r -- "$tree" | python3 -I -B $_AXQ "$@"
}
# drv_q_in <트리 JSON> <명령> <옵션…>: 미리 읽어 둔 트리에서 찾는다
drv_q_in() { print -r -- "$1" | python3 -I -B $_AXQ "${@:2}"; }
drv_screen_size() { drv_q screen; }
drv_screenshot() { axe screenshot --udid $UDID --output "$1" >/dev/null 2>&1; }

# ── 조작 ──
drv_tap() { axe tap --udid $UDID -x $1 -y $2 >/dev/null; }
drv_press() { axe touch -x $1 -y $2 --down --up --delay ${3:-0.15} --udid $UDID >/dev/null; }
drv_swipe() {   # drv_swipe <x1> <y1> <x2> <y2> [초]
  local extra=(); [[ -n ${5:-} ]] && extra=(--duration $5)
  axe swipe --udid $UDID --start-x $1 --start-y $2 --end-x $3 --end-y $4 $extra >/dev/null
}
# drv_type <키 문자열>: 하드웨어 키보드 키 이벤트(HID). 글자가 아니라 키를 보낸다
drv_type() { axe type "$1" --udid $UDID >/dev/null; }
drv_key() { axe key $1 --udid $UDID >/dev/null; }
drv_key_seq() { axe key-sequence --keycodes "$1" --udid $UDID >/dev/null; }

# ── 녹화 ──
DRV_REC_PID=""
drv_record_start() {   # drv_record_start <출력 mp4> [fps] [scale]
  axe record-video --udid $UDID --fps ${2:-30} --scale ${3:-0.5} --output "$1" > "${1:h}/record.log" 2>&1 &
  DRV_REC_PID=$!
  print $DRV_REC_PID > "${1:h}/.rec_pid"   # 각본이 셸 오류로 끝나도 실행기가 녹화를 닫을 수 있게
}
drv_record_stop() {
  [[ -n $DRV_REC_PID ]] || return 0
  kill -INT $DRV_REC_PID 2>/dev/null; wait $DRV_REC_PID 2>/dev/null
  DRV_REC_PID=""
}
