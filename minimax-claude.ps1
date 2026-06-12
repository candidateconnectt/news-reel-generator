# ============================================================
#  MiniMax Token Plan - Claude Code Setup Script for Windows
#  Usage: Right-click > "Run with PowerShell"
#         OR in PowerShell terminal: .\minimax-claude-setup.ps1
# ============================================================

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   MiniMax Token Plan - Claude Code Setup" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Get API Key ──────────────────────────────────────
$apiKey = Read-Host "Enter your MiniMax API Key"

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "[ERROR] API Key cannot be empty. Exiting." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[1/4] API Key received." -ForegroundColor Green

# ── Step 2: Claude Code CLI - ~/.claude/settings.json ───────
Write-Host "[2/4] Configuring Claude Code CLI..." -ForegroundColor Yellow

$claudeDir  = "$env:USERPROFILE\.claude"
$claudeFile = "$claudeDir\settings.json"

if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
    Write-Host "      Created directory: $claudeDir" -ForegroundColor Gray
}

$claudeSettings = @{
    env = @{
        ANTHROPIC_BASE_URL                       = "https://api.minimax.io/anthropic"
        ANTHROPIC_AUTH_TOKEN                     = $apiKey
        API_TIMEOUT_MS                           = "3000000"
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
        ANTHROPIC_MODEL                          = "MiniMax-M2.7"
        ANTHROPIC_DEFAULT_SONNET_MODEL           = "MiniMax-M2.7"
        ANTHROPIC_DEFAULT_OPUS_MODEL             = "MiniMax-M2.7"
        ANTHROPIC_DEFAULT_HAIKU_MODEL            = "MiniMax-M2.7"
    }
}

if (Test-Path $claudeFile) {
    Copy-Item $claudeFile "$claudeFile.backup" -Force
    Write-Host "      Backed up existing settings to: $claudeFile.backup" -ForegroundColor Gray
}

$claudeSettings | ConvertTo-Json -Depth 5 | Set-Content -Path $claudeFile -Encoding UTF8
Write-Host "      Saved: $claudeFile" -ForegroundColor Green

# ── Step 3: VS Code Extension - settings.json ───────────────
Write-Host "[3/4] Configuring VS Code Extension..." -ForegroundColor Yellow

$vscodeFile = "$env:APPDATA\Code\User\settings.json"
$vscodeDir  = "$env:APPDATA\Code\User"

if (-not (Test-Path $vscodeDir)) {
    Write-Host "      VS Code user settings folder not found. Skipping VS Code setup." -ForegroundColor DarkYellow
} else {
    if (Test-Path $vscodeFile) {
        try {
            $raw = Get-Content $vscodeFile -Raw -Encoding UTF8
            $vscodeSettings = $raw | ConvertFrom-Json -AsHashtable
        } catch {
            Write-Host "      Could not parse existing VS Code settings. Creating backup..." -ForegroundColor DarkYellow
            Copy-Item $vscodeFile "$vscodeFile.backup" -Force
            $vscodeSettings = @{}
        }
    } else {
        $vscodeSettings = @{}
    }

    $vscodeSettings["claudeCode.preferredLocation"]  = "panel"
    $vscodeSettings["claudeCode.selectedModel"]      = "minimax-m2.7"
    $vscodeSettings["claudeCode.environmentVariables"] = @(
        @{ name = "ANTHROPIC_BASE_URL";                       value = "https://api.minimax.io/anthropic" },
        @{ name = "ANTHROPIC_AUTH_TOKEN";                     value = $apiKey },
        @{ name = "API_TIMEOUT_MS";                           value = "3000000" },
        @{ name = "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"; value = "1" },
        @{ name = "ANTHROPIC_MODEL";                          value = "MiniMax-M2.7" },
        @{ name = "ANTHROPIC_DEFAULT_SONNET_MODEL";           value = "MiniMax-M2.7" },
        @{ name = "ANTHROPIC_DEFAULT_OPUS_MODEL";             value = "MiniMax-M2.7" },
        @{ name = "ANTHROPIC_DEFAULT_HAIKU_MODEL";            value = "MiniMax-M2.7" }
    )

    $vscodeSettings | ConvertTo-Json -Depth 10 | Set-Content -Path $vscodeFile -Encoding UTF8
    Write-Host "      Saved: $vscodeFile" -ForegroundColor Green
}

# ── Step 4: Verify / Install Claude Code CLI ────────────────
Write-Host "[4/4] Checking Claude Code CLI installation..." -ForegroundColor Yellow

$claudeCmd = Get-Command claude -ErrorAction SilentlyContinue
if ($null -eq $claudeCmd) {
    Write-Host "      [!] Claude Code CLI not found. Installing now via npm..." -ForegroundColor DarkYellow
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npmCmd) {
        Write-Host "      [ERROR] npm not found. Install Node.js first: https://nodejs.org" -ForegroundColor Red
    } else {
        npm install -g @anthropic-ai/claude-code
        Write-Host "      Claude Code CLI installed successfully." -ForegroundColor Green
    }
} else {
    Write-Host "      Claude Code CLI found: $($claudeCmd.Source)" -ForegroundColor Green
}

# ── Done ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "   Setup Complete!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  CLI Config : $claudeFile" -ForegroundColor White
Write-Host "  VS Code    : $vscodeFile" -ForegroundColor White
Write-Host "  Model      : MiniMax-M2.7" -ForegroundColor White
Write-Host "  Endpoint   : https://api.minimax.io/anthropic" -ForegroundColor White
Write-Host ""
Write-Host "  Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Open your project folder in terminal" -ForegroundColor White
Write-Host "  2. Run:  claude" -ForegroundColor Yellow
Write-Host "  3. Select 'Trust This Folder' on first launch" -ForegroundColor White
Write-Host "  4. Type  /status  to verify the base URL" -ForegroundColor White
Write-Host "  5. Type  /model   to verify the active model" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
