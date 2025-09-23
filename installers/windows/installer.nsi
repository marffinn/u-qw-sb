!define APP_NAME "BROWSANKA"
!define APP_VERSION "1.0.0"
!define APP_PUBLISHER "marffinn"
!define APP_URL "https://github.com/marffinn/u-qw-sb"
!define APP_EXE_NAME "BROWSANKA.exe"
!define APP_ICON "uttanka.ico"
!define BUILD_ROOT "..\..\executable_dist"

OutFile "${APP_NAME}-Setup-${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES\${APP_NAME}"
RequestExecutionLevel admin

Page directory
Page instfiles

UninstallText "This will uninstall ${APP_NAME}. Do you wish to continue?"
UninstallIcon "${BUILD_ROOT}\${APP_ICON}"
Section "Uninstall"
  Delete "$INSTDIR\${APP_EXE_NAME}"
  Delete "$INSTDIR\favorites.json"
  Delete "$INSTDIR\eu-sv.txt"
  Delete "$INSTDIR\servers_cache.json"
  Delete "$INSTDIR\settings.json"
  Delete "$INSTDIR\${APP_ICON}"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  RMDir "$INSTDIR"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
SectionEnd

Section "${APP_NAME} Main Application"
  SetOutPath "$INSTDIR"
  File "${BUILD_ROOT}\${APP_EXE_NAME}"
  File "${BUILD_ROOT}\favorites.json"
  File "..\..\eu-sv.txt"
  File "${BUILD_ROOT}\servers_cache.json"
  File "${BUILD_ROOT}\settings.json"
  File "${BUILD_ROOT}\${APP_ICON}"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE_NAME}" "" "$INSTDIR\${APP_ICON}"

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "URLInfoAbout" "${APP_URL}"
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd
