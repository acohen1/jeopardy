/**
 * Preload — exposes EXACTLY the DesktopBridge contract from
 * frontend/src/lib/desktop.ts as window.jeopardy.
 *
 * contextIsolation: true / nodeIntegration: false — the renderer only ever
 * sees the frozen object below.
 */

'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Sync fetch once at preload time so `appVersion` is a plain string property.
const appVersion = ipcRenderer.sendSync('jeopardy:app-version');

/**
 * Wrap ipcRenderer.on for a channel, passing only the payload to the
 * callback, and return an unsubscribe function.
 */
function subscribe(channel, cb) {
  const listener = (_event, payload) => cb(payload);
  ipcRenderer.on(channel, listener);
  return () => ipcRenderer.removeListener(channel, listener);
}

contextBridge.exposeInMainWorld('jeopardy', {
  /** Installed app version, e.g. "2.1.0". */
  appVersion,

  updates: {
    getState: () => ipcRenderer.invoke('jeopardy:update-get-state'),
    check: () => {
      ipcRenderer.send('jeopardy:update-check');
    },
    restartToUpdate: () => {
      ipcRenderer.send('jeopardy:update-restart');
    },
    onState: (cb) => subscribe('jeopardy:update-state', cb),
  },

  whatsNew: {
    get: () => ipcRenderer.invoke('jeopardy:whats-new'),
    dismiss: () => {
      ipcRenderer.send('jeopardy:whats-new-dismiss');
    },
  },

  onImported: (cb) => subscribe('jeopardy:imported', cb),

  storage: {
    getInfo: () => ipcRenderer.invoke('jeopardy:storage-info'),
    openFolder: () => {
      ipcRenderer.send('jeopardy:storage-open');
    },
    choose: () => ipcRenderer.invoke('jeopardy:storage-choose'),
    resetToDefault: () => ipcRenderer.invoke('jeopardy:storage-reset'),
  },

  lan: {
    get: () => ipcRenderer.invoke('jeopardy:lan-info'),
    set: (enabled) => ipcRenderer.invoke('jeopardy:lan-set', enabled),
  },

  remote: {
    start: () => ipcRenderer.invoke('jeopardy:remote-start'),
    stop: () => ipcRenderer.invoke('jeopardy:remote-stop'),
    get: () => ipcRenderer.invoke('jeopardy:remote-get'),
    onState: (cb) => subscribe('jeopardy:remote-state', cb),
  },
});
