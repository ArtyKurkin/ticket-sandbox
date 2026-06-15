function initLucide(root = document) {
  if (!window.lucide || typeof window.lucide.createIcons !== "function") {
    return;
  }

  try {
    window.lucide.createIcons({ root });
  } catch (error) {
    console.error("Lucide init error:", error);
  }
}

function openTerminalModal() {
  const terminalCard = document.getElementById("terminal-card");

  if (!terminalCard) {
    return;
  }

  terminalCard.classList.add("is-expanded");
  document.body.classList.add("terminal-is-expanded");

  setTimeout(function () {
    window.dispatchEvent(new Event("resize"));
  }, 100);
}

function closeTerminalModal() {
  const terminalCard = document.getElementById("terminal-card");

  if (!terminalCard) {
    return;
  }

  terminalCard.classList.remove("is-expanded");
  document.body.classList.remove("terminal-is-expanded");

  setTimeout(function () {
    window.dispatchEvent(new Event("resize"));
  }, 100);
}

function bindTerminalButtons() {
  const expandButton = document.getElementById("terminal-expand-button");
  const collapseButton = document.getElementById("terminal-collapse-button");

  if (expandButton) {
    expandButton.addEventListener("click", openTerminalModal);
  }

  if (collapseButton) {
    collapseButton.addEventListener("click", closeTerminalModal);
  }
}

function removeTerminalFrames() {
  document.querySelectorAll("iframe").forEach(function (frame) {
    frame.remove();
  });
}

function removeTerminalFramesBeforeSubmit() {
  document.querySelectorAll("form").forEach(function (form) {
    if (form.dataset.terminalCleanupBound === "true") {
      return;
    }

    form.dataset.terminalCleanupBound = "true";
    form.addEventListener("submit", function () {
      removeTerminalFrames();
    });
  });
}

function removeTerminalFramesBeforeLinks() {
  document.querySelectorAll("a").forEach(function (link) {
    if (link.dataset.terminalCleanupBound === "true") {
      return;
    }

    link.dataset.terminalCleanupBound = "true";
    link.addEventListener("click", function () {
      removeTerminalFrames();
    });
  });
}

async function copyShellCommand() {
  const shellCommand = document.getElementById("shell-command");
  if (!shellCommand) return;

  try {
    await navigator.clipboard.writeText(shellCommand.innerText.trim());
    console.log("Команда скопирована");
  } catch (error) {
    console.error("Clipboard error:", error);
    alert("Не удалось скопировать команду");
  }
}

function bindLoadingButtons(root = document) {
  root.querySelectorAll("button[data-loading-text]").forEach(function (button) {
    const form = button.closest("form");
    if (!form || form.dataset.loadingBound === "true") {
      return;
    }

    form.dataset.loadingBound = "true";
    form.addEventListener("submit", function () {
      button.disabled = true;
      button.classList.add("is-loading");

      const label = button.querySelector(".button-label");
      if (label) {
        button.dataset.originalText = label.textContent;
        label.textContent = button.dataset.loadingText;
      }

      if (!button.querySelector(".button-spinner")) {
        const spinner = document.createElement("i");
        spinner.dataset.lucide = "loader-circle";
        spinner.className = "button-spinner";
        button.prepend(spinner);
        initLucide(button);
      }
    });
  });
}

function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }

  const textarea = document.createElement("textarea");

  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  document.execCommand("copy");
  textarea.remove();

  return Promise.resolve();
}

function setupCopyButtons() {
  document.querySelectorAll("[data-copy-target]").forEach(function(button) {
    button.addEventListener("click", function() {
      const targetId = button.dataset.copyTarget;
      const target = document.getElementById(targetId);

      if (!target) {
        return;
      }

      const text = target.innerText.trim();

      if (!text) {
        return;
      }

      const label = button.querySelector(".button-label");
      const originalText = button.dataset.copyLabel || "Скопировать";
      const copiedText = button.dataset.copiedLabel || "Скопировано";

      copyTextToClipboard(text).then(function() {
        if (label) {
          label.textContent = copiedText;
        }

        button.disabled = true;

        setTimeout(function() {
          if (label) {
            label.textContent = originalText;
          }

          button.disabled = false;
        }, 1200);
      });
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  initLucide();
  removeTerminalFramesBeforeSubmit();
  removeTerminalFramesBeforeLinks();
  bindLoadingButtons();
  bindTerminalButtons();
  setupCopyButtons();
});

window.initLucide = initLucide;
window.openTerminalModal = openTerminalModal;
window.closeTerminalModal = closeTerminalModal;
window.removeTerminalFrames = removeTerminalFrames;
window.copyShellCommand = copyShellCommand;
