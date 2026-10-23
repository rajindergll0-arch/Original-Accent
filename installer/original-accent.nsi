; Original Accent Windows installer (NSIS 3). Build: makensis installer/original-accent.nsi
; Per-user install, no admin rights. The app and its own Python go in %LOCALAPPDATA%\Original Accent;
; the voice engines are chosen here and downloaded by the app on first launch, with progress.
Unicode true
Target amd64-unicode   ; 64-bit installer: the app needs 64-bit Windows anyway
!define APP "Original Accent"
!ifndef VERSION
  !define VERSION "0.3.0"
!endif
!define ROOT "$LOCALAPPDATA\OriginalAccent"
!define UNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\OriginalAccent"
!define OLDROOT "$LOCALAPPDATA\Voicecast"
!define OLDUNINST "Software\Microsoft\Windows\CurrentVersion\Uninstall\Voicecast"

Name "${APP}"
OutFile "..\dist\OriginalAccent-Setup-${VERSION}.exe"
InstallDir "${ROOT}\app"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "Original Accent ${VERSION} · runs entirely on this PC"
SpaceTexts none   ; engine downloads happen later, so a size here would mislead
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "Original Accent"
VIAddVersionKey "FileDescription" "Original Accent setup"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Rajinder Gill, MIT licence"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "Sections.nsh"

!define MUI_ICON "..\ui\icon.ico"
!define MUI_UNICON "..\ui\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "welcome.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "header.bmp"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Install Original Accent"
!define MUI_WELCOMEPAGE_TEXT "Original Accent clones a voice from a short recording and speaks your script in it, keeping the speaker's accent.$\r$\n$\r$\nEverything runs on this PC with open-source engines. Nothing is sent to a cloud service.$\r$\n$\r$\nYou need an NVIDIA graphics card and an internet connection for setup. The voice engines you choose on the next pages are downloaded when Original Accent first opens (several GB each); after that it works offline."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!define MUI_COMPONENTSPAGE_TEXT_TOP "Choose the voice engines. Point at one to see what it does. Greyed items are required. Engines download when Original Accent first opens (several GB each); change them later in Settings."
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "Original Accent is installed"
!define MUI_FINISHPAGE_TEXT "When Original Accent opens it will download the engines you chose and show their progress. You can keep using the PC meanwhile.$\r$\n$\r$\nOnly clone voices you have permission to use."
!define MUI_FINISHPAGE_RUN "$LOCALAPPDATA\OriginalAccent\app-env\Scripts\pythonw.exe"
!define MUI_FINISHPAGE_RUN_PARAMETERS "-m original_accent"
!define MUI_FINISHPAGE_RUN_TEXT "Open Original Accent now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ------------------------------------------------------------------ migration
; The app was called Voicecast before release. Move its voices, jobs, downloaded engines and
; settings into the new folder (same drive, so this is instant), then remove the old copy.
Function MigrateFromVoicecast
  IfFileExists "${OLDROOT}\*.*" 0 done
    DetailPrint "Moving your voices, jobs and engines from the earlier Voicecast install..."
    CreateDirectory "${ROOT}"
    !macro MOVE_IF NAME
      IfFileExists "${ROOT}\${NAME}" +3 0
      IfFileExists "${OLDROOT}\${NAME}" 0 +2
      Rename "${OLDROOT}\${NAME}" "${ROOT}\${NAME}"
    !macroend
    !insertmacro MOVE_IF "engines"
    !insertmacro MOVE_IF "voices"
    !insertmacro MOVE_IF "jobs"
    !insertmacro MOVE_IF "logs"
    !insertmacro MOVE_IF "settings.json"
    RMDir /r "${OLDROOT}\app"
    RMDir /r "${OLDROOT}\app-env"
    RMDir /r "${OLDROOT}\webview"
    Delete "${OLDROOT}\install-choices.json"
    Delete "$SMPROGRAMS\Voicecast.lnk"
    Delete "$DESKTOP\Voicecast.lnk"
    DeleteRegKey HKCU "${OLDUNINST}"
    RMDir "${OLDROOT}"
  done:
FunctionEnd

