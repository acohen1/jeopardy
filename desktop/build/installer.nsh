; Custom NSIS hooks for the Rhubarb installer.
;
; The sidecar (rhubarb-backend.exe) holding a file lock during an update
; makes NSIS silently skip locked files -> corrupt install -> "spawn UNKNOWN".
; The app's shell sweeps strays before quitting, but the INSTALLER is the
; only code guaranteed to be new-version regardless of how old the initiating
; app is - so it sweeps too. Runs in silent (auto-update) mode.
;
; The legacy sidecar name (jeopardy-backend.exe, pre-rename "Chaewon
; Jeopardy" installs through v2.3.0) is swept as well: the rename-era update
; is initiated by an old app whose own teardown only knows the old name.

!macro customInit
  nsExec::Exec 'taskkill /IM rhubarb-backend.exe /F /T'
  nsExec::Exec 'taskkill /IM jeopardy-backend.exe /F /T'
  Sleep 600
!macroend

!macro customUnInit
  nsExec::Exec 'taskkill /IM rhubarb-backend.exe /F /T'
  nsExec::Exec 'taskkill /IM jeopardy-backend.exe /F /T'
  Sleep 600
!macroend

; Rename-era shortcut hygiene: the update creates "Rhubarb" shortcuts, but
; NSIS knows nothing about the old name's shortcuts - without this, a stale
; "Chaewon Jeopardy" shortcut lingers pointing at an exe that no longer
; exists. Harmless no-ops on fresh installs.
!macro customInstall
  Delete "$DESKTOP\Chaewon Jeopardy.lnk"
  Delete "$SMPROGRAMS\Chaewon Jeopardy.lnk"
!macroend
