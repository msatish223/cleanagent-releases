# CleanAgent v2.0

Intelligent system optimizer for Mac & Windows. AI-powered recommendations, safe cleanup, and performance monitoring — all running locally on your machine.

## What's New in v2.0
- **AI Insights Panel** — prioritized recommendations after every scan
- **Thread-safe backend** — no more race conditions during scan
- **Better Windows support** — proper cache paths, crash dump cleanup, registry startup items
- **Auto-browser launch** — opens dashboard automatically when you start the app
- **Stability fixes** — graceful error handling throughout

## Project Structure
```
cleanagent/
├── app.py                 # Flask server (main entry point)
├── scanner.py             # System scanner (cross-platform)
├── cleaner.py             # Cleanup engine (cross-platform)
├── ai_advisor.py          # AI recommendation engine
├── requirements.txt       # Python dependencies
├── cleanagent.spec        # PyInstaller build config
├── templates/
│   └── dashboard.html     # Web dashboard UI
├── static/                # (future: icons, CSS)
└── .github/
    └── workflows/
        └── build.yml      # Auto-build Windows .exe & Mac binary
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

# Opens http://127.0.0.1:5000 automatically
```

## Building Executables

### Via GitHub Actions (recommended)
1. Push this repo to GitHub
2. Go to Actions → "Build CleanAgent" → Run workflow
3. Download the artifacts: `CleanAgent-Windows.exe` and `CleanAgent-Mac`

### To auto-create releases:
```bash
git tag v2.0.0
git push origin v2.0.0
```
This triggers the build AND creates a GitHub Release with both binaries attached.

### Local build (on the target platform)
```bash
pip install pyinstaller
pyinstaller cleanagent.spec --clean --noconfirm
# Output: dist/CleanAgent.exe (Windows) or dist/CleanAgent (Mac)
```

## Windows Gatekeeper / SmartScreen
The unsigned .exe will trigger Windows SmartScreen on first run. Users need to click "More info" → "Run anyway". To avoid this, you'd need a code signing certificate (~$200-400/yr from DigiCert, Sectigo, etc).

## Mac Gatekeeper
Unsigned Mac binaries get blocked. Users must right-click → Open, or:
```bash
xattr -cr ./CleanAgent
```
For proper distribution, you'd need an Apple Developer account ($99/yr) for code signing and notarization.