; ------------------------------------------------------------------ sections
Section "Original Accent app" SecApp
  SectionIn RO
  ; close anything Original Accent is running (the app, an engine install, uv) so its files aren't locked
  nsExec::Exec `powershell -NoProfile -Command "Get-Process | Where-Object { $$_.Path -like '${ROOT}\*' -or $$_.Path -like '${OLDROOT}\*' } | Stop-Process -Force"`
  Sleep 1500
  Call MigrateFromVoicecast
  SetOutPath "$INSTDIR"
  File /r /x __pycache__ "..\original_accent"
  File /r /x __pycache__ "..\workers"
  File /r "..\ui"
  File "..\requirements.txt"
  File "..\README.md"
  File "..\LICENSE"
  File "..\THIRD_PARTY_NOTICES.md"
  SetOutPath "$INSTDIR\licenses"
  File /r "..\licenses\*.*"
  SetOutPath "$INSTDIR\docs"
  File /r "..\docs\*.*"
  SetOutPath "$INSTDIR\bin"
  SetOverwrite try       ; uv.exe in use: keep the existing copy rather than stop the install
  File "bin\uv.exe"
  SetOverwrite on

  DetailPrint "Setting up Original Accent's own Python (downloads Python 3.12 the first time)..."
  nsExec::ExecToLog '"$INSTDIR\bin\uv.exe" venv "${ROOT}\app-env" -p 3.12 --allow-existing'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Original Accent couldn't create its Python environment (code $0).$\r$\nCheck the internet connection and run setup again. Details are in the list above."
    Abort
  ${EndIf}
  DetailPrint "Installing the app's packages..."
  nsExec::ExecToLog '"$INSTDIR\bin\uv.exe" pip install -p "${ROOT}\app-env\Scripts\python.exe" -r "$INSTDIR\requirements.txt"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Original Accent couldn't install its packages (code $0).$\r$\nCheck the internet connection and run setup again."
    Abort
  ${EndIf}

  SetOutPath "$INSTDIR"   ; CreateShortCut uses this as the shortcut's working directory
  CreateShortCut "$SMPROGRAMS\Original Accent.lnk" "${ROOT}\app-env\Scripts\pythonw.exe" "-m original_accent" "$INSTDIR\ui\icon.ico" 0 SW_SHOWNORMAL "" "Local voice cloning"
  CreateShortCut "$DESKTOP\Original Accent.lnk" "${ROOT}\app-env\Scripts\pythonw.exe" "-m original_accent" "$INSTDIR\ui\icon.ico" 0 SW_SHOWNORMAL "" "Local voice cloning"

  WriteUninstaller "$INSTDIR\Uninstall Original Accent.exe"
  WriteRegStr HKCU "${UNINST}" "DisplayName" "Original Accent"
  WriteRegStr HKCU "${UNINST}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST}" "Publisher" "Rajinder Gill"
  WriteRegStr HKCU "${UNINST}" "DisplayIcon" "$INSTDIR\ui\icon.ico"
  WriteRegStr HKCU "${UNINST}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST}" "UninstallString" '"$INSTDIR\Uninstall Original Accent.exe"'
  WriteRegDWORD HKCU "${UNINST}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST}" "NoRepair" 1
SectionEnd

SectionGroup /e "Voice engines" SecEngines
  Section "Qwen3-TTS" SecQwen
    SectionIn RO
  SectionEnd
  Section "Whisper" SecScore
  SectionEnd
  Section "Chatterbox" SecCbx
  SectionEnd
SectionGroupEnd

Section "-choices"
  ; tell the app which engines to install on first launch
  StrCpy $1 '"qwen"'
  ${If} ${SectionIsSelected} ${SecScore}
    StrCpy $1 '$1, "score"'
  ${EndIf}
  ${If} ${SectionIsSelected} ${SecCbx}
    StrCpy $1 '$1, "cbx"'
  ${EndIf}
  CreateDirectory "${ROOT}"
  FileOpen $2 "${ROOT}\install-choices.json" w
  FileWrite $2 '{"engines": [$1]}'
  FileClose $2
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} "The Original Accent app and its own private Python. Always installed."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecEngines} "Open-source engines that run on your NVIDIA GPU. Nothing goes to the cloud."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecQwen} "Required. The voice engine: clones a voice from a short clip and its transcript, keeping the accent."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecScore} "Recommended. Drafts the clip's transcript and scores each take's words and voice match. Without it, you type transcripts."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCbx} "Optional. A second voice engine for more variety. It can soften an accent, so you can choose whether it is used for each run."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ------------------------------------------------------------------ uninstall
Section "Uninstall"
  ; close anything Original Accent is running (the app, an engine install, uv) so its files aren't locked
  nsExec::Exec `powershell -NoProfile -Command "Get-Process | Where-Object { $$_.Path -like '${ROOT}\*' } | Stop-Process -Force"`
  Sleep 1500
  Delete "$SMPROGRAMS\Original Accent.lnk"
  Delete "$DESKTOP\Original Accent.lnk"
  RMDir /r "$INSTDIR"
  RMDir /r "${ROOT}\app-env"
  DeleteRegKey HKCU "${UNINST}"
  MessageBox MB_YESNO|MB_ICONQUESTION "Also delete your voices, jobs and the downloaded voice engines?$\r$\n$\r$\nChoose No to keep them for a future install." IDNO keep
    RMDir /r "${ROOT}"
  keep:
SectionEnd
