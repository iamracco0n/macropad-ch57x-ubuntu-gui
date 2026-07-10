#!/usr/bin/env bash
# ch57x-keyboard-tool 바이너리를 이 폴더에 내려받는다.
# (이 저장소는 서드파티 바이너리를 포함하지 않으므로, 최초 1회 실행 필요.)
#
# 시스템 glibc 가 낮으면(예: Ubuntu 22.04 = 2.35) 최신 릴리스가 GLIBC_2.38 을
# 요구해 실행되지 않는다. 그래서 여러 버전을 순서대로 시도해 '실행되는' 것을 고른다.
set -e
cd "$(dirname "$0")"

REPO="kriomant/ch57x-keyboard-tool"
case "$(uname -m)" in
  x86_64)  ARCH="x86_64-unknown-linux-gnu" ;;
  aarch64) ARCH="aarch64-unknown-linux-gnu" ;;
  *) echo "지원하지 않는 아키텍처: $(uname -m)"; exit 1 ;;
esac

# 최신 → 구버전 순. 낮은 glibc 시스템은 v1.5.0 로 폴백된다.
VERSIONS=("v1.7.0" "v1.6.2" "v1.5.4" "v1.5.0")
OUT="ch57x-keyboard-tool"

for v in "${VERSIONS[@]}"; do
  url="https://github.com/$REPO/releases/download/$v/ch57x-keyboard-tool-$ARCH.tar.gz"
  echo "==> 시도: $v"
  if curl -fsSL --max-time 60 -o /tmp/ch57x.tgz "$url" 2>/dev/null; then
    tar xzf /tmp/ch57x.tgz -C /tmp ch57x-keyboard-tool 2>/dev/null || tar xzf /tmp/ch57x.tgz -C /tmp
    if /tmp/ch57x-keyboard-tool --help >/dev/null 2>&1; then
      cp /tmp/ch57x-keyboard-tool "./$OUT"; chmod +x "./$OUT"
      echo "설치 완료: $(pwd)/$OUT  (버전 $v)"
      rm -f /tmp/ch57x.tgz /tmp/ch57x-keyboard-tool
      exit 0
    else
      echo "   $v 는 이 시스템에서 실행 불가(glibc 등). 다음 버전 시도."
    fi
  fi
done
echo "설치 실패: 실행 가능한 릴리스를 찾지 못했습니다. 소스 빌드가 필요할 수 있습니다."
exit 1
