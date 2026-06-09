# Voice Input Studio

PC全体で使える音声入力デスクトップアプリ。ホットキーで録音→Whisperで文字起こし→Geminiで整形→今フォーカスがあるアプリに自動貼付。

ブラウザ拡張機能と違い、Word・Slack・メモ帳・IDE・Notion等**あらゆるアプリ**で音声入力が使えます。

## 主な機能

- 🎙 **グローバルホットキー録音** (任意のキー組み合わせ設定可)
- 🤖 **Whisper API** で高精度な日本語認識
- ✨ **Gemini Flash** で擬音語/フィラー除去・句読点・文脈漢字補正
- 💃 **録音中インジケーター** (画面端に踊るキャラクター、音声レベル可視化)
- 📚 **定型文ポップアップ** (「定型文」と発話で一覧表示)
- 🏠 **住所自動入力** (フォームに郵便番号/住所/電話を一括フィル)
- 📖 **個人辞書** (固有名詞の強制変換)
- 💾 **設定永続化** (`%APPDATA%`に保存、更新で消えない)
- 🔄 **既存拡張機能からのデータ移行** (エクスポートJSONを取り込み)
- 🌐 **配布可能** (PyInstallerで.exe化、誰でもインストール)

## 必要なもの

- Windows 10/11
- Python 3.10以降 (開発時のみ。配布版は不要)
- **OpenAI APIキー** (Whisper STT用、$0.006/分)
- **Google Gemini APIキー** (テキスト整形用、無料枠あり)

## インストール (開発者向け)

```powershell
cd voice_input_app
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m voice_input
```

初回起動時にトレイアイコンが出現。右クリックメニューから「設定」を開き、APIキーを入力。

## インストール (一般ユーザー向け)

1. [Releasesページ](#) から `VoiceInputStudio-Setup.exe` をダウンロード
2. ダブルクリックでインストール
3. スタートメニューから起動
4. トレイアイコン右クリック → 設定 → APIキー入力
5. デフォルトホットキー `Ctrl+Shift+Y` を押して音声入力開始

## 使い方

| 操作 | 動作 |
|---|---|
| `Ctrl+Shift+Y` (デフォルト) | 録音開始 / 停止 |
| トレイアイコン右クリック | 設定 / 終了 |
| インジケーター上の停止ボタン | 録音中止 |
| 「定型文」と発話 | 定型文一覧をポップアップ |
| 「住所自動入力」と発話 | 住所選択ポップアップ |

## データ保存場所

| 内容 | 場所 |
|---|---|
| プログラム本体 | `C:\Program Files\VoiceInputStudio\` |
| ユーザー設定 | `%APPDATA%\VoiceInputStudio\settings.json` |
| 定型文・住所・辞書 | `%APPDATA%\VoiceInputStudio\data\*.json` |
| 自動バックアップ | `%APPDATA%\VoiceInputStudio\backups\` (起動時に最新10件保持) |
| 履歴ログ | `%APPDATA%\VoiceInputStudio\logs\` |

**アプリ更新時もユーザーデータは完全に保護されます。**

## 既存Chrome拡張機能からの移行

1. Chrome拡張機能の設定画面で「📥 全データをエクスポート」をクリック
2. 本アプリの設定 → データ管理 → 「Chrome拡張から取り込み」
3. ダウンロードしたJSONを選択

すべての定型文・住所・ボキャブラリー・モードが取り込まれます。

## 配布と自動アップデート (開発者向け)

配布形態は **ZIPを解凍して `VoiceInputStudio.exe` を実行**（インストール不要のポータブル版）。
ホスティングは **Dropbox の直リンク (`?dl=1`)**。

### 仕組み
- アプリは起動5秒後に Dropbox 上の `version.json` を確認し、新しい版があれば
  「更新しますか？」と通知 → OKで新しい `.exe` をDL → 終了・差し替え・再起動。
- トレイメニュー「🔄 更新を確認」で手動チェックも可能。
- 判定は `voice_input/__init__.py` の `__version__` と `version.json` の `version` を比較。

### 初回セットアップ (1回だけ)
1. `release/version.json` を Dropbox にアップロード → 共有リンクを取得し末尾を `?dl=1` に。
2. そのリンクを `voice_input/core/updater.py` の `MANIFEST_URL` に設定。
3. `scripts/release.ps1 -Version 1.5.0` でビルド。
4. `release/VoiceInputStudio.exe` を Dropbox にアップロード → `?dl=1` リンクを取得。
5. そのリンクを `version.json` の `exe_url` と `scripts/release.local.json`
   （`{ "exe_url": "..." }`）に設定し、`version.json` を Dropbox に上書きアップロード。
6. 相手には `release/VoiceInputStudio-v1.5.0.zip` を渡す。

### 2回目以降のリリース
```powershell
scripts\release.ps1 -Version 1.5.1 -Notes "変更点"
```
生成された `VoiceInputStudio.exe` と `version.json` を Dropbox に**上書き**アップロードするだけ。
共有リンクは変わらないので、配布済みのアプリが自動で新版を検知します。

> ⚠️ 注意: 署名なし `.exe` のため、初回起動時に Windows SmartScreen の警告が出ます。
> 「詳細情報」→「実行」で起動できます（相手にもその旨を伝えてください）。

## ライセンス

MIT License (予定)
