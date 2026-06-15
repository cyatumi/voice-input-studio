import sys

__version__ = "1.5.4"
__app_name__ = "VoiceInputStudio"

# ソースから直起動した「マスター（開発版）」か、配布された exe（配布版）かを判別。
# PyInstaller でビルドした exe は sys.frozen が True になる。
IS_FROZEN = getattr(sys, "frozen", False)

# 画面に出す名前。マスターは配布版と見分けられるよう「（マスター）」を付ける。
# 配布版（exe）は素の「Voice Input Studio」のまま。
__display_name__ = "Voice Input Studio" if IS_FROZEN else "Voice Input Studio（マスター）"
