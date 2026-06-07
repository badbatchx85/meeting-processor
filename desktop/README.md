# Meeting Processor — Desktop (macOS)

Native macOS shell (Tauri) around the Meeting Processor server + SPA.

## Build

```bash
./desktop/build.sh
```

Produces `Meeting Processor.app` and a `.dmg` under
`desktop/src-tauri/target/release/bundle/`.

## First launch (for the people you share it with)

The app is **unsigned**. macOS Gatekeeper will block the first open. Once:

1. Right-click the app -> **Open** -> **Open** again. (Or run
   `xattr -dr com.apple.quarantine "/Applications/Meeting Processor.app"`.)
2. On first run the app detects/installs missing tools (Homebrew, Python 3.11,
   ffmpeg) and sets up its environment. This needs an internet connection.
3. All data lives in `~/Library/Application Support/com.meetingprocessor.desktop/`.

## Manual smoke checklist

- [ ] **Fresh setup:** delete `~/Library/Application Support/com.meetingprocessor.desktop/.venv`,
      relaunch -> setup runs, bootstraps venv, then the SPA loads.
- [ ] **Missing ffmpeg:** `brew uninstall ffmpeg`, relaunch -> ffmpeg shown missing,
      "Instalar e configurar" installs it, then app starts.
- [ ] **Port in use:** start something on a random port, relaunch -> app still
      picks a free port and starts (no 8765 dependency).
- [ ] **Quit kills server:** with the app running, `pgrep -fl "meeting_processor web"`
      shows the child; quit the app -> re-run `pgrep` shows nothing (no orphan).
- [ ] **Data isolation:** confirm `vault/` and logs appear under Application Support,
      not inside the `.app` bundle.
