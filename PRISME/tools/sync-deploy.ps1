# =============================================================================
#  sync-deploy.ps1 - Compile PRISME et deploie le VST3 systeme.
#  Meme logique que TOTUMstrip.
#
#  Etapes :
#    1. refuse de tourner si le DAW est ouvert (Windows verrouille le VST3
#       charge, la copie echouerait a moitie)
#    2. Projucer --resave (le .jucer est la source de verite du projet)
#    3. msbuild Release x64
#    3b. pluginval - refuse de deployer si la validation echoue
#    4. deploie vers Common Files\VST3
#
#  ATTENTION : ecrire dans Program Files demande une elevation -> lancer en admin.
#
#  Usage :  powershell -ExecutionPolicy Bypass -File tools\sync-deploy.ps1
# =============================================================================
#  Parametre : severite de pluginval, de 1 a 10. 5 pour une passe de routine,
#  10 avant de partager une version.
param([int]$PluginvalLevel = 5, [switch]$NoDeploy)   # -NoDeploy : compile + valide, ne copie rien (pas besoin d'admin ni de fermer le DAW)

$ErrorActionPreference = 'Stop'
$tools  = $PSScriptRoot
$root   = Split-Path $tools -Parent
$jucer  = Join-Path $root 'PRISME.jucer'
$builds = Join-Path $root 'Builds\VisualStudio2022'
$sln    = Join-Path $builds 'PRISME.sln'
$src    = Join-Path $builds 'x64\Release\VST3\PRISME.vst3'
$dst    = 'C:\Program Files\Common Files\VST3\PRISME.vst3'

function Info ($m) { Write-Host "  $m" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "PRISME - compilation et deploiement" -ForegroundColor Cyan
Write-Host "---------------------------------------" -ForegroundColor Cyan

# 1. le DAW verrouille le VST3 charge
foreach ($p in $(if ($NoDeploy) { @() } else { @('FL64','FL','Ableton Live','reaper','Cubase') })) {
    if (Get-Process -Name $p -ErrorAction SilentlyContinue) {
        Write-Host ""
        Write-Host "  $p est ouvert. Windows verrouille le VST3 tant qu'il est charge." -ForegroundColor Red
        Write-Host "  Fermer le DAW puis relancer." -ForegroundColor Red
        exit 1
    }
}

# 2. le .jucer est la source de verite du projet
$projucer = 'C:\Users\llg53\Desktop\JUCE\Projucer.exe'
if (Test-Path $projucer) {
    Info "Projucer --resave ..."
    & $projucer --resave $jucer --fix-missing-dependencies | Out-Null
}

# 3. compilation
$vcvars = Get-ChildItem 'C:\Program Files\Microsoft Visual Studio' -Recurse -Filter vcvars64.bat -ErrorAction SilentlyContinue |
          Select-Object -First 1
if (-not $vcvars) { throw "vcvars64.bat introuvable - Visual Studio requis." }

$bat = Join-Path $env:TEMP 'prisme_build.bat'
@"
@echo off
call "$($vcvars.FullName)" >nul
msbuild "$sln" /p:Configuration=Release /p:Platform=x64 /m /v:minimal /nologo
"@ | Out-File $bat -Encoding ascii

Info "msbuild Release x64 ..."
& cmd /c $bat
if ($LASTEXITCODE -ne 0) { throw "Compilation echouee." }

# 3b. validation AVANT deploiement.
#
#     pluginval charge le VST3 comme le ferait un hote et lui fait passer de
#     l'audio a 44,1 / 48 / 96 kHz en buffers de 64 a 1024, avec de l'automation
#     en cours ; il ouvre et ferme l'editeur en boucle, sauvegarde et recharge
#     l'etat, et bouscule les parametres depuis d'autres threads.
#
#     ATTENTION : il n'a pas d'oreilles. Il attrape les fautes de CONSTRUCTION
#     (plantage, fuite, NaN, latence mal declaree), jamais les fautes de SON.
#     Un craquement ou un de-esser qui ajoute de l'aigu passent au vert ici.
#
#     Il a deja paye sa place : il a trouve une violation d'acces a la fermeture
#     de l'editeur que deux ouvertures du standalone n'avaient pas revelee.
if (-not (Test-Path $src)) { throw "VST3 introuvable : $src" }

# tous les outils du projet vivent sous la MEME racine, a cote du plugin :
# le dossier se deplace d'un bloc sans rien casser
$pluginval = Join-Path (Split-Path $root -Parent) '_outils\pluginval\pluginval.exe'
if (Test-Path $pluginval) {
    Info "pluginval (severite $PluginvalLevel) ..."
    & $pluginval --strictness-level $PluginvalLevel --timeout-ms 300000 --validate $src |
        Tee-Object -Variable pvOut | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  pluginval a echoue - RIEN N'EST DEPLOYE." -ForegroundColor Red
        $pvOut | Select-Object -Last 30 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        exit 1
    }
    Info "pluginval : SUCCESS"
} else {
    Info "pluginval absent - validation sautee"
}

if ($NoDeploy) { Write-Host ''; Write-Host '  Build + pluginval OK (rien deploye : -NoDeploy).' -ForegroundColor Green; exit 0 }

# 4. deploiement
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
Info "deploiement vers $dst"
Copy-Item $src $dst -Recurse -Force

Write-Host ""
Write-Host "  Deploye." -ForegroundColor Green
Write-Host ""
