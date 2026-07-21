; Custom NSIS hooks for the Chaewon Jeopardy installer.
;
; The sidecar (jeopardy-backend.exe) holding a file lock during an update
; makes NSIS silently skip locked files -> corrupt install -> "spawn UNKNOWN".
; The app's shell sweeps strays before quitting (v2.2.1+), but the INSTALLER
; is the only code guaranteed to be new-version regardless of how old the
; initiating app is - so it sweeps too. Runs in silent (auto-update) mode.

!macro customInit
  nsExec::Exec 'taskkill /IM jeopardy-backend.exe /F /T'
  Sleep 600
!macroend

!macro customUnInit
  nsExec::Exec 'taskkill /IM jeopardy-backend.exe /F /T'
  Sleep 600
!macroend
