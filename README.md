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

Su Windows e Linux/macOS il flusso consigliato e' lo stesso:

```bash
make install
```

Questo comando:

- crea un virtual environment gestito fuori dal repository
- usa una cartella utente locale:
  Windows: `%LOCALAPPDATA%\MediaTools`
  Linux: `${XDG_DATA_HOME:-~/.local/share}/media-tools`
- aggiorna `pip`
- installa il progetto in editable mode con `pip install -e .[dev]`

In questo modo installazione e sviluppo usano lo stesso ambiente, senza snapshot separati del repository, senza `PYTHONPATH` forzati e senza riempire la cartella del repository su Dropbox con il venv e i pacchetti installati.

Se non usi `make`, puoi ottenere lo stesso risultato anche con:

```bash
python -m media_tools.devtools install
```

## Avvio

Per l'uso standard:

```bash
make run
```

Questo avvia l'app su `http://127.0.0.1:8765`.

Per sviluppo sul repository corrente:

```bash
make dev
```

`make dev` usa sempre il codice presente nel repository aperto, quindi ogni modifica locale viene vista subito. Di default gira su `http://127.0.0.1:8766`, cosi non collide con l'istanza standard.

Per eseguire i test:

```bash
make test
```

## Avvio manuale senza make

```bash
python -m media_tools.devtools install
python -m media_tools.devtools run
```

Se vuoi forzare una cartella diversa per il runtime gestito, puoi impostare `MEDIA_TOOLS_HOME`.

## Flusso

1. Seleziona prima il tool dalla sidebar.
2. Imposta una cartella root di lavoro.
3. Sfoglia i soli file compatibili con il tool selezionato.
4. Configura i parametri del tool.
5. Lancia l'endpoint dal browser.

## Note

- La root selezionata viene limitata al backend corrente per evitare accessi fuori cartella.
- Il pulsante `Sfoglia` usa il dialog di `tkinter`, quindi non richiede PowerShell o dipendenze extra; se il dialog non e' disponibile puoi sempre inserire la path manualmente.
- Alcuni strumenti richiedono dipendenze esterne gia presenti, per esempio `ffmpeg` per certe conversioni video.
- `requirements.txt` punta al progetto stesso in editable mode, cosi resta allineato al `pyproject.toml` e non duplica la lista dipendenze.
- Il modulo `bird_audio_batch` usa BirdNET e nella suite installiamo direttamente `tensorflow` insieme alle altre dipendenze Python.
- `bird_audio_live` ora usa un worker interno al package e non richiede piu la presenza di un repository fratello separato.
- I vecchi alias runtime `MEDIA_BROWSER_*`, la cartella `workspace` e l'entrypoint `media-tools-dev` sono stati rimossi per tenere il progetto piu lineare.
- Le thumbnail vengono cacheate nella home utente, in `~/.media-tools/thumbnails`, con indice in `~/.media-tools/thumbnail_index.json`, usando path, dimensione e timestamp del file sorgente per ritrovarle o rigenerarle quando serve.
