#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MacroPad 설정 GUI (ch57x / 1189:8890 6키+노브 전용).

- 각 버튼/노브에 '키/단축키', '미디어', '앱 실행'을 클릭으로 지정.
- 저장하면 ch57x-keyboard-tool 용 YAML을 생성해 패드에 바로 업로드.
- '앱 실행'은 일반 키보드에 없는 F14~F18(→XF86Launch5~9 키심)을 자동 배정하고
  GNOME 커스텀 단축키(키심->명령)를 자동 등록/정리한다.
- LED 백라이트 모드를 눌러보며 찾아서 저장하고, 로그인/적용 시 자동 복원한다.
- 소스 오브 트루스: ~/.config/macropad/padconf.json (여기서 YAML/단축키를 생성).

권한: 패드 USB 접근(50-ch57x udev 규칙으로 sudo 불필요), GNOME(gsettings) 세션에서 실행.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "ch57x-keyboard-tool")
YAML_PATH = os.path.join(HERE, "config.yaml")
STATE_DIR = os.path.expanduser("~/.config/macropad")
STATE_PATH = os.path.join(STATE_DIR, "padconf.json")

VENDOR_ID = "4489"      # 0x1189
PRODUCT_ID = "34960"    # 0x8890

# ---- LED ----
# 이 모델(0x8890)에서 도구가 제공하는 LED 제어는 '모드 인덱스' 하나뿐이다.
# (색/밝기/키별 지정은 0x8840·0x8842 전용이라 여기선 불가.)
# ch57x-keyboard-tool 은 모드 바이트를 범위 검사 없이 그대로 보내므로 어떤 값이든
# '성공'으로 보인다. 실제 개수는 다음 근거로 3개 안팎:
#   - rOzzy1987/MacroPad 의 layouts.txt: `4489:34960` 항목이 `1:5:0:0:3`
#     (레이어1 / 시퀀스5 / 딜레이X / 색상X / LED모드 3) 이고, 같은 README 는
#     "only has 3 modes, on being the Off state" 라고 적고 있다.
#   - 실기 확인: 3 이후로는 새로운 효과가 보이지 않음.
# 그래서 0~3 만 노출한다(0 이 꺼짐).
LED_MIN_MODE = 0
LED_MAX_MODE = 3
LED_SERVICE_NAME = "macropad-led.service"
LED_SERVICE_DIR = os.path.expanduser("~/.config/systemd/user")

# '앱 실행'에 쓸 F키 후보 (F13=XF86Tools 는 설정과 충돌하므로 제외).
# evdev 키코드 = X11 키코드 - 8.  F14->X키코드192 ... F18->196.
LAUNCH_FKEYS = [
    ("f14", 192), ("f15", 193), ("f16", 194), ("f17", 195), ("f18", 196),
]

MEDIA_OPTIONS = [
    ("volumeup", "볼륨 ▲"), ("volumedown", "볼륨 ▼"), ("mute", "음소거"),
    ("play", "재생/정지"), ("next", "다음 곡"), ("previous", "이전 곡"),
    ("wheelup", "휠 ▲"), ("wheeldown", "휠 ▼"), ("click", "마우스 클릭"),
]
KEY_PRESETS = [
    "1", "2", "3", "escape", "enter", "tab", "space", "backspace", "delete",
    "f5", "left", "right", "up", "down", "home", "end",
    "ctrl-c", "ctrl-v", "ctrl-x", "ctrl-z", "ctrl-a", "ctrl-s",
    "ctrl-shift-t", "alt-tab", "shift-tab",
]
APP_PRESETS = [
    ("code", "VS Code"), ("terminator", "Terminator"),
    ("gnome-terminal", "GNOME 터미널"), ("firefox", "Firefox"),
    ("nautilus", "파일 관리자"), ("gnome-control-center", "설정"),
]

BUTTON_LABELS = ["상단 왼쪽", "상단 가운데", "상단 오른쪽",
                 "하단 왼쪽", "하단 가운데", "하단 오른쪽"]
