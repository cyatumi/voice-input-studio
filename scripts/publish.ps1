# =============================================================================
#  Voice Input Studio — ワンコマンド発行スクリプト
# -----------------------------------------------------------------------------
#  使い方:
#     scripts\publish.ps1 -Version 1.5.2 -Notes "バグ修正と高速化"
#     scripts\publish.ps1 -Version 1.5.2 -Notes "..." -Watch   # ビルド進捗も表示
#
#  やること（これだけで配信完了）:
#     1. バージョン番号を検査（X.Y.Z 形式 / タグ重複チェック）
#     2. voice_input\__init__.py の __version__ を書き換え
#     3. 変更を全部コミット（コミットメッセージ = リリースノートになる）
#     4. 注釈付きタグ vX.Y.Z を作成
#     5. main とタグを push  →  GitHub Actions が自動ビルド＆Release公開
#
#  push後 約8分でReleaseが公開され、配布済みアプリが自動更新します。
# =============================================================================
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$Notes = "",
    [switch]$Watch          # 指定するとビルド完了まで進捗を表示
)
$ErrorActionPreference = "Stop"

# --- 0. 準備 -----------------------------------------------------------------
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# gh CLI（PATHに無くてもフルパスで拾う）
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    $cand = "C:\Program Files\GitHub CLI\gh.exe"
    if (Test-Path $cand) { $gh = $cand }
}

function Fail($msg) { Write-Host "✗ $msg" -ForegroundColor Red; exit 1 }

# --- 1. バージョン検査 -------------------------------------------------------
$Version = $Version.TrimStart('v', 'V')
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Fail "バージョンは X.Y.Z 形式で指定してください（例: 1.5.2）。指定値: '$Version'"
}
$Tag = "v$Version"

# Gitリポジトリか
if (-not (Test-Path (Join-Path $Root ".git"))) { Fail "ここはGitリポジトリではありません: $Root" }

# origin があるか
$origin = git remote get-url origin 2>$null
if (-not $origin) { Fail "リモート 'origin' が設定されていません。" }

# タグ重複（ローカル）
$localTag = git tag --list $Tag
if ($localTag) { Fail "タグ $Tag は既に存在します。別の番号にしてください。" }

# タグ重複（リモート）
$remoteTag = git ls-remote --tags origin $Tag 2>$null
if ($remoteTag) { Fail "タグ $Tag はリモートに既に存在します。別の番号にしてください。" }

Write-Host "==== Voice Input Studio を $Tag として発行します ====" -ForegroundColor Cyan
Write-Host " リポジトリ: $origin"
Write-Host ""

# --- 2. バージョン書き換え ---------------------------------------------------
Write-Host "[1/4] __init__.py を v$Version に更新..." -ForegroundColor Cyan
$initFile = "voice_input\__init__.py"
(Get-Content $initFile -Raw) `
    -replace '__version__\s*=\s*"[^"]*"', "__version__ = `"$Version`"" |
    Set-Content $initFile -Encoding utf8 -NoNewline

# installer.iss にもバージョンがあれば合わせる（あれば）
$issFile = "scripts\installer.iss"
if (Test-Path $issFile) {
    (Get-Content $issFile -Raw) `
        -replace '#define MyAppVersion "[^"]*"', "#define MyAppVersion `"$Version`"" |
        Set-Content $issFile -Encoding utf8
}

# --- 3. コミット -------------------------------------------------------------
Write-Host "[2/4] 変更をコミット..." -ForegroundColor Cyan
git add -A

# コミットメッセージ = Release のノートになる（workflowが head_commit.message を使用）
$commitMsg = if ($Notes) { "release: $Tag`n`n$Notes" } else { "release: $Tag" }

# ステージに差分があるときだけコミット（無ければ現在のHEADにタグを打つ）
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m $commitMsg | Out-Null
    Write-Host "      コミット作成: $Tag" -ForegroundColor DarkGray
} else {
    Write-Host "      変更なし → 現在のコミットにタグを打ちます" -ForegroundColor DarkGray
}

# --- 4. タグ作成 & push ------------------------------------------------------
Write-Host "[3/4] タグ $Tag を作成..." -ForegroundColor Cyan
$tagMsg = if ($Notes) { "$Tag - $Notes" } else { $Tag }
git tag -a $Tag -m $tagMsg

Write-Host "[4/4] push（main + タグ）..." -ForegroundColor Cyan
git push origin HEAD
git push origin $Tag

# --- 完了 --------------------------------------------------------------------
# origin URL から owner/repo を取り出して各種URLを組み立てる
$slug = ($origin -replace '\.git$','') -replace '^https://github.com/',''
$actionsUrl  = "https://github.com/$slug/actions"
$releasesUrl = "https://github.com/$slug/releases"

Write-Host ""
Write-Host "==================== push 完了 ====================" -ForegroundColor Green
Write-Host " GitHub Actions が自動ビルドを開始しました（約8分）。"
Write-Host " 進捗   : $actionsUrl"
Write-Host " 公開先 : $releasesUrl/tag/$Tag"
Write-Host "==================================================="

# --- 任意: 完了まで見守る ----------------------------------------------------
if ($Watch) {
    if (-not $gh) {
        Write-Host "（gh CLI が見つからないため -Watch はスキップ。上のURLで確認してください）" -ForegroundColor Yellow
        return
    }
    Write-Host ""
    Write-Host "ビルドの開始を待っています..." -ForegroundColor Cyan
    Start-Sleep -Seconds 8
    $runId = & $gh run list --workflow "Build and Release" --limit 1 --json databaseId --jq ".[0].databaseId" 2>$null
    if ($runId) {
        & $gh run watch $runId --exit-status
        if ($LASTEXITCODE -eq 0) {
            Write-Host ""
            Write-Host "✓ ビルド成功！ Release を公開しました: $releasesUrl/tag/$Tag" -ForegroundColor Green
        } else {
            Write-Host ""
            Write-Host "✗ ビルドが失敗しました。ログを確認してください: $actionsUrl" -ForegroundColor Red
        }
    } else {
        Write-Host "実行IDを取得できませんでした。$actionsUrl で確認してください。" -ForegroundColor Yellow
    }
}
