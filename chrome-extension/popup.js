chrome.storage.local.get("lastResult").then(({lastResult}) => {
  if (!lastResult) return;
  const when = new Date(lastResult.timestamp).toLocaleString();
  document.getElementById("last").textContent =
    `最近：${lastResult.english} → ${lastResult.chinese}\n${when}`;
});
