/**
 * Chaewon Jeopardy — Electron main process.
 *
 * Responsibilities:
 *   - single-instance lock (second launch focuses window + forwards argv)
 *   - spawn/kill the FastAPI sidecar (resources/jeopardy-backend.exe)
 *   - .jeopardy file association -> POST /api/boards/import -> 'jeopardy:imported'
 *   - electron-updater wired to the UpdateState contract in
 *     frontend/src/lib/desktop.ts (pushed via 'jeopardy:update-state')
 *   - what's-new persistence (settings.json under userData)
 *
 * Plain CommonJS on purpose — no bundler.
 */

'use strict';

const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn, spawnSync } = require('child_process');
const { Blob } = require('buffer');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

// ---------------------------------------------------------------------------
// Mode & constants
// ---------------------------------------------------------------------------

const isDev = process.env.JEOPARDY_DEV === '1' || !app.isPackaged;
const DEV_URL = 'http://localhost:5173';
const DEV_API = 'http://127.0.0.1:8000';
const HEALTH_TIMEOUT_MS = 20000;
const HEALTH_INTERVAL_MS = 250;
const UPDATE_RECHECK_MS = 4 * 60 * 60 * 1000; // 4 hours

/** @type {BrowserWindow | null} */
let mainWindow = null;
/** @type {import('child_process').ChildProcess | null} */
let sidecar = null;
let quitting = false;

/** Base URL of the backend API (set once the sidecar is up; dev uses :8000). */
let apiBase = isDev ? DEV_API : null;

/** Resolves once the backend answers /api/health (dev: once app is ready). */
let resolveBackendReady;
const backendReady = new Promise((resolve) => { resolveBackendReady = resolve; });

// ---------------------------------------------------------------------------
// Shell log — %APPDATA%/Chaewon Jeopardy/shell.log
// Field failures (like a broken update) were undiagnosable without this.
// ---------------------------------------------------------------------------

function shellLog(line) {
  try {
    const dir = path.join(app.getPath('appData'), 'Chaewon Jeopardy');
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(
      path.join(dir, 'shell.log'),
      `${new Date().toISOString()} ${line}\n`,
      'utf8'
    );
  } catch { /* logging must never break the app */ }
}

/**
 * Kill ANY jeopardy-backend.exe on the system — not just our child.
 * Orphaned sidecars (crashes, hard kills) keep the exe file locked, and a
 * locked file during an auto-update means NSIS silently skips it → corrupt
 * install → "spawn UNKNOWN" on next launch. Run before spawning and before
 * any update installs.
 */
function killStrayBackends(context) {
  if (process.platform !== 'win32') return;
  try {
    const result = spawnSync('taskkill', ['/IM', 'jeopardy-backend.exe', '/F', '/T'], {
      windowsHide: true,
      timeout: 10000,
    });
    if (result.status === 0) {
      shellLog(`killStrayBackends(${context}): stray sidecar(s) terminated`);
      // taskkill returning != handles released; give Windows a beat.
      spawnSync('cmd', ['/c', 'ping', '-n', '2', '127.0.0.1'], {
        windowsHide: true,
        timeout: 5000,
      });
    }
  } catch (err) {
    shellLog(`killStrayBackends(${context}) failed: ${err}`);
  }
}

/** Best-effort sweep of stale PyInstaller onefile extraction dirs (>24h). */
function sweepMeiOrphans() {
  try {
    const tmp = os.tmpdir();
    const cutoff = Date.now() - 24 * 3600 * 1000;
    for (const name of fs.readdirSync(tmp)) {
      if (!name.startsWith('_MEI')) continue;
      const p = path.join(tmp, name);
      try {
        if (fs.statSync(p).mtimeMs < cutoff) {
          fs.rmSync(p, { recursive: true, force: true });
        }
      } catch { /* in use or gone — skip */ }
    }
  } catch { /* best-effort */ }
}

// ---------------------------------------------------------------------------
// Settings (userData/settings.json): host override + what's-new persistence
// ---------------------------------------------------------------------------

const settingsPath = path.join(app.getPath('userData'), 'settings.json');