KNOB_LABELS = {"ccw": "노브 ◀ 왼쪽회전", "press": "노브 ● 누르기", "cw": "노브 ▶ 오른쪽회전"}

DEFAULT_STATE = {
    "buttons": [
        {"type": "key", "value": "1"},
        {"type": "key", "value": "2"},
        {"type": "key", "value": "escape"},
        {"type": "launch", "value": "code"},
        {"type": "launch", "value": "terminator"},
        {"type": "key", "value": "f5"},
    ],
    "knob": {
        "ccw": {"type": "media", "value": "volumedown"},
        "press": {"type": "media", "value": "mute"},
        "cw": {"type": "media", "value": "volumeup"},
    },
    # mode: 적용할 LED 모드 인덱스, restore_on_login: 로그인 시 자동 복원 여부
    "led": {"mode": 1, "restore_on_login": True},
}


# ---------------- 상태 로드/저장 ----------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
            st.setdefault("buttons", DEFAULT_STATE["buttons"])
            st.setdefault("knob", DEFAULT_STATE["knob"])
            # 예전 버전 설정 파일에는 led 항목이 없다.
            led = st.get("led")
            if not isinstance(led, dict):
                led = {}
            led.setdefault("mode", DEFAULT_STATE["led"]["mode"])
            led.setdefault("restore_on_login",
                           DEFAULT_STATE["led"]["restore_on_login"])
            led["mode"] = clamp_led_mode(led["mode"])
            led["restore_on_login"] = bool(led["restore_on_login"])
            st["led"] = led
            return st
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


# ---------------- LED ----------------
def clamp_led_mode(mode):
    try:
        mode = int(mode)
    except (TypeError, ValueError):
        mode = DEFAULT_STATE["led"]["mode"]
    return max(LED_MIN_MODE, min(LED_MAX_MODE, mode))


def apply_led(mode, retries=1, delay=1.0):
    """패드에 LED 모드를 적용. (성공?, 메시지).

    retries>1 이면 장치가 아직 안 올라온 경우를 대비해 재시도한다
    (로그인 직후 복원 등).
    """
    mode = clamp_led_mode(mode)
    last = ""
    for attempt in range(max(1, retries)):
        r = run_tool(["--product-id", PRODUCT_ID, "led", str(mode)])
        if r.returncode == 0:
            return True, "LED 모드 %d 적용" % mode
        last = (r.stderr or r.stdout or "").strip()
        if attempt + 1 < max(1, retries):
            time.sleep(delay)
    return False, "LED 적용 실패: %s" % (last or "알 수 없는 오류")


def led_service_unit_text():
    py = sys.executable or "/usr/bin/python3"
    script = os.path.abspath(__file__)
    return (
        "[Unit]\n"
        "Description=MacroPad(ch57x) LED 모드 복원\n"
        "After=graphical-session.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "ExecStart=%s %s --restore-led\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n" % (py, script)
    )


def set_led_autostart(enabled):
    """로그인 시 LED 복원 systemd 사용자 서비스 설치/제거. (성공?, 메시지)"""
    unit_path = os.path.join(LED_SERVICE_DIR, LED_SERVICE_NAME)
    try:
        if enabled:
            os.makedirs(LED_SERVICE_DIR, exist_ok=True)
            with open(unit_path, "w", encoding="utf-8") as f:
                f.write(led_service_unit_text())
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           capture_output=True, text=True)
            r = subprocess.run(["systemctl", "--user", "enable", LED_SERVICE_NAME],
                               capture_output=True, text=True)
            if r.returncode != 0:
                return False, "서비스 등록 실패: %s" % (r.stderr or r.stdout).strip()
            return True, "로그인 시 LED 자동 복원 켜짐"
        else:
            subprocess.run(["systemctl", "--user", "disable", LED_SERVICE_NAME],
                           capture_output=True, text=True)
            if os.path.exists(unit_path):
                os.remove(unit_path)
            subprocess.run(["systemctl", "--user", "daemon-reload"],
                           capture_output=True, text=True)
            return True, "로그인 시 LED 자동 복원 꺼짐"
    except Exception as e:
        return False, "자동 복원 설정 실패: %s" % e


