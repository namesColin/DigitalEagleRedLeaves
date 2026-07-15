const DAEMON = "http://127.0.0.1:9020";
let tabId = null;

// Keep service worker alive
chrome.alarms.create("keepalive", { periodInMinutes: 0.5 });

async function getTab() {
  if (tabId) {
    try { await chrome.tabs.get(tabId); return tabId; } catch (e) { tabId = null; }
  }
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tabs.length) { tabId = tabs[0].id; return tabId; }
  const created = await chrome.tabs.create({ url: "about:blank" });
  tabId = created.id;
  return tabId;
}

async function handleCommand(cmd) {
  try {
    const tid = await getTab();
    const tab = await chrome.tabs.get(tid);
    await chrome.windows.update(tab.windowId, { focused: true });

    if (cmd.action === "navigate") {
      await chrome.tabs.update(tid, { url: cmd.url, active: true });
      return {};
    }

    await chrome.debugger.attach({ tabId: tid }, "1.3");

    let result;
    switch (cmd.action) {
      case "evaluate":
        result = await chrome.debugger.sendCommand({ tabId: tid }, "Runtime.evaluate", {
          expression: cmd.expression, returnByValue: true,
        });
        break;
      case "screenshot":
        result = await chrome.debugger.sendCommand({ tabId: tid }, "Page.captureScreenshot", {
          format: "png",
        });
        break;
      case "scroll":
        result = await chrome.debugger.sendCommand({ tabId: tid }, "Runtime.evaluate", {
          expression: `window.scrollBy(${cmd.x || 0}, ${cmd.y || 0})`, returnByValue: true,
        });
        break;
      case "click":
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchMouseEvent", {
          type: "mousePressed", x: cmd.x, y: cmd.y, button: "left", clickCount: 1,
        });
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchMouseEvent", {
          type: "mouseReleased", x: cmd.x, y: cmd.y, button: "left", clickCount: 1,
        });
        result = {};
        break;
      case "type":
        for (const ch of cmd.text) {
          await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyDown", key: ch, text: ch });
          await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyUp", key: ch });
        }
        result = {};
        break;
      case "press":
        const km = { Enter: "\r", Tab: "\t", Escape: "\x1b", Backspace: "\b" };
        const key = km[cmd.key] || cmd.key;
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyDown", key });
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyUp", key });
        result = {};
        break;
      default:
        result = { error: "unknown" };
    }
    await chrome.debugger.detach({ tabId: tid });
    return result || {};
  } catch (e) {
    return { error: e.message };
  }
}

async function poll() {
  while (true) {
    try {
      const resp = await fetch(DAEMON + "/pop");
      if (resp.ok) {
        const cmds = await resp.json();
        if (Array.isArray(cmds) && cmds.length > 0) {
          const tid = await getTab();
          const tab = await chrome.tabs.get(tid);
          await chrome.windows.update(tab.windowId, { focused: true });

          const navCmds = cmds.filter(c => c.action === "navigate");
          const cdpCmds = cmds.filter(c => c.action !== "navigate");

          for (const cmd of navCmds) {
            const r = await handleNav(cmd, tid);
            await pushResult(cmd.id, r);
          }

          if (cdpCmds.length > 0) {
            await chrome.debugger.attach({ tabId: tid }, "1.3");
            for (const cmd of cdpCmds) {
              const r = await execCdp(cmd, tid);
              await pushResult(cmd.id, r);
            }
            await chrome.debugger.detach({ tabId: tid });
          }
        }
      }
    } catch (e) { console.error(e); }
    await new Promise(r => setTimeout(r, 200));
  }
}

async function handleNav(cmd, tid) {
  try {
    await chrome.tabs.update(tid, { url: cmd.url, active: true });
    return {};
  } catch (e) { return { error: e.message }; }
}

async function execCdp(cmd, tid) {
  try {
    switch (cmd.action) {
      case "evaluate":
        return await chrome.debugger.sendCommand({ tabId: tid }, "Runtime.evaluate", {
          expression: cmd.expression, returnByValue: true,
        });
      case "screenshot":
        return await chrome.debugger.sendCommand({ tabId: tid }, "Page.captureScreenshot", {
          format: "png",
        });
      case "scroll":
        return await chrome.debugger.sendCommand({ tabId: tid }, "Runtime.evaluate", {
          expression: `window.scrollBy(${cmd.x || 0}, ${cmd.y || 0})`, returnByValue: true,
        });
      case "click":
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchMouseEvent", {
          type: "mousePressed", x: cmd.x, y: cmd.y, button: "left", clickCount: 1,
        });
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchMouseEvent", {
          type: "mouseReleased", x: cmd.x, y: cmd.y, button: "left", clickCount: 1,
        });
        return {};
      case "type":
        for (const ch of cmd.text) {
          await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyDown", key: ch, text: ch });
          await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyUp", key: ch });
        }
        return {};
      case "press":
        const km = { Enter: "\r", Tab: "\t", Escape: "\x1b", Backspace: "\b" };
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyDown", key: km[cmd.key] || cmd.key });
        await chrome.debugger.sendCommand({ tabId: tid }, "Input.dispatchKeyEvent", { type: "keyUp", key: km[cmd.key] || cmd.key });
        return {};
      default:
        return { error: "unknown: " + cmd.action };
    }
  } catch (e) { return { error: e.message }; }
}

async function pushResult(id, result) {
  try {
    await fetch(DAEMON + "/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, result }),
    });
  } catch (e) {}
}

poll();
