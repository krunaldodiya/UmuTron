# Automated Download & Unattended Installation Pipeline

This specification defines the architecture, decision matrix, and implementation strategy for automated, non-interactive (background/headless) game downloads and installations in UmuTron across all release formats.

---

## 1. Core Principles & Guardrails

1. **Zero Interactive Installer Windows**: The user must never be prompted with an interactive setup wizard, license agreement dialog, or manual directory picker during installation.
2. **Strict Exclusion of Multi-Part / Split Archives**: Any link, release, or torrent containing split or multi-part archives (`.part1.rar`, `.part01.rar`, `.7z.001`, `.z01`, chunked HTTP segments) is filtered out and excluded at the discovery/search level. Only single unified containers or complete torrents are eligible.
3. **Privilege & System Safety**:
   - Zero `sudo` or elevated permissions.
   - All downloads, staging, extractions, and prefix initializations execute strictly with the user's unprivileged permissions.
   - Staging is isolated at `~/.local/share/umutron/staging/<game_id>/`.
4. **Operation Locking**: The launcher supervisor retains an exclusive operation lock during active download, extraction, or silent installer execution. Only one installation or game launch may run at a time.
5. **Atomic Cleanup**: Setup binaries, intermediate archives, and installers are deleted after verified installation to reclaim disk space.

---

## 2. Exhaustive Content & Transport Matrix

| # | Transport Layer | Container Format | Inner Payload | Detection Heuristic | Unattended Pipeline Flow | Executable Resolution | Staging Cleanup | User UI Prompt |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **1** | **Torrent / Magnet** | **Loose Files** | **Pre-installed / Portable** | Directory contains game data assets (`Engine/`, `bin/`) and `.exe` binaries; **no** `setup.exe` or setup archives (`.bin`, `.doi`, `.cab`). | **No installer execution.** Move directory atomically from staging to final game destination `~/.local/share/umutron/games/<title>/`. | Score primary `.exe` by game title match, architecture (64-bit), and binary size in root or `bin/`. | None needed (directory moved directly). | **None** (Silent) |
| **2** | **Torrent / Magnet** | **Loose Files** | **Installer Package** | Root directory contains `setup.exe` / `install.exe` alongside setup archives (`data*.bin`, `*.doi`, `setup.cab`). | **1.** If Inno Setup: native `innoextract --silent -d <target_dir> setup.exe`<br>**2.** If NSIS/MSI: headless silent Proton run (`/S` or `/VERYSILENT /DIR=<target_dir>`). | Scan target game folder for main installed game binary (excluding redist and uninstallers). | Delete staging folder (`setup.exe`, `.bin` archives). | **None** (Silent) |
| **3** | **Torrent / Magnet** | **Single Archive / Disc** (`.zip`, `.rar`, `.7z`, `.iso`) | **Pre-installed / Portable** | Exactly one container file. Archive TOC inspection (`7z l`) displays game assets and binaries without setup executables. | **1.** Extract container directly into target game folder via native `7za x` (or loopback mount for `.iso`).<br>**2.** No Wine/Proton required during unpacking. | Scan extracted target folder for main game executable. | Delete the downloaded container file (`.iso`/`.zip`) from staging. | **None** (Silent) |
| **4** | **Torrent / Magnet** | **Single Archive / Disc** (`.iso`, `.zip`, `.rar`, `.7z`) | **Installer Package** | Exactly one container file. Archive TOC inspection (`7z l`) contains `setup.exe` + setup data files (or crack folder like `CODEX/`, `RUNE/`). | **1.** Extract/mount container to temporary directory.<br>**2.** Run silent installer (`innoextract` or headless `/VERYSILENT` via Proton).<br>**3.** If crack directory exists in container, copy crack files over target folder. | Scan target game folder for main installed binary. | Unmount and wipe temporary extracted folder and original container image. | **None** (Silent) |
| **5** | **Direct Download** | **Single Archive** (`.zip`, `.rar`, `.7z`) | **Pre-installed / Portable** | Single downloaded archive. Archive TOC inspection (`7z l`) shows root game binaries and asset folders; zero installer signatures. | **No installer execution.** Extract archive directly into final destination `~/.local/share/umutron/games/<title>/` using native `7za x`. | Scan destination folder for main game executable. | Delete downloaded archive from staging. | **None** (Silent) |
| **6** | **Direct Download** | **Single Archive** (`.zip`, `.rar`, `.7z`) | **Installer Package** | Single downloaded archive. Archive TOC inspection (`7z l`) contains `setup.exe` + `.bin` setup archives. | **1.** Extract archive to temporary staging folder.<br>**2.** Run unattended silent installation (`innoextract` or Proton silent switch `/VERYSILENT` / `/S`). | Scan destination folder for main installed binary. | Delete both temporary staging files and downloaded source archive. | **None** (Silent) |

