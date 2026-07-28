const MENU_ID = "send-to-beidanci";
const HOST_NAME = "com.touchfish.beidanci";
const WORD_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 '\-]*$/;

let nativePort = null;
let pendingRequest = null;

function createMenu() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_ID,
      title: "📥 发送到背单词并翻译",
      contexts: ["selection"]
    });
  });
}

chrome.runtime.onInstalled.addListener(createMenu);
chrome.runtime.onStartup.addListener(createMenu);

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icons/128.png",
    title,
    message
  });
}

async function showTranslationCard(tabId, payload) {
  if (!Number.isInteger(tabId)) return false;
  try {
    await chrome.scripting.executeScript({
      target: {tabId},
      files: ["content.js"]
    });
    await chrome.tabs.sendMessage(tabId, {type: "beidanci-card", ...payload});
    return true;
  } catch (_) {
    // chrome:// 等受限页面不能注入；由调用方回退到系统通知。
    return false;
  }
}

function resetNativePort() {
  nativePort = null;
  if (pendingRequest) {
    clearTimeout(pendingRequest.timer);
    pendingRequest = null;
  }
}

function ensureNativePort() {
  if (nativePort) return nativePort;
  nativePort = chrome.runtime.connectNative(HOST_NAME);
  nativePort.onMessage.addListener((response) => {
    if (!pendingRequest) return;
    const current = pendingRequest;
    clearTimeout(current.timer);
    pendingRequest = null;
    current.resolve(response);
  });
  nativePort.onDisconnect.addListener(() => {
    const detail = chrome.runtime.lastError?.message || "本机通信已断开";
    if (pendingRequest) {
      const current = pendingRequest;
      clearTimeout(current.timer);
      pendingRequest = null;
      current.reject(new Error(detail));
    }
    nativePort = null;
  });
  return nativePort;
}

function translateWithHost(english) {
  if (pendingRequest) {
    return Promise.reject(new Error("上一条翻译仍在进行中"));
  }
  return new Promise((resolve, reject) => {
    const port = ensureNativePort();
    const timer = setTimeout(() => {
      pendingRequest = null;
      try { port.disconnect(); } catch (_) {}
      nativePort = null;
      reject(new Error("翻译超时，请检查网络后重试"));
    }, 25000);
    pendingRequest = {resolve, reject, timer};
    port.postMessage({type: "translate", english});
  });
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) return;
  const english = String(info.selectionText || "").trim().replace(/\s+/g, " ");
  const tabId = tab?.id;

  if (english.length < 1 || english.length > 64) {
    const message = "只支持 1–64 个字符的英文单词或短语";
    const shown = await showTranslationCard(tabId, {
      phase: "error", english, message
    });
    if (!shown) notify("无法发送", message);
    return;
  }
  if (!WORD_PATTERN.test(english)) {
    const message = "仅支持英文、数字、空格、连字符和撇号";
    const shown = await showTranslationCard(tabId, {
      phase: "error", english, message
    });
    if (!shown) notify("无法发送", message);
    return;
  }

  await showTranslationCard(tabId, {phase: "loading", english});
  try {
    const response = await translateWithHost(english);
    if (response?.status !== "ok") {
      throw new Error(response?.message || response?.code || "翻译失败");
    }
    const message = `${response.english} → ${response.chinese}`;
    const shown = await showTranslationCard(tabId, {
      phase: "success",
      english: response.english,
      chinese: response.chinese,
      added: response.added
    });
    if (!shown) {
      notify(response.added ? "已加入背单词" : "已更新翻译", message);
    }
    await chrome.storage.local.set({
      lastResult: {
        ...response,
        timestamp: Date.now()
      }
    });
  } catch (error) {
    const raw = String(error?.message || error);
    const message = raw.includes("native messaging host")
      ? "未找到背单词 Native Host，请先运行安装脚本"
      : raw;
    const shown = await showTranslationCard(tabId, {
      phase: "error", english, message
    });
    if (!shown) notify("翻译失败", message);
  }
});