function loadSettings() {
  try {
    return JSON.parse(fs.readFileSync(settingsPath, 'utf8')) || {};
  } catch {
    return {};
  }
}

function saveSettings(settings) {
  try {
    fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
    fs.writeFileSync(settingsPath, JSON.stringify(settings, null, 2), 'utf8');
  } catch (err) {
    console.error('Failed to save settings:', err);
  }
}

let settings = loadSettings();

// ---------------------------------------------------------------------------
// Single instance lock
// ---------------------------------------------------------------------------

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', (_event, argv, workingDirectory) => {
    focusMainWindow();
    for (const p of jeopardyPathsFromArgv(argv, workingDirectory)) {
      queueImport(p);
    }
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function focusMainWindow() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

/** Extract absolute paths to existing .jeopardy files from an argv array. */
function jeopardyPathsFromArgv(argv, workingDirectory) {
  const out = [];
  for (const arg of argv || []) {
    if (typeof arg !== 'string') continue;
    if (arg.startsWith('-')) continue; // flags (e.g. --allow-file-access)
    if (!arg.toLowerCase().endsWith('.jeopardy')) continue;
    const abs = path.isAbsolute(arg)
      ? arg
      : path.resolve(workingDirectory || process.cwd(), arg);
    if (fs.existsSync(abs)) out.push(abs);
  }
  return out;
}

/** Find a free TCP port by binding to port 0 and reading the assignment. */
function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

/** Prefer a fixed port (stable TV URLs); fall back to any free one if taken. */
function getStablePort(preferred) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', () => resolve(getFreePort()));
    srv.listen(preferred, '0.0.0.0', () => {
      srv.close(() => resolve(preferred));
    });
  });
}

/** Non-internal IPv4 addresses — what a TV/phone on the wifi can reach. */
function lanAddresses() {
  const out = [];
  for (const ifaces of Object.values(os.networkInterfaces())) {
    for (const iface of ifaces || []) {
      if (iface.family === 'IPv4' && !iface.internal) out.push(iface.address);
    }
  }
  return out;
}