# ---------------- 키심 탐지 (앱 실행용) ----------------
def detect_launch_keysyms():
    """xmodmap 으로 F14~F18 의 실제 X11 키심을 조회. {fkey: keysym}."""
    result = {}
    try:
        out = subprocess.check_output(["xmodmap", "-pke"], text=True,
                                      stderr=subprocess.DEVNULL)
    except Exception:
        return result
    kc_sym = {}
    for line in out.splitlines():
        m = re.match(r"keycode\s+(\d+)\s*=\s*(\S+)?", line)
        if m and m.group(2):
            kc_sym[int(m.group(1))] = m.group(2)
    for fkey, kc in LAUNCH_FKEYS:
        sym = kc_sym.get(kc)
        if sym and sym != "NoSymbol":
            result[fkey] = sym
    return result


# ---------------- YAML 생성 ----------------
def action_to_chord(action, launch_alloc):
    """액션 -> ch57x YAML 에 넣을 chord 문자열."""
    t = action.get("type")
    v = action.get("value", "")
    if t == "launch":
        # launch_alloc: 이 액션에 배정된 f키
        return launch_alloc.get(id(action), "escape")
    return v or "escape"


def build_yaml_and_launches(state):
    """YAML 문자열과, 등록할 launch 목록[(keysym, command)] 반환."""
    keysyms = detect_launch_keysyms()          # {fkey: keysym}
    pool = [fk for fk, _ in LAUNCH_FKEYS if fk in keysyms]
    launch_alloc = {}                          # id(action) -> fkey
    launches = []                              # (keysym, command)
    warnings = []

    # 버튼 순회하며 launch 에 f키 배정
    for i, action in enumerate(state["buttons"]):
        if action.get("type") == "launch":
            if pool:
                fk = pool.pop(0)
                launch_alloc[id(action)] = fk
                launches.append((keysyms[fk], action.get("value", "").strip()))
            else:
                warnings.append("앱 실행 슬롯이 너무 많음(F14~F18 소진). '%s' 는 무시됨."
                                % action.get("value"))
                launch_alloc[id(action)] = "escape"
    # 노브도 launch 허용
    for k in ("ccw", "press", "cw"):
        action = state["knob"][k]
        if action.get("type") == "launch":
            if pool:
                fk = pool.pop(0)
                launch_alloc[id(action)] = fk
                launches.append((keysyms[fk], action.get("value", "").strip()))
            else:
                warnings.append("앱 실행 슬롯 초과: 노브 '%s' 무시" % k)
                launch_alloc[id(action)] = "escape"

    b = [action_to_chord(a, launch_alloc) for a in state["buttons"]]
    kn = {k: action_to_chord(state["knob"][k], launch_alloc)
          for k in ("ccw", "press", "cw")}

    yaml = (
        "orientation: normal\n"
        "rows: 2\n"
        "columns: 3\n"
        "knobs: 1\n"
        "layers:\n"
        "  - buttons:\n"
        '      - ["%s", "%s", "%s"]\n'
        '      - ["%s", "%s", "%s"]\n'
        "    knobs:\n"
        '      - ccw: "%s"\n'
        '        press: "%s"\n'
        '        cw: "%s"\n'
    ) % (b[0], b[1], b[2], b[3], b[4], b[5], kn["ccw"], kn["press"], kn["cw"])
    return yaml, launches, warnings


# ---------------- 적용: 업로드 + 단축키 ----------------
def run_tool(args, stdin=None):
    return subprocess.run([TOOL] + args, input=stdin, capture_output=True, text=True)


