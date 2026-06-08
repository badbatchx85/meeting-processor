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

## Linux (AppImage)

Fully self-contained: the AppImage bundles a relocatable Python 3.11, CPU-only
torch + whisper, a static ffmpeg, and the app. Friends download one file, no
install or first-run download.

### One-time: generate the dependency lockfile

The build installs Python deps with `--require-hashes` from a committed
`desktop/requirements-linux.lock`, so that lock must exist first. Generate it on
Linux (the CPU torch wheels are Linux-specific):

- **Via CI:** run the **Lock Linux deps** workflow (Actions tab), download the
  `requirements-linux-lock` artifact, and commit it as
  `desktop/requirements-linux.lock`.
- **Locally on Linux:** `./desktop/lock-linux-deps.sh` then commit the result.

Re-run this whenever `requirements.txt` changes.

### Build

Must build on Linux (ubuntu-22.04 baseline). Locally:

```bash
./desktop/build-linux.sh
# → desktop/build/linux/Meeting_Processor-x86_64.AppImage
```

Or trigger the **Linux AppImage** GitHub Actions workflow (manual run, or push a
`v*` tag to attach it to a release).

All external binaries (Python, ffmpeg, linuxdeploy) are pinned and SHA-256
verified; the build fails closed on any mismatch.

### Run

```bash
chmod +x Meeting_Processor-x86_64.AppImage
./Meeting_Processor-x86_64.AppImage
```

Data lives in `~/.local/share/com.meetingprocessor.desktop/`.

### Manual smoke checklist (on a real Linux box)

- [ ] Launch the AppImage → the SPA loads at `/ui` with no setup screen.
- [ ] Process one recording end-to-end → exercises the bundled ffmpeg + CPU torch.
- [ ] Confirm `vault/` and logs appear under `~/.local/share/com.meetingprocessor.desktop/`.
- [ ] Quit → `pgrep -fl "meeting_processor web"` shows nothing (server killed).
