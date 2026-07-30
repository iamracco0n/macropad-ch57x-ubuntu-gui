# macropad-ch57x-ubuntu-gui

A small **Linux GUI** to configure cheap **6-key + knob macro pads** (the ubiquitous
`1189:8890` "ch57x" pads) — assign keys, shortcuts, media controls, and **app launchers**
to each button/knob by clicking, then flash it straight to the pad.

No Windows-only vendor software required. Built as a friendly front-end over
[`kriomant/ch57x-keyboard-tool`](https://github.com/kriomant/ch57x-keyboard-tool).

> **한국어 요약**: 윈도우 전용 프로그램 없이, 리눅스에서 6키+노브 매크로패드(1189:8890)를
> 클릭으로 설정하고 패드에 바로 굽는 GUI. 버튼/노브에 키·단축키·미디어·앱실행을 지정할 수 있고,
> '앱 실행'은 F키↔키심↔GNOME 단축키 연결을 앱이 자동 처리한다.

![status](https://img.shields.io/badge/platform-Linux%20(X11%2FGNOME)-informational)

---

## Why this exists

These pads **store the key mapping in the pad's own firmware**. Out of the box, *every*
key often sends the **same** keycode, so you cannot tell the buttons apart in software —
you must **write** a mapping into the device. The official configurator is Windows-only.

`ch57x-keyboard-tool` can flash the pad from Linux via a YAML file. This project wraps it
in a GUI and, crucially, **automates the annoying parts**:

- **App launchers.** A macro pad can only send keystrokes, not "run a program". So to
  launch an app we assign a phantom function key (**F14–F18**, which no real keyboard has),
  then register a GNOME custom shortcut for it. But there's a catch (see below) — the app
  handles it all: you just type `code` or `firefox`.
- **The F13/keysym gotcha.** On many distros the X11 keymap turns HID `F13…F24` into
  `XF86Tools` / `XF86Launch5…9` keysyms rather than `F13…F24`. Binding a GNOME shortcut to
  `F13` silently fails, and `F13` (=`XF86Tools`) even opens *Settings*. The app detects the
  **actual** keysym for each F-key at runtime (via `xmodmap`) and binds to that.

---

## Features

- 3×2 buttons + knob (CCW / press / CW), edited visually.
- Per-slot action: **Key / shortcut**, **Media / volume**, or **Launch app**.
- One click to **validate + flash the pad + sync GNOME shortcuts**.
- **LED backlight mode picker** — step through modes, keep the one you like, auto-restore it on login.
- No `sudo` needed after a one-time udev rule.
- Config is a plain JSON source-of-truth; generated YAML is compatible with `ch57x-keyboard-tool`.

## Supported devices

Same as ch57x-keyboard-tool: USB IDs `1189:8890`, `1189:8840`, `1189:8842`.
This GUI is tuned for the **3×2 keys + 1 knob** variant. (Other layouts: tweak `rows/columns/knobs`.)

## Requirements

- Linux with **X11** and **GNOME** (uses `gsettings` + `xmodmap`).
- Python 3 + **PyQt5**  ·  `curl`  ·  member of the `plugdev` group.

```bash
sudo apt install python3-pyqt5 curl
```

## Install

```bash
git clone https://github.com/iamracco0n/macropad-ch57x-ubuntu-gui.git
cd macropad-ch57x-ubuntu-gui

./install.sh              # downloads the ch57x-keyboard-tool binary next to padconf.py
sudo ./setup-udev.sh      # one-time: lets you flash the pad without sudo
# then unplug & replug the pad
```

## Usage

```bash
python3 padconf.py
```

1. Click a button (or a knob direction) on the left.
2. Pick an action type and value on the right:
   - **Key / shortcut** — `1`, `escape`, `f5`, `ctrl-c`, `alt-tab`, `left`, …
   - **Media / volume** — volume up/down, mute, play, …
   - **Launch app** — `code`, `firefox`, or any command (F14–F18 + GNOME shortcut auto-managed).
3. **💾 Save & apply to pad** — flashes the pad and syncs shortcuts.

### LED backlight

The pad's backlight lives in the **LED backlight** box (bottom-left).

```bash
python3 padconf.py --led 3           # apply mode 3 and remember it
python3 padconf.py --restore-led     # re-apply the saved mode (retries while the pad enumerates)
python3 padconf.py --led-autostart on|off
```

- **◀ / ▶** — jump to the previous/next mode and apply it immediately.
- **🔄 Auto-cycle** — advances every 2 s; press again to stop on the one you like.
- **Save this mode** — stores it in `padconf.json` and re-applies it on every *Save & apply*.
- **Restore on login** — installs a `systemd --user` unit (`macropad-led.service`).

> **What the hardware allows:** on `1189:8890` the underlying tool exposes a single
> *mode index* — there is no color, brightness or per-key control (those exist only for
> `8840`/`8842`). It also writes the mode byte with no bounds check, so *every* value
> looks like a success. **This pad has only 3 LED modes**, so the picker is limited to
> `0–3` with `0` = off.
>
> Sources for the mode count: [`rOzzy1987/MacroPad`](https://github.com/rOzzy1987/MacroPad)
> lists this exact device in `layouts.txt` as `4489:34960` → `1:5:0:0:3`
> (*layers : sequence length : delay : color support : **LED modes***), and its README notes
> the pad "doesn't support colors, and only has 3 modes, on being the Off state".

### Example: Claude Code / prompt answering

A handy setup is mapping the top row to answer numbered CLI prompts:

| Button | Sends | Use |
|-------:|:------|:----|
| top-left   | `1` | Yes (always the first option) |
| top-middle | `2` | "Yes, and don't ask again" (only on 3-option prompts) |
| top-right  | `escape` | **No / reject** — works whether there are 2 or 3 options |

> Prefer **Esc** for "No": prompts sometimes show only 2 options, where "No" is `2`, not `3`.
> Esc rejects regardless of the option count.

## Troubleshooting

- **A button opens *Settings* / does nothing** → the F13/keysym gotcha above. Re-run
  *Save & apply* (the app binds to the real keysym). `F13`=`XF86Tools`=Settings is avoided.
- **See what a key actually sends** → `python3 tools/diagnose.py` (raw evdev event viewer).
- **All keys report the same code** → normal for an unprogrammed pad; flash it, then they differ.
- **`Access denied` when flashing** → run `sudo ./setup-udev.sh`, replug, confirm you're in `plugdev`.
- **Prebuilt binary won't run (`GLIBC_2.38 not found`)** → `install.sh` auto-falls back to an
  older release (v1.5.0) that runs on older glibc (e.g. Ubuntu 22.04).
- **LED mode does nothing / looks identical** → not every index is a real mode on this
  hardware, and the tool reports success either way. Try the neighbouring indices.
- **Pad vanished entirely (`device not found`)** → check the *hub* first: `lsusb`, then
  `cat /sys/bus/usb/devices/usb1/1-0:1.0/usb1-port*/state`. If a hub drops out, every device
  behind it disappears at once and no amount of re-flashing helps.

## Credits & license

- Flashing is done by [`kriomant/ch57x-keyboard-tool`](https://github.com/kriomant/ch57x-keyboard-tool)
  (GPL-3.0) — **not bundled**; fetched by `install.sh`.
- This wrapper (GUI + scripts): **MIT**, see [LICENSE](LICENSE).