def sync_gnome_shortcuts(launches):
    """macropad-* 커스텀 단축키를 launches 로 재구성."""
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"

    def gset(*a):
        subprocess.run(["gsettings"] + list(a), capture_output=True, text=True)

    def gget(*a):
        return subprocess.run(["gsettings", "get"] + list(a),
                              capture_output=True, text=True).stdout.strip()

    # 기존 목록에서 macropad-* 제거
    cur = gget(schema, "custom-keybindings")
    paths = re.findall(r"'([^']+)'", cur)
    paths = [p for p in paths if "/macropad-" not in p]

    # 새 launch 등록
    for idx, (keysym, command) in enumerate(launches):
        slot = "macropad-app%d" % idx
        path = "%s/%s/" % (base, slot)
        kb = "%s.custom-keybinding:%s" % (schema, path)
        gset("set", kb, "name", "MacroPad %s" % command)
        gset("set", kb, "command", command)
        gset("set", kb, "binding", keysym)
        paths.append(path)

    newlist = "[%s]" % ", ".join("'%s'" % p for p in paths) if paths else "@as []"
    gset("set", schema, "custom-keybindings", newlist)


def apply_state(state):
    """상태 -> YAML 생성 -> validate -> 업로드 -> 단축키 동기화. (성공?, 메시지)"""
    yaml, launches, warnings = build_yaml_and_launches(state)
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        f.write(yaml)

    v = run_tool(["validate"], stdin=yaml)
    if v.returncode != 0:
        return False, "YAML 검증 실패:\n" + (v.stderr or v.stdout)

    up = run_tool(["--product-id", PRODUCT_ID, "upload"], stdin=yaml)
    if up.returncode != 0:
        return False, "패드 업로드 실패:\n" + (up.stderr or up.stdout)

    try:
        sync_gnome_shortcuts(launches)
        sc_msg = "단축키 %d개 등록" % len(launches)
    except Exception as e:
        sc_msg = "단축키 등록 경고: %s" % e

    # 키 매핑 업로드 뒤에 LED 를 다시 적용한다.
    # (업로드 과정에서 백라이트가 초기화되는 경우가 있어 순서가 중요)
    led_ok, led_msg = apply_led(state.get("led", {}).get("mode",
                                                         DEFAULT_STATE["led"]["mode"]))

    notes = list(warnings)
    if led_ok:
        msg = "패드 적용 완료. %s, %s" % (sc_msg, led_msg)
    else:
        msg = "패드 적용 완료. %s" % sc_msg
        notes.append(led_msg)
    if notes:
        msg += "\n주의:\n- " + "\n- ".join(notes)
    return True, msg


