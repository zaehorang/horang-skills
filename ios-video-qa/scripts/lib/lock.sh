# 전역 설정 잠금. 화면 키보드에 필요한 시뮬레이터 전역 설정은 Mac(사용자)당 하나라 한 번에 한 실행만 바꾼다.
# run.sh와 시험(scripts/tests)이 source한다.
#
# 필요한 것: LOCK(잠금 폴더 경로), lock_restore <원래 값> <udid>(죽은 실행이 남긴 설정을 되돌리는 함수)
# 잠금 폴더 안: pid, udid, orig(원래 값). 파일은 임시 파일을 mv로 놓아 반쯤 쓰인 내용이 보이지 않게 한다.
#
#   lock_acquire        0 잡음 · 3 다른 실행이 살아 있음. 죽은 실행의 잠금은 원래 값으로 되돌린 뒤 회수한다
#   lock_set_orig <값>  원래 값 기록(잡은 뒤, 설정을 바꾸기 전에)
#   lock_release        잠금 풀기(설정을 되돌린 뒤에)

LOCK_GRACE=${LOCK_GRACE:-10}   # pid가 아직 없는 잠금을 '막 잡는 중'으로 보는 시간(초)

_lock_put() { local tmp="$LOCK/.$1.$$"; print -r -- "$2" > $tmp && mv -f $tmp $LOCK/$1; }
_lock_age() { local m; m=$(stat -f %m $LOCK 2>/dev/null) || { print 0; return; }; print $(( $(date +%s) - m )); }

lock_acquire() {
  local lpid lorig ludid moved
  while ! mkdir $LOCK 2>/dev/null; do
    lpid=$(cat $LOCK/pid 2>/dev/null)
    if [[ -z $lpid ]] && (( $(_lock_age) < LOCK_GRACE )); then sleep 1; continue; fi
    if [[ -n $lpid ]] && kill -0 $lpid 2>/dev/null; then
      print "다른 실행이 진행 중입니다(pid $lpid). 화면 키보드 각본은 Mac당 한 번에 하나만 돌 수 있습니다"
      return 3
    fi
    # 죽은 실행의 잠금: 다른 이름으로 옮겨(여럿이 동시에 회수해도 한 실행만 성공) 그 안의 기록으로 되돌린다
    moved=$LOCK.reclaim.$$
    mv $LOCK $moved 2>/dev/null || continue
    if [[ $(cat $moved/pid 2>/dev/null) != "$lpid" ]]; then   # 그사이 다른 실행이 새로 잡은 잠금이었다: 돌려놓는다
      [[ -e $LOCK ]] || mv $moved $LOCK 2>/dev/null
      rm -rf $moved
      continue
    fi
    lorig=$(cat $moved/orig 2>/dev/null); ludid=$(cat $moved/udid 2>/dev/null)
    if [[ -n $lorig ]]; then
      print "▶ 지난 실행(pid ${lpid:-?})이 남긴 설정 복구: 원래 값=$lorig"
      lock_restore $lorig "$ludid"
    else
      print "⚠ 지난 실행(pid ${lpid:-?})의 원래 값 기록이 없어 전역 설정은 건드리지 않음(qa doctor로 확인)"
    fi
    rm -rf $moved
  done
  _lock_put pid $$
  _lock_put udid "${UDID:-}"
}
lock_set_orig() { _lock_put orig "$1"; }
lock_release() { rm -rf $LOCK; }