/** Poll GET /api/health until {"status":"ok"} or the timeout elapses. */
async function waitForHealth(base, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${base}/api/health`, {
        signal: AbortSignal.timeout(1000),
      });
      if (res.ok) {
        const body = await res.json();
        if (body && body.status === 'ok') return true;
      }
    } catch {
      // not up yet — keep polling
    }
    await new Promise((r) => setTimeout(r, HEALTH_INTERVAL_MS));
  }
  return false;
}

// ---------------------------------------------------------------------------
// Sidecar management
// ---------------------------------------------------------------------------

/** Default library location — the same directory the legacy app used. */
function defaultDataDir() {
  return path.join(app.getPath('appData'), 'Chaewon Jeopardy');
}

/** Effective data directory: the user's persisted choice, else the default. */
function getDataDir() {
  return typeof settings.dataDir === 'string' && settings.dataDir
    ? settings.dataDir
    : defaultDataDir();
}

/** Set while we intentionally bounce the sidecar (storage relocation) so the
 * unexpected-exit handler stays quiet. */
let respawning = false;

async function startSidecar() {
  const exePath = path.join(process.resourcesPath, 'jeopardy-backend.exe');
  if (!fs.existsSync(exePath)) {
    throw new Error(
      `Backend executable not found at:\n${exePath}\n\nReinstalling the app fixes this.`
    );
  }
  // A partially-written exe (interrupted update) fails as "spawn UNKNOWN" —
  // catch it here with a clear message instead.
  const sizeMb = fs.statSync(exePath).size / (1024 * 1024);
  if (sizeMb < 5) {
    shellLog(`sidecar exe suspicious size: ${sizeMb.toFixed(1)}MB`);
    throw new Error(
      `The backend file looks damaged (${sizeMb.toFixed(1)} MB) — likely an interrupted update.\n\nReinstalling the app fixes this.`
    );
  }

  const lanEnabled = settings.lan === true;
  const host = lanEnabled ? '0.0.0.0' : '127.0.0.1';
  // LAN mode wants a STABLE port so the TV URL survives relaunches; local-only
  // mode can take any free port.
  const port = lanEnabled ? await getStablePort(8477) : await getFreePort();
  const dataDir = getDataDir();

  // Spawn with retries: fresh-after-update binaries can be briefly locked by
  // AV scans or not-yet-released handles; one failure must not kill the app.
  let lastError = null;
  sidecar = null;
  for (let attempt = 1; attempt <= 3 && sidecar === null; attempt++) {
    try {
      shellLog(`spawning sidecar (attempt ${attempt}) port=${port} host=${host}`);
      const child = spawn(exePath, [], {
        env: {
          ...process.env,
          PORT: String(port),
          JEOPARDY_HOST: host,
          JEOPARDY_DATA_DIR: dataDir,
          FRONTEND_DIST: path.join(process.resourcesPath, 'frontend-dist'),
        },
        stdio: 'ignore',
        windowsHide: true,
      });
      // spawn errors (UNKNOWN/EACCES/…) arrive async — surface them here.
      await new Promise((resolve, reject) => {
        const onError = (err) => reject(err);
        child.once('error', onError);
        setTimeout(() => {
          child.removeListener('error', onError);
          resolve();
        }, 400);
      });
      sidecar = child;
    } catch (err) {
      lastError = err;
      shellLog(`sidecar spawn attempt ${attempt} failed: ${err}`);
      await new Promise((r) => setTimeout(r, 700));
    }
  }
  if (sidecar === null) {
    throw new Error(
      `Could not start the backend (${lastError}).\n\nReinstalling the app fixes this.`
    );
  }
  shellLog(`sidecar running pid=${sidecar.pid}`);

  sidecar.on('exit', (code) => {
    sidecar = null;
    if (!quitting && !respawning) {
      dialog.showErrorBox(
        'Chaewon Jeopardy',
        `The backend process exited unexpectedly (code ${code}). The app will now close.`
      );
      app.quit();
    }
  });

  const base = `http://127.0.0.1:${port}`;
  const healthy = await waitForHealth(base, HEALTH_TIMEOUT_MS);
  if (!healthy) {
    throw new Error('The backend did not become ready within 20 seconds.');
  }
  apiBase = base;
  return base;
}

/** Bounce the sidecar (after a storage change) and point the window at the
 * fresh instance. Only meaningful in packaged mode. */
async function restartSidecar() {
  respawning = true;
  try {
    stopTunnel(); // the port may change; the UI restarts remote play on demand
    killSidecar();
    const base = await startSidecar();
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadURL(base);
    }
    return base;
  } finally {
    respawning = false;
  }
}

/** Kill the sidecar and its whole process tree. Never leave an orphan. */
function killSidecar() {
  const proc = sidecar;
  sidecar = null;
  if (!proc || proc.killed || typeof proc.pid !== 'number') return;
  try {
    if (process.platform === 'win32') {
      spawnSync('taskkill', ['/pid', String(proc.pid), '/T', '/F'], {
        windowsHide: true,
        timeout: 10000,
      });
    } else {
      proc.kill('SIGTERM');
    }
  } catch (err) {
    console.error('Failed to kill sidecar:', err);
  }
}

// ---------------------------------------------------------------------------
// .jeopardy import handling
// ---------------------------------------------------------------------------

/** @type {string[]} */
const pendingImports = [];
let importsUnlocked = false;

function queueImport(filePath) {
  pendingImports.push(filePath);
  if (importsUnlocked) drainImports();
}

async function drainImports() {
  while (pendingImports.length > 0) {
    const fp = pendingImports.shift();
    await importJeopardyFile(fp);
  }
}

async function importJeopardyFile(filePath) {
  try {
    await backendReady;
    const buf = await fs.promises.readFile(filePath);
    const form = new FormData();
    form.append('file', new Blob([buf]), path.basename(filePath));
    const res = await fetch(`${apiBase}/api/boards/import`, {
      method: 'POST',
      body: form,
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = String(body.detail);
      } catch { /* non-JSON error body */ }
      throw new Error(detail);
    }
    const board = await res.json();
    const boardId = board && (board.id ?? board.boardId ?? board.board_id);
    if (boardId === undefined || boardId === null) {
      throw new Error('Import succeeded but the response had no board id.');
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('jeopardy:imported', String(boardId));
    }
    focusMainWindow();
  } catch (err) {
    dialog.showErrorBox(
      'Import failed',
      `Could not import "${path.basename(filePath)}":\n${err.message || err}`
    );
  }
}