# ======================= GUI =======================
def make_gui(run=True):
    from PyQt5 import QtWidgets, QtCore

    class Main(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("MacroPad 설정 (ch57x 1189:8890)")
            self.state = load_state()
            self.sel = ("button", 0)
            self._build()
            self._refresh_cells()
            self._load_editor()

        def _build(self):
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QHBoxLayout(central)

            left = QtWidgets.QVBoxLayout()
            left.addWidget(QtWidgets.QLabel("<b>버튼 (3 x 2)</b>"))
            grid = QtWidgets.QGridLayout()
            self.cell_btns = []
            for i in range(6):
                b = QtWidgets.QPushButton()
                b.setMinimumSize(140, 66)
                b.clicked.connect(lambda _, idx=i: self._select(("button", idx)))
                grid.addWidget(b, i // 3, i % 3)
                self.cell_btns.append(b)
            left.addLayout(grid)
            left.addWidget(QtWidgets.QLabel("<b>노브</b>"))
            knob = QtWidgets.QHBoxLayout()
            self.knob_btns = {}
            for k in ("ccw", "press", "cw"):
                b = QtWidgets.QPushButton()
                b.setMinimumSize(140, 52)
                b.clicked.connect(lambda _, kk=k: self._select(("knob", kk)))
                knob.addWidget(b)
                self.knob_btns[k] = b
            left.addLayout(knob)
            left.addWidget(self._build_led_box())
            left.addStretch(1)
            root.addLayout(left)

            right = QtWidgets.QVBoxLayout()
            self.sel_label = QtWidgets.QLabel()
            right.addWidget(self.sel_label)
            right.addWidget(QtWidgets.QLabel("동작 종류"))
            self.type_combo = QtWidgets.QComboBox()
            self.type_combo.addItem("키 / 단축키", "key")
            self.type_combo.addItem("미디어 / 볼륨", "media")
            self.type_combo.addItem("앱 실행", "launch")
            self.type_combo.currentIndexChanged.connect(self._type_changed)
            right.addWidget(self.type_combo)

            right.addWidget(QtWidgets.QLabel("값"))
            self.key_combo = QtWidgets.QComboBox()
            self.key_combo.setEditable(True)
            self.key_combo.addItems(KEY_PRESETS)
            right.addWidget(self.key_combo)

            self.media_combo = QtWidgets.QComboBox()
            for mid, ml in MEDIA_OPTIONS:
                self.media_combo.addItem(ml, mid)
            right.addWidget(self.media_combo)

            self.app_combo = QtWidgets.QComboBox()
            self.app_combo.setEditable(True)
            for cmd, name in APP_PRESETS:
                self.app_combo.addItem("%s (%s)" % (name, cmd), cmd)
            right.addWidget(self.app_combo)

            self.hint = QtWidgets.QLabel()
            self.hint.setStyleSheet("color:#777;font-size:11px;")
            self.hint.setWordWrap(True)
            right.addWidget(self.hint)

            self.apply_slot_btn = QtWidgets.QPushButton("이 슬롯에 반영(임시)")
            self.apply_slot_btn.clicked.connect(self._save_slot)
            right.addWidget(self.apply_slot_btn)

            right.addStretch(1)
            self.upload_btn = QtWidgets.QPushButton("💾 저장 & 패드에 적용")
            self.upload_btn.setStyleSheet("font-weight:bold;padding:8px;")
            self.upload_btn.clicked.connect(self._apply_all)
            right.addWidget(self.upload_btn)
            self.status = QtWidgets.QLabel("준비됨")
            self.status.setWordWrap(True)
            right.addWidget(self.status)
            root.addLayout(right)

        def _build_led_box(self):
            """LED 모드 찾기/저장 UI.

            0x8890 은 '모드 인덱스'만 바꿀 수 있고 도구가 유효 범위를 알려주지
            않으므로, 인덱스를 순회하며 눈으로 고르는 방식으로 만든다.
            """
            box = QtWidgets.QGroupBox("LED 백라이트")
            v = QtWidgets.QVBoxLayout(box)

            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel("모드"))
            self.led_spin = QtWidgets.QSpinBox()
            self.led_spin.setRange(LED_MIN_MODE, LED_MAX_MODE)
            self.led_spin.setValue(clamp_led_mode(self.state["led"]["mode"]))
            row.addWidget(self.led_spin)

            prev_btn = QtWidgets.QPushButton("◀")
            prev_btn.setFixedWidth(36)
            prev_btn.setToolTip("이전 모드로 바꿔 바로 적용")
            prev_btn.clicked.connect(lambda: self._led_step(-1))
            row.addWidget(prev_btn)

            next_btn = QtWidgets.QPushButton("▶")
            next_btn.setFixedWidth(36)
            next_btn.setToolTip("다음 모드로 바꿔 바로 적용")
            next_btn.clicked.connect(lambda: self._led_step(1))
            row.addWidget(next_btn)

            try_btn = QtWidgets.QPushButton("지금 적용해보기")
            try_btn.clicked.connect(self._led_try)
            row.addWidget(try_btn)
            row.addStretch(1)
            v.addLayout(row)

            row2 = QtWidgets.QHBoxLayout()
            self.led_cycle_btn = QtWidgets.QPushButton("🔄 자동 순회")
            self.led_cycle_btn.setCheckable(True)
            self.led_cycle_btn.setToolTip("2초마다 다음 모드로 넘어감. "
                                          "마음에 드는 모드에서 다시 눌러 멈추세요.")
            self.led_cycle_btn.toggled.connect(self._led_cycle_toggled)
            row2.addWidget(self.led_cycle_btn)

            save_btn = QtWidgets.QPushButton("이 모드로 저장")
            save_btn.clicked.connect(self._led_save)
            row2.addWidget(save_btn)
            row2.addStretch(1)
            v.addLayout(row2)

            self.led_login_chk = QtWidgets.QCheckBox("로그인할 때 이 LED 모드 자동 복원")
            self.led_login_chk.setChecked(bool(self.state["led"]["restore_on_login"]))
            self.led_login_chk.toggled.connect(self._led_login_toggled)
            v.addWidget(self.led_login_chk)

            note = QtWidgets.QLabel(
                "이 패드(0x8890)는 '모드 번호'만 바꿀 수 있고 색·밝기 지정은 불가합니다. "
                "모드는 3개뿐이라 0~3 만 보여줍니다 (0 = 꺼짐). "
                "◀▶ 나 자동 순회로 눌러보고 마음에 드는 번호를 저장하세요.")
            note.setStyleSheet("color:#777;font-size:11px;")
            note.setWordWrap(True)
            v.addWidget(note)

            self.led_cycle_timer = QtCore.QTimer(self)
            self.led_cycle_timer.setInterval(2000)
            self.led_cycle_timer.timeout.connect(lambda: self._led_step(1))
            return box

        def _led_try(self):
            mode = self.led_spin.value()
            ok, msg = apply_led(mode)
            self.status.setText(("✅ " if ok else "❌ ") + msg +
                                ("  (저장하려면 '이 모드로 저장')" if ok else ""))

        def _led_step(self, delta):
            span = LED_MAX_MODE - LED_MIN_MODE + 1
            nxt = LED_MIN_MODE + ((self.led_spin.value() - LED_MIN_MODE + delta) % span)
            self.led_spin.setValue(nxt)
            self._led_try()

        def _led_cycle_toggled(self, on):
            if on:
                self.led_cycle_btn.setText("⏹ 순회 멈춤")
                self.led_cycle_timer.start()
            else:
                self.led_cycle_btn.setText("🔄 자동 순회")
                self.led_cycle_timer.stop()

        def _led_save(self):
            if self.led_cycle_btn.isChecked():
                self.led_cycle_btn.setChecked(False)   # 순회 중이면 멈춤
            mode = self.led_spin.value()
            self.state["led"]["mode"] = mode
            save_state(self.state)
            ok, msg = apply_led(mode)
            self.status.setText(("✅ " if ok else "❌ ") +
                                "LED 모드 %d 저장됨. %s" % (mode, msg))

        def _led_login_toggled(self, on):
            self.state["led"]["restore_on_login"] = bool(on)
            save_state(self.state)
            ok, msg = set_led_autostart(on)
            self.status.setText(("✅ " if ok else "❌ ") + msg)


        def _cur_action(self):
            kind, key = self.sel
            if kind == "button":
                return self.state["buttons"][key]
            return self.state["knob"][key]

        def _select(self, sel):
            self.sel = sel
            self._refresh_cells()
            self._load_editor()

        def _load_editor(self):
            kind, key = self.sel
            name = BUTTON_LABELS[key] if kind == "button" else KNOB_LABELS[key]
            self.sel_label.setText("<b>선택: %s</b>" % name)
            a = self._cur_action()
            idx = {"key": 0, "media": 1, "launch": 2}.get(a.get("type"), 0)
            self.type_combo.setCurrentIndex(idx)
            self._type_changed()
            t, v = a.get("type"), a.get("value", "")
            if t == "media":
                mi = self.media_combo.findData(v)
                if mi >= 0:
                    self.media_combo.setCurrentIndex(mi)
            elif t == "launch":
                ai = self.app_combo.findData(v)
                if ai >= 0:
                    self.app_combo.setCurrentIndex(ai)
                else:
                    self.app_combo.setEditText(v)
            else:
                self.key_combo.setEditText(v)

        def _type_changed(self):
            t = self.type_combo.currentData()
            self.key_combo.setVisible(t == "key")
            self.media_combo.setVisible(t == "media")
            self.app_combo.setVisible(t == "launch")
            hints = {
                "key": "키 이름 또는 조합. 예: 1 · escape · f5 · ctrl-c · alt-tab · left",
                "media": "노브 회전에 볼륨▲/▼ 지정하면 볼륨 다이얼처럼 사용 가능",
                "launch": "명령 입력 시 F14~F18 자동배정 + GNOME 단축키 등록. 예: code, firefox",
            }
            self.hint.setText(hints.get(t, ""))

        def _save_slot(self):
            t = self.type_combo.currentData()
            if t == "media":
                v = self.media_combo.currentData()
            elif t == "launch":
                idx = self.app_combo.currentIndex()
                typed = self.app_combo.currentText().strip()
                if (idx >= 0 and self.app_combo.itemText(idx) == typed
                        and self.app_combo.itemData(idx)):
                    v = self.app_combo.itemData(idx)   # 프리셋 선택
                else:
                    v = typed                          # 직접 입력한 명령
            else:
                v = self.key_combo.currentText().strip()
            a = self._cur_action()
            a["type"] = t
            a["value"] = v
            save_state(self.state)
            self._refresh_cells()
            self.status.setText("슬롯 저장됨 (아직 패드 미적용 — '저장 & 패드에 적용' 눌러야 반영)")

        def _summary(self, a):
            t, v = a.get("type"), a.get("value", "")
            if t == "media":
                return "미디어: %s" % dict(MEDIA_OPTIONS).get(v, v)
            if t == "launch":
                return "실행: %s" % v
            return "키: %s" % v

        def _refresh_cells(self):
            for i, b in enumerate(self.cell_btns):
                a = self.state["buttons"][i]
                b.setText("%s\n%s" % (BUTTON_LABELS[i], self._summary(a)))
                b.setStyleSheet("border:2px solid #2d7;font-weight:bold;"
                                if self.sel == ("button", i) else "")
            for k, b in self.knob_btns.items():
                a = self.state["knob"][k]
                b.setText("%s\n%s" % (KNOB_LABELS[k], self._summary(a)))
                b.setStyleSheet("border:2px solid #2d7;font-weight:bold;"
                                if self.sel == ("knob", k) else "")

        def _apply_all(self):
            self._save_slot()
            self.status.setText("적용 중...")
            QtWidgets.QApplication.processEvents()
            ok, msg = apply_state(self.state)
            self.status.setText(("✅ " if ok else "❌ ") + msg)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    w = Main()
    w.resize(760, 460)
    if not run:
        return app, w
    w.show()
    sys.exit(app.exec_())


USAGE = """사용법:
  padconf.py                  설정 GUI 실행
  padconf.py --apply          저장된 설정(키+LED)을 패드에 적용
  padconf.py --led N          LED 모드 N 을 적용하고 저장
  padconf.py --restore-led    저장된 LED 모드를 복원 (로그인 서비스용, 재시도 포함)
  padconf.py --led-autostart on|off
                              로그인 시 LED 자동 복원 서비스 등록/해제
"""

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "--apply":
        ok, msg = apply_state(load_state())
        print(msg)
        sys.exit(0 if ok else 1)

    if arg == "--led":
        if len(sys.argv) < 3:
            print(USAGE)
            sys.exit(2)
        st = load_state()
        st["led"]["mode"] = clamp_led_mode(sys.argv[2])
        save_state(st)
        ok, msg = apply_led(st["led"]["mode"])
        print(msg)
        sys.exit(0 if ok else 1)

    if arg == "--restore-led":
        st = load_state()
        # 로그인 직후에는 USB 장치가 아직 안 올라왔을 수 있어 여러 번 시도한다.
        ok, msg = apply_led(st["led"]["mode"], retries=10, delay=2.0)
        print(msg)
        sys.exit(0 if ok else 1)

    if arg == "--led-autostart":
        if len(sys.argv) < 3 or sys.argv[2] not in ("on", "off"):
            print(USAGE)
            sys.exit(2)
        on = sys.argv[2] == "on"
        st = load_state()
        st["led"]["restore_on_login"] = on
        save_state(st)
        ok, msg = set_led_autostart(on)
        print(msg)
        sys.exit(0 if ok else 1)

    if arg in ("-h", "--help"):
        print(USAGE)
        sys.exit(0)

    make_gui()
