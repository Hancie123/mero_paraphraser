; Installer hooks for Mero Paraphraser (see bundle.windows.nsis.installerHooks).
;
; A release is a folder with the installer and an "ai" folder next to it
; (built by scripts/package-release.mjs). After installing, copy that folder
; into the app's data folder, where backend/paraphraser/ai.py looks for it.
; Without the "ai" folder (or for updates) nothing is copied and the app
; downloads the model on first launch instead.
;
; The uninstaller's "Delete the application data" option removes
; $LOCALAPPDATA\${BUNDLEID}, which includes the model.

!define MERO_AI_MODEL_FILE "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"

!macro NSIS_HOOK_POSTINSTALL
  IfFileExists "$EXEDIR\ai\models\${MERO_AI_MODEL_FILE}" 0 mero_ai_done
  IfFileExists "$LOCALAPPDATA\${BUNDLEID}\ai\models\${MERO_AI_MODEL_FILE}" mero_ai_done 0
    DetailPrint "Installing the offline AI model (2.5 GB)..."
    CreateDirectory "$LOCALAPPDATA\${BUNDLEID}\ai"
    CopyFiles /SILENT "$EXEDIR\ai\*.*" "$LOCALAPPDATA\${BUNDLEID}\ai"
    DetailPrint "Offline AI model installed."
  mero_ai_done:
!macroend
