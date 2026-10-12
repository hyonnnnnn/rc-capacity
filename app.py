"""데스크톱 프로그램: dist/index.html 을 시스템 웹뷰 창에 띄움 (macOS .app / Windows .exe 로 묶는 용도)

실행:  .venv/bin/python app.py            (개발 중 바로 띄우기)
빌드:  README 의 "컴퓨터 프로그램" 절 참고 (PyInstaller)
저장 버튼(엑셀·JSON·보고서·PNG)은 페이지에서 window.pywebview.api.save_file 을 불러 OS 저장 대화상자로 저장한다.
"""
import base64
import pathlib
import sys

import webview

HERE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))   # PyInstaller 묶음 안이면 임시 폴더
INDEX = HERE / "dist" / "index.html"


class Api:
    def save_file(self, filename, b64):
        win = webview.windows[0]
        path = win.create_file_dialog(webview.SAVE_DIALOG, save_filename=filename)
        if not path:
            return False
        if not isinstance(path, str):
            path = path[0]
        pathlib.Path(path).write_bytes(base64.b64decode(b64))
        return True


if __name__ == "__main__":
    if not INDEX.exists():
        sys.exit(f"dist/index.html 이 없어요. 먼저 python3 build_dist.py 를 실행하세요 ({INDEX})")
    webview.create_window("RC 단면 내력 계산기 · 3D FEM", INDEX.as_uri(), js_api=Api(), width=1240, height=860, min_size=(800, 600))
    webview.start()