// macOS-style open-file (harmless on Windows; argv covers Windows launches).
app.on('open-file', (event, filePath) => {
  event.preventDefault();
  if (filePath.toLowerCase().endsWith('.jeopardy')) queueImport(filePath);
});

// ---------------------------------------------------------------------------
// Updates (electron-updater -> UpdateState contract)
// ---------------------------------------------------------------------------

/** @type {import('electron-updater').AppUpdater | null} */
let autoUpdater = null;
try {
  autoUpdater = require('electron-updater').autoUpdater;
} catch (err) {
  console.error('electron-updater unavailable:', err);
}

/** Current UpdateState (see frontend/src/lib/desktop.ts). */
let updateState = { phase: 'idle' };
let manualCheckInFlight = false;

function setUpdateState(state) {
  updateState = state;
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send('jeopardy:update-state', state);
  }
}

/** releaseNotes may be a string (possibly HTML) or an array — flatten to text. */
function normalizeReleaseNotes(notes) {
  if (!notes) return '';
  if (Array.isArray(notes)) {
    return notes
      .map((n) => {
        const version = n && n.version ? `${n.version}\n` : '';
        const body = n && n.note ? stripHtml(String(n.note)) : '';
        return `${version}${body}`.trim();
      })
      .filter(Boolean)
      .join('\n\n');
  }
  return stripHtml(String(notes)).trim();
}

