#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MacroPad 설정 GUI (ch57x / 1189:8890 6키+노브 전용).

- 각 버튼/노브에 '키/단축키', '미디어', '앱 실행'을 클릭으로 지정.
- 저장하면 ch57x-keyboard-tool 용 YAML을 생성해 패드에 바로 업로드.
- '앱 실행'은 일반 키보드에 없는 F14~F18(→XF86Launch5~9 키심)을 자동 배정하고
  GNOME 커스텀 단축키(키심->명령)를 자동 등록/정리한다.
- 소스 오브 트루스: ~/.config/macropad/padconf.json (여기서 YAML/단축키를 생성).

권한: 패드 USB 접근(50-ch57x udev 규칙으로 sudo 불필요), GNOME(gsettings) 세션에서 실행.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "ch57x-keyboard-tool")
YAML_PATH = os.path.join(HERE, "config.yaml")
STATE_DIR = os.path.expanduser("~/.config/macropad")
STATE_PATH = os.path.join(STATE_DIR, "padconf.json")

VENDOR_ID = "4489"      # 0x1189
PRODUCT_ID = "34960"    # 0x8890

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
}


# ---------------- 상태 로드/저장 ----------------
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
            st.setdefault("buttons", DEFAULT_STATE["buttons"])
            st.setdefault("knob", DEFAULT_STATE["knob"])
            return st
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_STATE))


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)


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

    msg = "패드 적용 완료. " + sc_msg
    if warnings:
        msg += "\n주의:\n- " + "\n- ".join(warnings)
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


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--apply":
        ok, msg = apply_state(load_state())
        print(msg)
        sys.exit(0 if ok else 1)
    make_gui()
