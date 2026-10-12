@echo off
rem Windows 용 데스크톱 프로그램 빌드 (Python 3.10+ 설치 필요, https://www.python.org/downloads/ 에서 "Add python.exe to PATH" 체크)
rem 결과: release\RC내력계산기.exe  (WebView2 런타임은 Windows 10/11 에 Edge 와 함께 기본 설치되어 있음)
cd /d "%~dp0"
python -m pip install --quiet pywebview pyinstaller pillow
python build_dist.py
python -m PyInstaller --noconfirm --windowed --onefile --name "RC내력계산기" --distpath release --workpath build --specpath build --add-data "%~dp0dist;dist" app.py
echo.
echo 완료: release\RC내력계산기.exe
pause