function stripHtml(s) {
  return s
    .replace(/<\s*br\s*\/?\s*>/gi, '\n')
    .replace(/<\/\s*(p|div|li|h[1-6]|ul|ol)\s*>/gi, '\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Translate electron-updater failures into one short human sentence; the
 *  raw errors are multi-line HTTP dumps. Full detail always goes to shell.log. */
function friendlyUpdateError(err) {
  const raw = err && err.message ? err.message : String(err);
  shellLog(`update check failed: ${raw}`);
  // latest.yml 404 = a release is mid-publish (the tag exists but artifacts
  // are still uploading) — the only time an installed app can see this.
  if (/latest\.yml/i.test(raw) && /404/.test(raw)) {
    return 'A new update is being published right now — hang tight and check again in a few minutes.';
  }
  if (/ERR_INTERNET_DISCONNECTED|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_NETWORK|ENOTFOUND|ETIMEDOUT|ECONNRESET|EAI_AGAIN/i.test(raw)) {
    return "Couldn't reach the update server — check your internet connection and try again.";
  }
  return raw.split('\n', 1)[0];
}

function setupAutoUpdater() {
  if (!autoUpdater) return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('checking-for-update', () => {
    setUpdateState({ phase: 'checking' });
  });

  autoUpdater.on('update-not-available', () => {
    manualCheckInFlight = false;
    setUpdateState({ phase: 'up-to-date' });
  });

  autoUpdater.on('update-available', () => {
    setUpdateState({ phase: 'downloading', percent: 0 });
  });

  autoUpdater.on('download-progress', (progress) => {
    setUpdateState({
      phase: 'downloading',
      percent: Math.round(progress && progress.percent ? progress.percent : 0),
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    manualCheckInFlight = false;
    const notes = normalizeReleaseNotes(info && info.releaseNotes);
    // Persist so the NEXT launch (post-install) can show "what's new".
    settings.pendingNotes = notes;
    settings.pendingVersion = info && info.version ? info.version : '';
    saveSettings(settings);
    setUpdateState({
      phase: 'ready',
      version: (info && info.version) || '',
      notes,
    });
  });

  autoUpdater.on('error', (err) => {
    const wasManual = manualCheckInFlight;
    manualCheckInFlight = false;
    const message = friendlyUpdateError(err); // always logs full detail
    if (wasManual) {
      // Only a MANUAL check surfaces errors...
      setUpdateState({ phase: 'error', message });
    } else {
      // ...a failing silent auto-check (offline, mid-publish) stays idle.
      setUpdateState({ phase: 'idle' });
    }
  });
}

function checkForUpdates(manual) {
  if (!app.isPackaged || !autoUpdater) {
    if (manual) {
      setUpdateState({
        phase: 'error',
        message: 'Updates are only available in the installed app.',
      });
    }
    return;
  }
  manualCheckInFlight = Boolean(manual);
  try {
    const p = autoUpdater.checkForUpdates();
    if (p && typeof p.catch === 'function') {
      p.catch(() => { /* handled by the 'error' event */ });
    }
  } catch (err) {
    // A missing/misconfigured feed must never crash the app.
    const wasManual = manualCheckInFlight;
    manualCheckInFlight = false;
    if (wasManual) {
      setUpdateState({ phase: 'error', message: friendlyUpdateError(err) });
    } else {
      setUpdateState({ phase: 'idle' });
    }
  }
}

// ---------------------------------------------------------------------------
// What's-new (shown once after an update, until dismissed)
// ---------------------------------------------------------------------------

/** @type {{ fromVersion: string, toVersion: string, notes: string } | null} */
let whatsNew = null;

function initWhatsNew() {
  const currentVersion = app.getVersion();
  const last = settings.lastRunVersion;

  if (last && last !== currentVersion && settings.pendingNotes) {
    // Keep lastRunVersion/pendingNotes untouched until dismissed so the
    // notice survives a relaunch, then clears exactly once on dismiss.
    whatsNew = {
      fromVersion: last,
      toVersion: currentVersion,
      notes: String(settings.pendingNotes),
    };
  } else if (last !== currentVersion) {
    settings.lastRunVersion = currentVersion;
    delete settings.pendingNotes;
    delete settings.pendingVersion;
    saveSettings(settings);
  }
}

function dismissWhatsNew() {
  whatsNew = null;
  settings.lastRunVersion = app.getVersion();
  delete settings.pendingNotes;
  delete settings.pendingVersion;
  saveSettings(settings);
}

// ---------------------------------------------------------------------------
// IPC surface (consumed by preload.cjs -> window.jeopardy)
// ---------------------------------------------------------------------------

ipcMain.on('jeopardy:app-version', (event) => {
  event.returnValue = app.getVersion();
});

ipcMain.handle('jeopardy:update-get-state', () => updateState);

ipcMain.on('jeopardy:update-check', () => {
  checkForUpdates(true);
});

// Discord-style update splash: our process dies the moment NSIS starts, so
// nothing WE own can show install progress. Instead we spawn a tiny detached
// WPF window (via PowerShell — deliberately nothing from the install dir, so
// it can never hold the file locks that caused the old corrupt-install bug).
// It tracks two phases by polling processes — "Preparing" while we tear down,
// "Installing" once we've exited — and closes itself when the new version
// boots (or after a 2-minute give-up).
//
// PS syntax notes: no backticks and no ${ } anywhere (JS template literal);
// here-string terminators must stay at column 0.
const UPDATE_SPLASH_PS1 = `param([int]$OldPid = 0)
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName PresentationFramework
[xml]$xaml = @'
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Chaewon Jeopardy" Width="340" Height="180"
        WindowStyle="None" ResizeMode="NoResize" WindowStartupLocation="CenterScreen"
        Topmost="True" ShowInTaskbar="True" Background="#252525">
  <Border BorderBrush="#505050" BorderThickness="1">
    <StackPanel VerticalAlignment="Center" HorizontalAlignment="Center">
      <TextBlock Text="CHAEWON JEOPARDY!" Foreground="#7daf8d" FontSize="16" FontWeight="Bold" HorizontalAlignment="Center" FontFamily="Segoe UI" />
      <TextBlock x:Name="StatusText" Text="Preparing update..." Foreground="#e5ddd5" FontSize="12" Margin="0,14,0,0" HorizontalAlignment="Center" FontFamily="Segoe UI" />
      <ProgressBar IsIndeterminate="True" Width="240" Height="6" Margin="0,12,0,0" Foreground="#7daf8d" Background="#38332e" BorderThickness="0" />
    </StackPanel>
  </Border>
</Window>
'@
$reader = New-Object System.Xml.XmlNodeReader $xaml
$window = [Windows.Markup.XamlReader]::Load($reader)
$status = $window.FindName('StatusText')
$script:phase = 1
$deadline = (Get-Date).AddSeconds(120)
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(500)
$timer.Add_Tick({
  if ((Get-Date) -gt $deadline) { $window.Close(); return }
  if ($script:phase -eq 1) {
    $old = $null
    if ($OldPid -gt 0) { $old = Get-Process -Id $OldPid -ErrorAction SilentlyContinue }
    if (-not $old) {
      $script:phase = 2
      $status.Text = 'Installing update...'
    }
  } else {
    $fresh = Get-Process -Name 'Chaewon Jeopardy' -ErrorAction SilentlyContinue
    if ($fresh) { Start-Sleep -Milliseconds 800; $window.Close() }
  }
})
$window.Add_Closed({ [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown() })
$timer.Start()
$window.Show()
[System.Windows.Threading.Dispatcher]::Run()
`;

function showUpdateSplash() {
  try {
    const splashPath = path.join(app.getPath('temp'), 'chaewon-update-splash.ps1');
    fs.writeFileSync(splashPath, UPDATE_SPLASH_PS1, 'utf8');
    spawn(
      'powershell.exe',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-STA', '-WindowStyle', 'Hidden', '-File', splashPath, String(process.pid)],
      { detached: true, stdio: 'ignore', windowsHide: true },
    ).unref();
    shellLog('update splash spawned');
  } catch (err) {
    // Cosmetic only — a missing splash must never block the update itself.
    shellLog('update splash failed to spawn: ' + err);
  }
}

ipcMain.on('jeopardy:update-restart', () => {
  if (!autoUpdater) return;
  quitting = true;
  // Splash first, then hide ourselves: the user sees ONE continuous
  // "updating" surface from click to relaunch instead of dead air.
  showUpdateSplash();
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
  shellLog('update-restart: tearing down sidecars before install');
  killSidecar();
  // The NSIS installer starts the moment we quit — ANY lingering backend
  // process (incl. orphans from old crashes) still holding the exe makes the
  // installer silently skip locked files → corrupt install → spawn UNKNOWN.
  killStrayBackends('pre-update');
  // Silent install + relaunch (Discord-style). Without isSilent the assisted
  // installer pops its full wizard on every update; the wizard should only
  // ever greet a first-time install.
  autoUpdater.quitAndInstall(true, true);
});

ipcMain.handle('jeopardy:whats-new', () => whatsNew);

ipcMain.on('jeopardy:whats-new-dismiss', () => {
  dismissWhatsNew();
});

// ---------------------------------------------------------------------------
// Storage location (data directory) — view, open, relocate, reset
// ---------------------------------------------------------------------------

function countBoards(dataDir) {
  try {
    const boardsDir = path.join(dataDir, 'boards');
    return fs
      .readdirSync(boardsDir, { withFileTypes: true })
      .filter((e) => e.isDirectory() && fs.existsSync(path.join(boardsDir, e.name, 'board.json')))
      .length;
  } catch {
    return 0;
  }
}

ipcMain.handle('jeopardy:storage-info', () => ({
  path: getDataDir(),
  boardCount: countBoards(getDataDir()),
  isDefault: getDataDir() === defaultDataDir(),
}));

ipcMain.on('jeopardy:storage-open', () => {
  const dir = getDataDir();
  fs.mkdirSync(dir, { recursive: true });
  shell.openPath(dir);
});

ipcMain.handle('jeopardy:storage-choose', async () => {
  if (isDev) {
    dialog.showMessageBox(mainWindow, {
      type: 'info',
      message: 'Changing the data folder is only available in the installed app.',
      detail: 'In development the backend owns its own data directory (backend/data).',
    });
    return null;
  }

  const picked = await dialog.showOpenDialog(mainWindow, {
    title: 'Choose where Chaewon Jeopardy stores your boards',
    defaultPath: getDataDir(),
    properties: ['openDirectory', 'createDirectory'],
  });
  if (picked.canceled || picked.filePaths.length === 0) return null;

  const target = picked.filePaths[0];
  const current = getDataDir();
  if (path.resolve(target) === path.resolve(current)) return { path: current };

  const targetHasLibrary = countBoards(target) > 0;
  const currentHasBoards = countBoards(current) > 0;

  if (!targetHasLibrary && currentHasBoards) {
    // Empty destination + existing library: offer to bring the boards along.
    const { response } = await dialog.showMessageBox(mainWindow, {
      type: 'question',
      buttons: ['Move my boards there', 'Start fresh there', 'Cancel'],
      defaultId: 0,
      cancelId: 2,
      message: 'Move your current library to the new folder?',
      detail:
        `Current library: ${current} (${countBoards(current)} board(s)).\n` +
        `Your boards will be copied to:\n${target}\n\n` +
        'The originals are left in place as a backup.',
    });
    if (response === 2) return null;
    if (response === 0) {
      const src = path.join(current, 'boards');
      if (fs.existsSync(src)) {
        await fs.promises.cp(src, path.join(target, 'boards'), { recursive: true });
      }
    }
  }
  // Destination already holding a library: just point at it (deliberate
  // "use my synced/second-disk folder" flow — nothing is copied or merged).

  settings.dataDir = target;
  saveSettings(settings);
  await restartSidecar();
  return { path: target };
});

ipcMain.handle('jeopardy:storage-reset', async () => {
  if (isDev || getDataDir() === defaultDataDir()) return;
  delete settings.dataDir;
  saveSettings(settings);
  await restartSidecar();
});

// ---------------------------------------------------------------------------
// LAN / TV-view access
// ---------------------------------------------------------------------------

ipcMain.handle('jeopardy:lan-info', () => {
  const enabled = settings.lan === true;
  const port = apiBase ? Number(new URL(apiBase).port) : null;
  return {
    enabled,
    urls:
      enabled && port
        ? lanAddresses().map((ip) => `http://${ip}:${port}`)
        : [],
  };
});

ipcMain.handle('jeopardy:lan-set', async (_event, enabled) => {
  if (isDev) return;
  settings.lan = enabled === true;
  saveSettings(settings);
  await restartSidecar();
});

// ---------------------------------------------------------------------------
// Remote play — cloudflared quick tunnel (friends join over the internet)
//
// The tunnel dials OUT to Cloudflare's edge and forwards a public
// https://…trycloudflare.com URL to the local backend — join page, API, and
// the live WebSocket all ride the same origin, so the whole session protocol
// works unchanged. No accounts, no hosting, no inbound firewall holes.
// ---------------------------------------------------------------------------

let tunnelProc = null;
let tunnelUrl = null;
/** @type {Promise<string> | null} */
let tunnelStarting = null;

function broadcastRemoteState() {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send('jeopardy:remote-state', { url: tunnelUrl });
    }
  }
}

function spawnTunnel() {
  return new Promise((resolve, reject) => {
    const exe = path.join(process.resourcesPath, 'cloudflared.exe');
    if (!fs.existsSync(exe)) {
      reject(new Error('The remote-play component is missing — reinstalling the app fixes this.'));
      return;
    }
    if (!apiBase) {
      reject(new Error('The backend is not running yet.'));
      return;
    }
    shellLog(`starting quick tunnel -> ${apiBase}`);
    const proc = spawn(exe, ['tunnel', '--url', apiBase, '--no-autoupdate'], {
      windowsHide: true,
      stdio: ['ignore', 'ignore', 'pipe'],
    });
    tunnelProc = proc;
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        stopTunnel();
        reject(new Error('The tunnel did not come up within 40 seconds — check your internet connection and try again.'));
      }
    }, 40000);
    // cloudflared prints the assigned URL to stderr.
    proc.stderr.on('data', (chunk) => {
      const m = String(chunk).match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/);
      if (m && !settled) {
        settled = true;
        clearTimeout(timeout);
        tunnelUrl = m[0];
        shellLog(`tunnel up: ${tunnelUrl}`);
        broadcastRemoteState();
        resolve(tunnelUrl);
      }
    });
    proc.on('exit', (code) => {
      shellLog(`tunnel exited code=${code}`);
      tunnelProc = null;
      tunnelUrl = null;
      broadcastRemoteState();
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(new Error(`The tunnel process exited unexpectedly (code ${code}).`));
      }
    });
    proc.on('error', (err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        tunnelProc = null;
        reject(err);
      }
    });
  });
}

