#!/bin/zsh
# 전역 설정 잠금(lib/lock.sh): 살아 있는 실행은 막고, 죽은 실행은 원래 값으로 되돌린 뒤 회수하고, 막 잡는 중인 잠금은 기다린다.
# 실제 전역 설정은 건드리지 않는다(lock_restore를 기록 함수로 바꾼다). 결과 줄: ok … / FAIL …
LIB=${0:A:h:h}/lib
TMP=$(mktemp -d -t qa-lock)
LOCK=$TMP/lock.d
RESTORED=$TMP/restored
lock_restore() { print -r -- "$1 ${2:-}" >> $RESTORED; }
source $LIB/lock.sh
t() { if eval "$2"; then print "ok $1"; else print "FAIL $1"; fi; }

UDID=dev-A
lock_acquire >/dev/null; rc=$?
t "빈 잠금을 잡음" '(( rc == 0 )) && [[ $(cat $LOCK/pid) == $$ && $(cat $LOCK/udid) == dev-A ]]'
lock_set_orig 0
t "원래 값 기록" '[[ $(cat $LOCK/orig) == 0 ]]'
t "임시 파일이 남지 않음" '[[ -z $(print $LOCK/.*(N)) ]]'
lock_release

# 살아 있는 다른 실행
sleep 30 & live=$!
mkdir $LOCK; print $live > $LOCK/pid; print 1 > $LOCK/orig
out=$(lock_acquire); rc=$?
t "살아 있는 실행이면 3" '(( rc == 3 ))'
t "살아 있는 실행의 설정은 되돌리지 않음" '[[ ! -f $RESTORED ]]'
t "살아 있는 실행의 잠금은 그대로" '[[ $(cat $LOCK/pid) == $live ]]'
kill $live; wait $live 2>/dev/null

# 죽은 실행(원래 값 있음) → 그 값으로 되돌리고 회수
lock_acquire >/dev/null; rc=$?
t "죽은 실행의 잠금 회수" '(( rc == 0 )) && [[ $(cat $LOCK/pid) == $$ ]]'
t "죽은 실행의 원래 값으로 되돌림" '[[ $(cat $RESTORED) == "1 " ]]'
lock_release; rm -f $RESTORED

# 죽은 실행(원래 값 기록 전에 죽음) → 설정을 건드리지 않음
mkdir $LOCK; print 999999 > $LOCK/pid; print dev-B > $LOCK/udid
out=$(lock_acquire); rc=$?
t "원래 값이 없으면 되돌리지 않음" '(( rc == 0 )) && [[ ! -f $RESTORED ]] && [[ $out == *"건드리지 않음"* ]]'
lock_release

# 막 만든 잠금(pid 쓰기 전): 기다린 뒤에야 회수
mkdir $LOCK
LOCK_GRACE=2
s=$SECONDS; lock_acquire >/dev/null; rc=$?
t "pid 없는 새 잠금은 바로 회수하지 않음" '(( rc == 0 && SECONDS - s >= 1 ))'
lock_release

# run.sh: 잠금을 잡은 뒤에만 정리 trap을 건다(잠금 실패 때 다른 실행의 기기·설정을 건드리지 않게)
RUN=${0:A:h:h}/run.sh
la=$(grep -n '^lock_acquire || exit 3' $RUN | cut -d: -f1); tr=$(grep -n '^trap cleanup EXIT' $RUN | cut -d: -f1)
t "run.sh: trap은 잠금 뒤" '[[ -n $la && -n $tr ]] && (( tr > la ))'
t "run.sh: cleanup은 잠금을 잡았을 때만" 'grep -q "(( LOCKED )) || return 0" $RUN'
rm -rf $TMP
