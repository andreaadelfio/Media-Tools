# Media Browser Suite

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
.\install_media_browser_suite.bat
```

L'installer crea una installazione utente separata dal repository:

- cartella applicazione: `%LOCALAPPDATA%\MediaBrowserSuite`
- virtual environment: `%LOCALAPPDATA%\MediaBrowserSuite\venv`
- launcher globale: `%USERPROFILE%\.local\bin\media-browser-suite.cmd`

Se `%USERPROFILE%\.local\bin` non e gia nel `PATH` utente, l'installer lo aggiunge automaticamente.

Dopo l'installazione il comando globale diventa:

```powershell
media-browser-suite
```

Il launcher apre anche il browser su `http://127.0.0.1:8765` in automatico.

Se preferisci non aspettare un nuovo terminale, puoi usare subito:

```powershell
$HOME\.local\bin\media-browser-suite.cmd
```

oppure i launcher del repository:

```powershell
.\run_media_browser_suite.bat
.\media-browser-suite.cmd
```

Entrambi provano prima a usare l'installazione globale e solo in fallback un eventuale `.venv` locale del repo.

Se vuoi comunque attivare manualmente il venv installato:

```powershell
powershell -ExecutionPolicy Bypass -NoExit -Command "& '$env:LOCALAPPDATA\MediaBrowserSuite\venv\Scripts\Activate.ps1'"
```

Oppure puoi evitare del tutto l'attivazione e lanciare direttamente:

```powershell
$env:LOCALAPPDATA\MediaBrowserSuite\venv\Scripts\media-browser-suite.exe
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
- `requirements.txt` resta utile per installazioni rapide, ma per lavorare bene sul progetto conviene usare `install.ps1`, che crea l'installazione nella cartella utente e registra il launcher globale.
- Il modulo `bird_audio_batch` usa BirdNET e nella suite installiamo direttamente `tensorflow` insieme alle altre dipendenze Python.
- Le thumbnail vengono cacheate nella home utente, in `~/.media-browser-suite/thumbnails`, con indice in `~/.media-browser-suite/thumbnail_index.json`, usando path, dimensione e timestamp del file sorgente per ritrovarle o rigenerarle quando serve.
