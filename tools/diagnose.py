#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""매크로패드 원시 입력 진단 - 각 버튼/노브가 실제로 무슨 이벤트를 보내는지 출력.
사용:  (macropad.py 앱을 먼저 끈 뒤)
       python3 ~/macropad/diagnose.py
    그리고 버튼1~6, 노브 좌회전/우회전/누르기를 하나씩 천천히 눌러보고
    출력 전체를 복사해서 붙여넣으세요. Ctrl+C 로 종료.
"""
import sys, time
import evdev
from evdev import ecodes

VENDOR, PRODUCT = 0x1189, 0x8890

devs = []
for path in evdev.list_devices():
    try:
        d = evdev.InputDevice(path)
    except Exception:
        continue
    if d.info.vendor == VENDOR and d.info.product == PRODUCT:
        devs.append(d)

if not devs:
    print("매크로패드(1189:8890) 미발견. 연결/권한 확인.")
    sys.exit(1)

print("=== 발견된 인터페이스 ===")
for d in devs:
    print(f"  {d.path}  '{d.name}'  caps:", end=" ")
    caps = d.capabilities(verbose=False)
    print("EV_KEY" if ecodes.EV_KEY in caps else "",
          "EV_REL" if ecodes.EV_REL in caps else "")
print("\n=== 지금부터 버튼/노브를 하나씩 눌러보세요 (Ctrl+C 종료) ===\n")

import select
fdmap = {d.fd: d for d in devs}
try:
    while True:
        r, _, _ = select.select(fdmap.keys(), [], [], 1.0)
        for fd in r:
            dev = fdmap[fd]
            for ev in dev.read():
                if ev.type == ecodes.EV_KEY:
                    name = ecodes.KEY.get(ev.code, f"code{ev.code}")
                    val = {0: "release", 1: "PRESS", 2: "repeat"}.get(ev.value, ev.value)
                    tag = dev.path.rsplit("/", 1)[-1]
                    print(f"[{tag}] KEY  {name} (code={ev.code})  {val}")
                elif ev.type == ecodes.EV_REL:
                    name = ecodes.REL.get(ev.code, f"rel{ev.code}")
                    tag = dev.path.rsplit("/", 1)[-1]
                    print(f"[{tag}] REL  {name}  value={ev.value}")
except KeyboardInterrupt:
    print("\n종료.")
