# Compile et lance les tests de non-régression C++ (MSVC). Régénérer les références d'abord : python _proto\export_refs.py
#   powershell -NoProfile -ExecutionPolicy Bypass -File PRISME\tests\build.ps1
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $vcvars = 'C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat'
    $cmd = "`"$vcvars`" >nul 2>&1 && cl /nologo /std:c++17 /O2 /EHsc /W3 /permissive- /D_USE_MATH_DEFINES test_refs.cpp /Fe:test_refs.exe"
    cmd /c $cmd
    if ($LASTEXITCODE -ne 0) { throw "compilation échouée" }
    & .\test_refs.exe refs
    exit $LASTEXITCODE
}
finally { Pop-Location }
