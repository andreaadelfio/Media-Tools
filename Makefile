APPDATA_ROOT := $(LOCALAPPDATA)\MediaTools
VENV_PYTHON := $(APPDATA_ROOT)\venv\Scripts\python.exe
REPO_ROOT := $(CURDIR)

.PHONY: dev

dev:
	@if not exist "$(VENV_PYTHON)" (echo Installazione non trovata in "$(APPDATA_ROOT)". Esegui prima install.ps1 & exit /b 1)
	@set PYTHONPATH=$(REPO_ROOT) && set MEDIA_TOOLS_PORT=8766 && set MEDIA_TOOLS_OPEN=1 && cd /d "$(REPO_ROOT)" && "$(VENV_PYTHON)" -m media_tools
