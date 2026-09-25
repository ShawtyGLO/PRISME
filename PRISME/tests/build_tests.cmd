@echo off
rem Compile et lance les tests de non-régression C++ (MSVC). Régénérer les références d'abord : python _proto\export_refs.py
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
pushd "%~dp0"
cl /nologo /std:c++17 /O2 /EHsc /W4 /permissive- /D_USE_MATH_DEFINES test_refs.cpp /Fe:test_refs.exe || exit /b 1
test_refs.exe refs