async function startTunnel() {
  if (tunnelUrl) return tunnelUrl;
  if (!tunnelStarting) {
    tunnelStarting = spawnTunnel().finally(() => {
      tunnelStarting = null;
    });
  }
  return tunnelStarting;
}

function stopTunnel() {
  const proc = tunnelProc;
  tunnelProc = null;
  tunnelUrl = null;
  if (proc && !proc.killed && typeof proc.pid === 'number') {
    try {
      if (process.platform === 'win32') {
        spawnSync('taskkill', ['/pid', String(proc.pid), '/T', '/F'], {
          windowsHide: true,
          timeout: 10000,
        });
      } else {
        proc.kill('SIGTERM');
      }
    } catch (err) {
      shellLog(`failed to kill tunnel: ${err}`);
    }
  }
  broadcastRemoteState();
}

ipcMain.handle('jeopardy:remote-start', async () => ({ url: await startTunnel() }));
ipcMain.handle('jeopardy:remote-stop', () => {
  stopTunnel();
});
ipcMain.handle('jeopardy:remote-get', () => ({ url: tunnelUrl }));

// ---------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------

function createWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    backgroundColor: '#252525',
    icon: path.join(__dirname, 'build', 'icon.ico'),
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // preload needs require('electron')
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // target=_blank & window.open -> the user's default browser, never a child window.
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    if (/^https?:\/\//i.test(target)) shell.openExternal(target);
    return { action: 'deny' };
  });

  // In-page navigation to another origin -> default browser too.
  mainWindow.webContents.on('will-navigate', (event, target) => {
    const appOrigin = new URL(url).origin;
    let targetOrigin = null;
    try { targetOrigin = new URL(target).origin; } catch { /* ignore */ }
    if (targetOrigin && targetOrigin !== appOrigin) {
      event.preventDefault();
      if (/^https?:\/\//i.test(target)) shell.openExternal(target);
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.loadURL(url);
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

if (gotLock) {
  app.whenReady().then(async () => {
    shellLog(`app start v${app.getVersion()} packaged=${app.isPackaged}`);
    if (!isDev) {
      // Stale sidecars from crashes would fight us for the port AND hold
      // file locks through future updates; clear them before spawning ours.
      killStrayBackends('startup');
      sweepMeiOrphans();
    }
    initWhatsNew();
    setupAutoUpdater();

    // .jeopardy file passed on the command line at launch.
    for (const p of jeopardyPathsFromArgv(process.argv.slice(1), process.cwd())) {
      pendingImports.push(p);
    }

    let url;
    if (isDev) {
      // Dev: the integrator runs `npm run dev` (vite :5173 + uvicorn :8000).
      url = DEV_URL;
      resolveBackendReady();
    } else {
      try {
        url = await startSidecar();
        resolveBackendReady();
      } catch (err) {
        quitting = true;
        killSidecar();
        shellLog(`startup failed: ${err.message || err}`);
        dialog.showErrorBox(
          'Chaewon Jeopardy failed to start',
          `${err.message || err}`
        );
        app.quit();
        return;
      }
    }

    createWindow(url);

    importsUnlocked = true;
    drainImports();

    // Silent auto-check on launch + every 4 hours. Never crashes without a feed.
    checkForUpdates(false);
    const recheck = setInterval(() => checkForUpdates(false), UPDATE_RECHECK_MS);
    recheck.unref?.();
  });
}

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', () => {
  quitting = true;
  stopTunnel();
  killSidecar();
  // autoInstallOnAppQuit can run the installer right after this quit — make
  // sure no stray backend holds file locks when it does.
  if (!isDev) killStrayBackends('before-quit');
});

app.on('will-quit', () => {
  killSidecar();
});

process.on('exit', () => {
  killSidecar();
});
