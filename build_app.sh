#!/bin/sh
# macOS 용 데스크톱 프로그램 빌드 → release/RC내력계산기.app
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --quiet pywebview pyinstaller pillow
.venv/bin/python build_dist.py
.venv/bin/pyinstaller --noconfirm --windowed --name "RC내력계산기" --distpath release --workpath build --specpath build --add-data "$(pwd)/dist:dist" app.py
echo "완료: release/RC내력계산기.app"
