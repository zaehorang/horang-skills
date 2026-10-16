# 시뮬레이터 관리(xcrun simctl, Simulator.app). 앱 이름이나 문구는 없다.

sim_udid() {   # sim_udid <기기 이름> → udid(사용 가능한 iOS 런타임 중 마지막)
  xcrun simctl list devices available -j | python3 -I -B -c '
import json, sys
name = sys.argv[1]
devs = [d for rt, ds in json.load(sys.stdin)["devices"].items() if "iOS" in rt for d in ds if d["name"] == name]
print(devs[-1]["udid"] if devs else "")' "$1"
}

sim_boot() {
  xcrun simctl boot $UDID 2>/dev/null
  xcrun simctl bootstatus $UDID -b >/dev/null
}
sim_shutdown() { xcrun simctl shutdown $UDID >/dev/null 2>&1; }
sim_reboot() { sim_shutdown; sim_boot; }

# 영상마다 상태 표시줄이 같도록 고정
sim_status_bar_fix() {
  xcrun simctl status_bar $UDID override --time ${1:-9:41} --batteryState charged --batteryLevel 100 \
    --wifiBars 3 --cellularMode active --cellularBars 4 2>/dev/null
}
sim_status_bar_clear() { xcrun simctl status_bar $UDID clear 2>/dev/null; }

# 글씨 크기: extra-small … extra-extra-extra-large, accessibility-medium … accessibility-extra-extra-extra-large
sim_content_size() { xcrun simctl ui $UDID content_size ${1:-medium} >/dev/null 2>&1; }

# Simulator.app 창. 화면 키보드는 창이 있어야 그려진다
sim_window_open() { open -a Simulator --args -CurrentDeviceUDID $UDID; }
sim_window_quit() { osascript -e 'tell application "Simulator" to quit' >/dev/null 2>&1; _sleep 1; }
sim_window_running() { pgrep -xq Simulator; }

# ── 앱 ──
sim_install() { xcrun simctl install $UDID "$1"; }
sim_uninstall() { xcrun simctl uninstall $UDID $1 >/dev/null 2>&1; }
sim_launch() { xcrun simctl launch $UDID "$@" >/dev/null; }
sim_terminate() { xcrun simctl terminate $UDID $1 >/dev/null 2>&1; }
sim_container() { xcrun simctl get_app_container $UDID $1 data 2>/dev/null; }
sim_bundle_id() { /usr/libexec/PlistBuddy -c "Print CFBundleIdentifier" "$1/Info.plist"; }

_sleep() { perl -e "select(undef,undef,undef,$1)"; }
