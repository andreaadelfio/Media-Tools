# MediaTools

Suite unica per esporre da browser i tool Python che manipolano immagini, video e suoni.

## Cosa include nella prima versione

- Naturalizzazione foto
- Overlay stereo tra due immagini
- Estrazione frame da video
- Creazione GIF da intervallo video
- Conversione video web / GoPro
- Bird audio batch analysis
- Bird audio denoise
- Bird audio live

## Installazione consigliata

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Se PowerShell blocca gli script, puoi usare anche:

```bat
.\install_media_tools.bat
```

L'installer crea una installazione utente separata dal repository:

- cartella applicazione: `%LOCALAPPDATA%\MediaTools`
- virtual environment: `%LOCALAPPDATA%\MediaTools\venv`
- snapshot sorgente usato per installare: `%LOCALAPPDATA%\MediaTools\source`
- artefatti build e metadati: `%LOCALAPPDATA%\MediaTools\build-artifacts` e `%LOCALAPPDATA%\MediaTools\source\media_tools.egg-info`
- launcher globale: `%USERPROFILE%\.local\bin\media-tools.cmd`
- alias globale aggiuntivo: `%USERPROFILE%\.local\bin\media_tools.cmd`

Se `%USERPROFILE%\.local\bin` o `%LOCALAPPDATA%\MediaTools\venv\Scripts` non sono gia nel `PATH` utente, l'installer li aggiunge automaticamente.

Dopo l'installazione i comandi globali diventano:

```powershell
media-tools
media_tools
```

Il launcher apre anche il browser su `http://127.0.0.1:8765` in automatico.

Se preferisci non aspettare un nuovo terminale, puoi usare subito:

```powershell
$HOME\.local\bin\media-tools.cmd
```

oppure i launcher del repository:

```powershell
.\run_media_tools.bat
.\media-tools.cmd
```

Questi launcher usano solo l'installazione utente dedicata e non creano o riusano un `.venv` locale nel repository.

Se vuoi comunque attivare manualmente il venv installato:

```powershell
powershell -ExecutionPolicy Bypass -NoExit -Command "& '$env:LOCALAPPDATA\MediaTools\venv\Scripts\Activate.ps1'"
```

Oppure puoi evitare del tutto l'attivazione e lanciare direttamente:

```powershell
$env:LOCALAPPDATA\MediaTools\venv\Scripts\media-tools.exe
```

## Avvio manuale

```powershell
pip install -r requirements.txt
python app.py
```

Poi apri `http://127.0.0.1:8765`.

## Flusso

1. Seleziona prima il tool dalla sidebar.
2. Imposta una cartella root di lavoro.
3. Sfoglia i soli file compatibili con il tool selezionato.
4. Configura i parametri del tool.
5. Lancia l'endpoint dal browser.

## Note

- La root selezionata viene limitata al backend corrente per evitare accessi fuori cartella.
- Alcuni strumenti richiedono dipendenze esterne gia presenti, per esempio `ffmpeg` per certe conversioni video.
- `requirements.txt` resta utile per installazioni rapide, ma per lavorare bene sul progetto conviene usare `install.ps1`, che crea l'installazione nella cartella utente, tiene fuori dal repo `build` e `*.egg-info`, e registra i launcher globali.
- Il modulo `bird_audio_batch` usa BirdNET e nella suite installiamo direttamente `tensorflow` insieme alle altre dipendenze Python.
- Le thumbnail vengono cacheate nella home utente, in `~/.media-tools/thumbnails`, con indice in `~/.media-tools/thumbnail_index.json`, usando path, dimensione e timestamp del file sorgente per ritrovarle o rigenerarle quando serve.
