# Cloudflare Tunnel Setup Script for Charm Email OS
# Run this script in PowerShell to set up the tunnel

$ErrorActionPreference = "Stop"

Write-Host "=== Cloudflare Tunnel Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check if cloudflared is installed
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Installing cloudflared..." -ForegroundColor Yellow
    winget install cloudflare.cloudflared
    Write-Host "Please restart your terminal and run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "cloudflared version: $(cloudflared --version)" -ForegroundColor Green
Write-Host ""

# Check for existing auth
$certPath = "$env:USERPROFILE\.cloudflared\cert.pem"
if (-not (Test-Path $certPath)) {
    Write-Host "Step 1: Authenticating with Cloudflare..." -ForegroundColor Yellow
    Write-Host "A browser will open - select your domain (laviefatigue.com)" -ForegroundColor Cyan
    cloudflared tunnel login
    Write-Host ""
}
else {
    Write-Host "Step 1: Already authenticated (cert.pem exists)" -ForegroundColor Green
    Write-Host ""
}

# Check for existing tunnel
$tunnelName = "charm-services"
$existingTunnel = cloudflared tunnel list 2>&1 | Select-String $tunnelName

if ($existingTunnel) {
    Write-Host "Step 2: Tunnel '$tunnelName' already exists" -ForegroundColor Green
    $tunnelId = ($existingTunnel -split '\s+')[0]
    Write-Host "  Tunnel ID: $tunnelId" -ForegroundColor Cyan
}
else {
    Write-Host "Step 2: Creating tunnel '$tunnelName'..." -ForegroundColor Yellow
    cloudflared tunnel create $tunnelName
    $tunnelId = (cloudflared tunnel list | Select-String $tunnelName | ForEach-Object { ($_ -split '\s+')[0] })
    Write-Host "  Tunnel ID: $tunnelId" -ForegroundColor Cyan
}
Write-Host ""

# Route DNS
Write-Host "Step 3: Setting up DNS routes..." -ForegroundColor Yellow
$hostname = "slack-hooks.laviefatigue.com"

try {
    cloudflared tunnel route dns $tunnelName $hostname 2>&1 | Out-Null
    Write-Host "  Route created: $hostname -> $tunnelName" -ForegroundColor Green
}
catch {
    Write-Host "  Route may already exist for $hostname (this is OK)" -ForegroundColor Yellow
}
Write-Host ""

# Update config with actual credentials path
$configPath = "$PSScriptRoot\config.yml"
$credsPath = "$env:USERPROFILE\.cloudflared\$tunnelId.json"

if (Test-Path $credsPath) {
    Write-Host "Step 4: Credentials file found at:" -ForegroundColor Green
    Write-Host "  $credsPath" -ForegroundColor Cyan
}
else {
    # Try alternate naming
    $altCredsPath = "$env:USERPROFILE\.cloudflared\charm-services.json"
    if (Test-Path $altCredsPath) {
        $credsPath = $altCredsPath
        Write-Host "Step 4: Credentials file found at:" -ForegroundColor Green
        Write-Host "  $credsPath" -ForegroundColor Cyan
    }
    else {
        Write-Host "Step 4: WARNING - Credentials file not found!" -ForegroundColor Red
        Write-Host "  Expected: $credsPath" -ForegroundColor Yellow
    }
}
Write-Host ""

# Summary
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To start the tunnel:" -ForegroundColor Cyan
Write-Host "  cloudflared tunnel --config $configPath run" -ForegroundColor White
Write-Host ""
Write-Host "Your Slack webhook URL will be:" -ForegroundColor Cyan
Write-Host "  https://$hostname/api/slack/interactions" -ForegroundColor White
Write-Host ""
Write-Host "Configure this URL in your Slack App:" -ForegroundColor Cyan
Write-Host "  1. Go to https://api.slack.com/apps" -ForegroundColor White
Write-Host "  2. Select your app -> Interactivity & Shortcuts" -ForegroundColor White
Write-Host "  3. Enable Interactivity" -ForegroundColor White
Write-Host "  4. Set Request URL to the webhook URL above" -ForegroundColor White
Write-Host ""
