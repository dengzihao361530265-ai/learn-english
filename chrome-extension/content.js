if (!globalThis.__beidanciCardInstalled) {
  globalThis.__beidanciCardInstalled = true;

  const ROOT_ID = "__beidanci_translation_card";
  let anchorRect = null;
  let dismissTimer = null;

  function rememberSelectionPosition() {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return;
    const rect = selection.getRangeAt(0).getBoundingClientRect();
    if (rect.width || rect.height) {
      anchorRect = {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom
      };
    }
  }

  function removeCard() {
    if (dismissTimer) clearTimeout(dismissTimer);
    dismissTimer = null;
    document.getElementById(ROOT_ID)?.remove();
  }

  function positionCard(host, card) {
    const anchor = anchorRect || {
      left: Math.max(16, window.innerWidth / 2 - 20),
      right: Math.max(56, window.innerWidth / 2 + 20),
      top: window.innerHeight / 2,
      bottom: window.innerHeight / 2
    };
    const margin = 12;
    const edge = 12;
    const width = card.offsetWidth;
    const height = card.offsetHeight;
    let left = anchor.left + (anchor.right - anchor.left - width) / 2;
    left = Math.max(edge, Math.min(left, window.innerWidth - width - edge));
    let top = anchor.bottom + margin;
    if (top + height > window.innerHeight - edge) {
      top = Math.max(edge, anchor.top - height - margin);
    }
    host.style.left = `${Math.round(left)}px`;
    host.style.top = `${Math.round(top)}px`;
  }

  function renderCard(message) {
    rememberSelectionPosition();
    removeCard();

    const host = document.createElement("div");
    host.id = ROOT_ID;
    Object.assign(host.style, {
      all: "initial",
      position: "fixed",
      zIndex: "2147483647",
      left: "12px",
      top: "12px"
    });
    const shadow = host.attachShadow({mode: "open"});

    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      .card {
        box-sizing: border-box; width: min(360px, calc(100vw - 24px));
        padding: 14px 15px 13px; border: 1px solid rgba(22, 95, 67, .16);
        border-radius: 14px; background: rgba(255,255,255,.98); color: #17231e;
        box-shadow: 0 14px 40px rgba(23, 45, 35, .22), 0 2px 8px rgba(23,45,35,.1);
        font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI",
          "Microsoft YaHei UI", sans-serif; backdrop-filter: blur(16px);
        animation: enter .16s ease-out;
      }
      .top { display: flex; align-items: center; gap: 9px; min-width: 0; }
      .mark {
        display: grid; place-items: center; flex: 0 0 auto; width: 26px; height: 26px;
        border-radius: 8px; color: #fff; background: linear-gradient(135deg,#0a84ff,#5e5ce6);
        font-size: 12px; font-weight: 750;
      }
      .word { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis;
        white-space: nowrap; font-size: 15px; font-weight: 650; letter-spacing: .01em; }
      button { border: 0; font: inherit; cursor: pointer; }
      .close { flex: 0 0 auto; width: 26px; height: 26px; padding: 0;
        border-radius: 7px; color: #748078; background: transparent; font-size: 18px; }
      .close:hover { background: #eef3f0; color: #34463d; }
      .body { margin: 11px 0 2px 35px; color: #253c31; font-size: 15px;
        line-height: 1.65; overflow-wrap: anywhere; }
      .loading { display: flex; align-items: center; gap: 9px; color: #66766e; font-size: 13px; }
      .spinner { width: 13px; height: 13px; border: 2px solid #d8e5df;
        border-top-color: #2b9b70; border-radius: 50%; animation: spin .7s linear infinite; }
      .footer { display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin: 10px 0 0 35px; color: #75827b; font-size: 12px; }
      .status { display: inline-flex; align-items: center; gap: 5px; color: #26815f; }
      .copy { padding: 3px 8px; border-radius: 6px; color: #52645b; background: #edf4f0;
        font-size: 12px; }
      .copy:hover { background: #e1eee7; }
      .error .mark { background: #bf493f; }
      .error .body { color: #9c352e; font-size: 13px; }
      @keyframes spin { to { transform: rotate(360deg); } }
      @keyframes enter { from { opacity: 0; transform: translateY(-4px) scale(.98); }
        to { opacity: 1; transform: translateY(0) scale(1); } }
      @media (prefers-color-scheme: dark) {
        .card { border-color: #3a4b43; background: rgba(29,35,32,.98); color: #edf4f0;
          box-shadow: 0 14px 44px rgba(0,0,0,.38); }
        .body { color: #dce8e2; } .loading { color: #aab8b1; }
        .close { color: #aab5af; } .close:hover { background: #39443f; color: #fff; }
        .copy { color: #c5d3cc; background: #35443d; }
        .copy:hover { background: #40534a; } .error .body { color: #ffaaa3; }
      }
    `;

    const card = document.createElement("div");
    card.className = `card ${message.phase === "error" ? "error" : ""}`;

    const top = document.createElement("div");
    top.className = "top";
    const mark = document.createElement("span");
    mark.className = "mark";
    mark.textContent = "Aa";
    const word = document.createElement("div");
    word.className = "word";
    word.textContent = message.english || "背单词";
    const close = document.createElement("button");
    close.className = "close";
    close.type = "button";
    close.title = "关闭";
    close.setAttribute("aria-label", "关闭翻译卡片");
    close.textContent = "×";
    close.addEventListener("click", removeCard);
    top.append(mark, word, close);

    const body = document.createElement("div");
    body.className = "body";
    if (message.phase === "loading") {
      body.classList.add("loading");
      const spinner = document.createElement("span");
      spinner.className = "spinner";
      const text = document.createElement("span");
      text.textContent = "正在翻译并加入词库…";
      body.append(spinner, text);
    } else if (message.phase === "success") {
      body.textContent = message.chinese || "";
    } else {
      body.textContent = message.message || "翻译失败，请稍后重试";
    }

    card.append(top, body);

    if (message.phase === "success") {
      const footer = document.createElement("div");
      footer.className = "footer";
      const status = document.createElement("span");
      status.className = "status";
      status.textContent = message.added ? "✓ 已加入背单词" : "✓ 已更新词库";
      const copy = document.createElement("button");
      copy.className = "copy";
      copy.type = "button";
      copy.textContent = "复制释义";
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(message.chinese || "");
          copy.textContent = "已复制";
        } catch (_) {
          copy.textContent = "复制失败";
        }
      });
      footer.append(status, copy);
      card.append(footer);
    }

    shadow.append(style, card);
    (document.body || document.documentElement).appendChild(host);
    positionCard(host, card);

    if (message.phase !== "loading") {
      dismissTimer = setTimeout(removeCard, message.phase === "success" ? 12000 : 8000);
    }
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "beidanci-card") renderCard(message);
  });
}
