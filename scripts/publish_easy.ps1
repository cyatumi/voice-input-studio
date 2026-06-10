# =============================================================================
#  Voice Input Studio ― 人に配る（新バージョンを公開）やさしい版
#  「★ 人に配る（新バージョンを公開）.bat」から呼び出される。
#  むずかしい操作なし。番号は自動で提案、変更点を一言入れてEnterするだけ。
# =============================================================================
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { [Console]::InputEncoding  = [System.Text.Encoding]::UTF8 } catch {}

$HandoutUrl = "https://github.com/cyatumi/voice-input-studio/releases/latest"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  Voice Input Studio を 人に配る（新しい版を公開）"   -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " 相手に渡すリンクは、いつもコレ1本だけ：" -ForegroundColor Yellow
Write-Host "   $HandoutUrl" -ForegroundColor Yellow
Write-Host " （この操作をすると、約8分後にこのリンクが新しい版になります）"
Write-Host ""

# --- 次のバージョン番号を自動計算（最新タグ +1）------------------------------
$tags = @(git tag 2>$null | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' })
if ($tags.Count -gt 0) {
    $latest = $tags | ForEach-Object { [version]($_.Substring(1)) } |
              Sort-Object -Descending | Select-Object -First 1
    $next = "{0}.{1}.{2}" -f $latest.Major, $latest.Minor, ($latest.Build + 1)
} else {
    $next = "1.0.0"
}

Write-Host "次に公開する番号は  v$next  にします。" -ForegroundColor Green
Write-Host "（このままでよければ何も入力せず Enter。番号を変えたいときだけ入力）"
$ans = Read-Host "バージョン番号"
if ($ans) { $next = $ans.TrimStart('v','V') }

Write-Host ""
$notes = Read-Host "今回の変更を一言で（例: 誤字を直した / 録音を速くした）"
if (-not $notes) { $notes = "細かな改善" }

Write-Host ""
Write-Host "----------------------------------------"
Write-Host "  公開する版 : v$next"
Write-Host "  変更の説明 : $notes"
Write-Host "----------------------------------------"
$ok = Read-Host "これで公開します。よければ y を入力して Enter（やめるなら何も入力せず Enter）"
if ($ok -ne 'y' -and $ok -ne 'Y') {
    Write-Host ""
    Write-Host "中止しました。何も公開していません。" -ForegroundColor Yellow
    return
}

Write-Host ""
Write-Host "公開を始めます…（ビルドに約8分。終わるまでこのまま待ってください）" -ForegroundColor Cyan
Write-Host ""

# 既存の発行スクリプトを呼ぶ（コミット→タグ→push→GitHubが自動ビルド＆公開）
& (Join-Path $PSScriptRoot "publish.ps1") -Version $next -Notes $notes -Watch

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  公開できました！ 相手にはこのリンクを送るだけ："      -ForegroundColor Green
Write-Host "   $HandoutUrl" -ForegroundColor Yellow
Write-Host "  すでに渡した人は、次にアプリを開くと自動更新されます。" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
