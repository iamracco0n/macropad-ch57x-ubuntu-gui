#!/usr/bin/env bash
# 매크로패드 USB 장치를 plugdev 그룹이 rw 하도록 udev 규칙 설치.
# 한 번만 sudo 로 실행하면, 이후 sudo 없이 패드에 업로드 가능.
set -e
cd "$(dirname "$0")"
DEST=/etc/udev/rules.d/50-ch57x-macrokeyboard.rules
sudo cp udev/50-ch57x-macrokeyboard.rules "$DEST"
sudo udevadm control --reload-rules
sudo udevadm trigger --attr-match=idVendor=1189 --attr-match=idProduct=8890 || sudo udevadm trigger
echo "완료. 패드 USB 를 뽑았다 다시 꽂으면 적용됩니다."
echo "현재 사용자가 plugdev 그룹인지 확인:  id -nG | tr ' ' '\\n' | grep -x plugdev"