---

## 3. Pipeline Stages & Detailed Workflow

### Stage 1: Download Ingestion & Multi-Part Filtering

1. **Pre-Download Filter**:
   - Inspect URI, torrent file metadata, and filenames.
   - If any file matches `(?i)\.(part\d+|7z\.\d+|\d{3}|z\d+)$`, reject and hide the release.
2. **Transport Handlers**:
   - **BitTorrent / Magnet**: Headless torrent client (embedded `libtorrent-rasterbar` or `aria2c` RPC) streaming directly to `~/.local/share/umutron/staging/<game_id>/`.
   - **Direct Download**: Multi-connection chunked HTTP/HTTPS streaming with resume support.

---

### Stage 2: Payload Inspection & Classification

Before invoking any Wine or Proton process, inspect the staged filesystem:

1. **Container Check**:
   - Is there a single archive (`.iso`, `.zip`, `.rar`, `.7z`)?
   - If yes, inspect its Table of Contents using `7z l -ba -slt <archive_file>` to determine if the internal files are portable assets or an installer package.
2. **Loose Files Check**:
   - Inspect files on disk or inside the extracted archive:
     - Search for `setup.exe`, `install.exe`, `installer.exe`.
     - Search for installer companions: `*.bin`, `*.doi`, `setup*.cab`.
   - If installer signature is **absent** $\to$ Classify as **Pre-installed / Portable**.
   - If installer signature is **present** $\to$ Classify as **Installer Package**.

---

### Stage 3: Headless / Unattended Installation Engine

When an installer is detected, bypass interactive wizards via three prioritized tiers:

#### Tier 1: Native Extraction (`innoextract`)
Applies to Inno Setup repacks (FitGirl, DODI, GOG, KaOsKrew, ByXatab, etc.).
- Bypasses Wine entirely; unpacks compressed `.bin` payloads at native Linux speed.
- **Command**:
  ```bash
  innoextract --silent --extract --output-dir "<destination_game_dir>" setup.exe
  ```

#### Tier 2: Proton Silent Command-Line Switches
When native extraction is unavailable (NSIS, standard Inno, InstallShield, Wise, MSI), detect the engine via PE header/strings inspection and execute with silent arguments:

- **Inno Setup**:
  ```bash
  umu-run setup.exe /VERYSILENT /SP- /NORESTART /SUPPRESSMSGBOXES /DIR="C:\Game"
  ```
- **NSIS**:
  ```bash
  umu-run setup.exe /S /D=C:\Game
  ```
- **InstallShield**:
  ```bash
  umu-run setup.exe /s /v"/qn INSTALLDIR=\"C:\Game\""
  ```
- **MSI**:
  ```bash
  umu-run msiexec.exe /i setup.msi /qn TARGETDIR="C:\Game"
  ```

#### Tier 3: Off-Screen Virtual Desktop (Headless Fallback)
For proprietary, highly custom repackers that refuse silent command-line flags:
- Run Proton inside a dedicated off-screen virtual display buffer (`Xvfb` or Proton desktop mode `explorer /desktop=Setup,1280x720`).
- The window is never visible to the user.
- Automated sequence signals default confirmations (`Enter`/`Space`) until installer exit.

---

### Stage 4: Executable Auto-Detection Engine

Once files are in the game folder (via direct extraction, portable move, or silent installer):

1. **Exclusion Filter**: Exclude non-game auxiliary binaries:
   - `unins*.exe`, `uninstall*.exe`, `UnityCrashHandler*.exe`, `crashreport*.exe`, `dxwebsetup.exe`, `vcredist*.exe`, `vc_redist*.exe`, `EasyAntiCheat*.exe`.
2. **Heuristic Scoring**:
   - Title token match (e.g., `witcher3.exe` for *The Witcher 3: Wild Hunt*).
   - Directory depth (prefer `bin/x64/`, `bin/Win64/`, or root).
   - Binary size and 64-bit architecture precedence over 32-bit launcher stubs.
3. **Library & Prefix Handoff**:
   - Initialize dedicated game prefix at `~/.local/share/umutron/prefixes/<game_id>/`.
   - Bind game entry to the discovered binary.
   - Update game state to **Installed**; enable **Play** button.

---

### Stage 5: Disk Space & Staging Cleanup

- Once the main game binary is verified in the target directory:
  - Delete staging directory contents (`setup.exe`, `.bin` archives, intermediate ISOs).
  - Sync filesystem buffers to reclaim storage.
