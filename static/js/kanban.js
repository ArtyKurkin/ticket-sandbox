"use strict";

// Перетаскивание карточек реализовано на pointerdown/pointermove/pointerup,
// а не на нативном HTML5 draggable/dragstart — при использовании нативного
// Drag & Drop API браузер блокирует программные изменения scrollLeft во время
// активного drag-цикла, из-за чего автоскролл к краям доски физически
// не работает. Проверено опытным путём.

const AUTOSCROLL_ZONE_PX = 90;
const AUTOSCROLL_MIN_SPEED_PX = 5;
const AUTOSCROLL_MAX_SPEED_PX = 22;
const DRAG_START_THRESHOLD_PX = 6;

let pendingStageMove = null;

function initKanban() {
  const container = document.getElementById("kanban-board-container");
  if (!container) return;

  initStageMoveDialog(container);
  attachDragHandlers(container);
}

function initStageMoveDialog(container) {
  const dialog = document.getElementById("stage-move-dialog");
  const form = document.getElementById("stage-move-form");

  if (!dialog || !form) return;

  form.addEventListener("submit", function (event) {
    event.preventDefault();

    if (!pendingStageMove || !form.reportValidity()) {
      return;
    }

    const dateInput = document.getElementById("stage-move-date");
    const noteInput = document.getElementById("stage-move-note");

    setStageMoveDialogBusy(dialog, true);

    moveTraineeStage({
      moveUrl: pendingStageMove.moveUrl,
      stageId: pendingStageMove.stageId,
      transitionDate: dateInput.value,
      note: noteInput.value,
    })
      .then(function () {
        closeStageMoveDialog(dialog);
        return refreshKanbanBoard(container);
      })
      .catch(function (error) {
        showMoveError(
          error.message || "Не удалось изменить этап.",
        );
      })
      .finally(function () {
        setStageMoveDialogBusy(dialog, false);
      });
  });

  dialog
    .querySelectorAll("[data-stage-move-cancel]")
    .forEach(function (button) {
      button.addEventListener("click", function () {
        closeStageMoveDialog(dialog);
      });
    });

  // Нажатие Escape.
  dialog.addEventListener("cancel", function (event) {
    event.preventDefault();

    if (dialog.getAttribute("aria-busy") === "true") {
      return;
    }

    closeStageMoveDialog(dialog);
  });

  // Клик по затемнённой области за окном.
  dialog.addEventListener("click", function (event) {
    if (
      event.target === dialog &&
      dialog.getAttribute("aria-busy") !== "true"
    ) {
      closeStageMoveDialog(dialog);
    }
  });

  dialog.addEventListener("close", function () {
    pendingStageMove = null;
    resetStageMoveDialog(dialog);
  });
}

function attachDragHandlers(container) {
  const scrollBox = container.querySelector(".kanban-board");
  if (!scrollBox) return;

  container.querySelectorAll(".kanban-card").forEach(function (card) {
    card.addEventListener("pointerdown", function (event) {
      startPointerDrag(event, card, container, scrollBox);
    });
  });
}

function startPointerDrag(startEvent, card, container, scrollBox) {
  if (!startEvent.isPrimary || startEvent.button !== 0) return;

  if (
    startEvent.target.closest(
      "a, button, input, textarea, select",
    )
  ) {
    return;
  }

  const startX = startEvent.clientX;
  const startY = startEvent.clientY;
  const pointerId = startEvent.pointerId;

  let pointerX = startX;
  let pointerY = startY;
  let dragStarted = false;
  let ghost = null;
  let currentDropColumn = null;
  let autoscrollFrameId = null;
  let autoscrollSpeedPx = 0;

  try {
    card.setPointerCapture(pointerId);
  } catch (error) {
    // Pointer capture может быть недоступен в старом браузере.
  }

  function onPointerMove(event) {
    if (event.pointerId !== pointerId) return;

    pointerX = event.clientX;
    pointerY = event.clientY;

    const deltaX = pointerX - startX;
    const deltaY = pointerY - startY;

    if (!dragStarted) {
      if (
        Math.abs(deltaX) < DRAG_START_THRESHOLD_PX &&
        Math.abs(deltaY) < DRAG_START_THRESHOLD_PX
      ) {
        return;
      }

      dragStarted = true;
      card.classList.add("is-dragging");
      scrollBox.classList.add("is-dragging");
      ghost = createGhost(card);
    }

    event.preventDefault();
    positionGhost(ghost, pointerX, pointerY);
    updateAutoscrollSpeed();
    updateCurrentDropTarget();
  }

  function updateAutoscrollSpeed() {
    const rect = scrollBox.getBoundingClientRect();
    const maxScrollLeft = Math.max(0, scrollBox.scrollWidth - scrollBox.clientWidth);

    if (
      maxScrollLeft === 0 ||
      pointerY < rect.top ||
      pointerY > rect.bottom
    ) {
      stopAutoscroll();
      return;
    }

    const leftDistance = pointerX - rect.left;
    const rightDistance = rect.right - pointerX;
    let nextSpeed = 0;

    if (leftDistance >= 0 && leftDistance < AUTOSCROLL_ZONE_PX) {
      nextSpeed = -calculateAutoscrollSpeed(leftDistance);
    } else if (rightDistance >= 0 && rightDistance < AUTOSCROLL_ZONE_PX) {
      nextSpeed = calculateAutoscrollSpeed(rightDistance);
    }

    if (
      (nextSpeed < 0 && scrollBox.scrollLeft <= 0) ||
      (nextSpeed > 0 && scrollBox.scrollLeft >= maxScrollLeft - 1)
    ) {
      nextSpeed = 0;
    }

    autoscrollSpeedPx = nextSpeed;

    if (autoscrollSpeedPx === 0) {
      stopAutoscroll();
    } else {
      startAutoscroll();
    }
  }

  function calculateAutoscrollSpeed(distanceFromEdge) {
    const proximity = 1 - distanceFromEdge / AUTOSCROLL_ZONE_PX;

    return (
      AUTOSCROLL_MIN_SPEED_PX +
      proximity * (AUTOSCROLL_MAX_SPEED_PX - AUTOSCROLL_MIN_SPEED_PX)
    );
  }

  function startAutoscroll() {
    if (autoscrollFrameId !== null) return;

    function step() {
      if (!dragStarted || autoscrollSpeedPx === 0) {
        autoscrollFrameId = null;
        return;
      }

      const maxScrollLeft = Math.max(0, scrollBox.scrollWidth - scrollBox.clientWidth);
      const previousScrollLeft = scrollBox.scrollLeft;
      const nextScrollLeft = Math.max(
        0,
        Math.min(maxScrollLeft, previousScrollLeft + autoscrollSpeedPx)
      );

      scrollBox.scrollLeft = nextScrollLeft;

      // После движения доски под неподвижным курсором могла оказаться другая колонка.
      updateCurrentDropTarget();

      if (nextScrollLeft === previousScrollLeft) {
        autoscrollSpeedPx = 0;
        autoscrollFrameId = null;
        return;
      }

      autoscrollFrameId = requestAnimationFrame(step);
    }

    autoscrollFrameId = requestAnimationFrame(step);
  }

  function stopAutoscroll() {
    autoscrollSpeedPx = 0;

    if (autoscrollFrameId !== null) {
      cancelAnimationFrame(autoscrollFrameId);
      autoscrollFrameId = null;
    }
  }

  function updateCurrentDropTarget() {
    currentDropColumn = findDropColumn(pointerX, pointerY, ghost);

    clearDropTargetHighlight(container);
    if (currentDropColumn) {
      currentDropColumn.classList.add("is-drop-target");
    }
  }

function finishPointerDrag(event, shouldConfirmMove) {
  if (
    event &&
    "pointerId" in event &&
    event.pointerId !== pointerId
  ) {
    return;
  }

  document.removeEventListener(
    "pointermove",
    onPointerMove,
  );
  document.removeEventListener(
    "pointerup",
    onPointerUp,
  );
  document.removeEventListener(
    "pointercancel",
    onPointerCancel,
  );
  window.removeEventListener(
    "blur",
    onWindowBlur,
  );

  stopAutoscroll();

  card.classList.remove("is-dragging");
  scrollBox.classList.remove("is-dragging");

  try {
    if (card.hasPointerCapture(pointerId)) {
      card.releasePointerCapture(pointerId);
    }
  } catch (error) {
    // Браузер мог уже освободить pointer capture.
  }

  if (ghost) {
    ghost.remove();
  }

  clearDropTargetHighlight(container);

  if (
    !shouldConfirmMove ||
    !dragStarted ||
    !currentDropColumn
  ) {
    return;
  }

  openStageMoveDialog(
    card,
    currentDropColumn,
  );
}

function onPointerUp(event) {
  finishPointerDrag(event, true);
}

function onPointerCancel(event) {
  finishPointerDrag(event, false);
}

function onWindowBlur() {
  finishPointerDrag(null, false);
}

document.addEventListener(
  "pointermove",
  onPointerMove,
  { passive: false },
);
document.addEventListener(
  "pointerup",
  onPointerUp,
);
document.addEventListener(
  "pointercancel",
  onPointerCancel,
);
window.addEventListener(
  "blur",
  onWindowBlur,
);
}

function findDropColumn(pointerX, pointerY, ghost) {
  if (ghost) {
    ghost.style.display = "none";
  }

  const elementUnderPointer = document.elementFromPoint(
    pointerX,
    pointerY,
  );

  if (ghost) {
    ghost.style.display = "";
  }

  return elementUnderPointer
    ? elementUnderPointer.closest(".kanban-dropzone")
    : null;
}

function clearDropTargetHighlight(container) {
  container
    .querySelectorAll(
      ".kanban-dropzone.is-drop-target",
    )
    .forEach(function (element) {
      element.classList.remove("is-drop-target");
    });
}

function createGhost(card) {
  const rect = card.getBoundingClientRect();
  const ghost = card.cloneNode(true);
  ghost.classList.add("kanban-ghost-card");
  ghost.style.width = rect.width + "px";
  document.body.appendChild(ghost);
  positionGhost(ghost, rect.left + rect.width / 2, rect.top + rect.height / 2);
  return ghost;
}

function positionGhost(ghost, x, y) {
  ghost.style.left = x + "px";
  ghost.style.top = y + "px";
}

function openStageMoveDialog(card, dropZone) {
  const dialog = document.getElementById(
    "stage-move-dialog",
  );
  const summary = document.getElementById(
    "stage-move-summary",
  );
  const dateInput = document.getElementById(
    "stage-move-date",
  );
  const noteInput = document.getElementById(
    "stage-move-note",
  );

  if (
    !dialog ||
    !summary ||
    !dateInput ||
    !noteInput
  ) {
    showMoveError(
      "Не удалось открыть окно смены этапа.",
    );
    return;
  }

  const currentStageId =
    card.dataset.currentStageId;
  const targetStageId =
    dropZone.dataset.stageId;

  // Отпустили карточку в её же колонке.
  if (
    !targetStageId ||
    currentStageId === targetStageId
  ) {
    return;
  }

  const traineeName =
    card.dataset.traineeName || "Стажёр";
  const currentStageName =
    card.dataset.currentStageName || "Текущий этап";
  const targetStageName =
    dropZone.dataset.stageName || "Новый этап";
  const currentStageStartedAt =
    card.dataset.currentStageStartedAt;
  const defaultTransitionDate =
    dialog.dataset.defaultTransitionDate;

  pendingStageMove = {
    moveUrl: card.dataset.moveUrl,
    stageId: targetStageId,
  };

  summary.textContent =
    traineeName +
    ": " +
    currentStageName +
    " → " +
    targetStageName;

  // Нельзя выбрать дату раньше начала текущего этапа
  // или позже сегодняшнего дня.
  dateInput.min = currentStageStartedAt || "";
  dateInput.max = defaultTransitionDate || "";
  dateInput.value =
    defaultTransitionDate ||
    currentStageStartedAt ||
    "";

  noteInput.value = "";

  dialog.showModal();
  dateInput.focus();

  if (typeof lucide !== "undefined") {
    lucide.createIcons();
  }
}

function closeStageMoveDialog(dialog) {
  if (dialog.open) {
    dialog.close();
  }
}

function resetStageMoveDialog(dialog) {
  const form = document.getElementById(
    "stage-move-form",
  );
  const summary = document.getElementById(
    "stage-move-summary",
  );
  const dateInput = document.getElementById(
    "stage-move-date",
  );

  if (form) {
    form.reset();
  }

  if (summary) {
    summary.textContent =
      "Подтверди перевод стажёра на новый этап.";
  }

  if (dateInput) {
    dateInput.removeAttribute("min");
    dateInput.max =
      dialog.dataset.defaultTransitionDate || "";
  }
}

function setStageMoveDialogBusy(
  dialog,
  isBusy,
) {
  dialog.setAttribute(
    "aria-busy",
    String(isBusy),
  );

  dialog
    .querySelectorAll(
      "button, input, textarea",
    )
    .forEach(function (element) {
      element.disabled = isBusy;
    });
}

function moveTraineeStage(options) {
  return fetch(options.moveUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfCookie(),
    },
    body: JSON.stringify({
      stage_id: options.stageId,
      transition_date: options.transitionDate,
      note: options.note,
    }),
  }).then(function (response) {
    return response.text().then(function (text) {
      let data = {};

      if (text) {
        try {
          data = JSON.parse(text);
        } catch (error) {
          data = {};
        }
      }

      if (!response.ok) {
        throw new Error(
          data.error ||
          "Не удалось изменить этап.",
        );
      }

      return data;
    });
  });
}

function refreshKanbanBoard(container) {
  const refreshUrl =
    container.dataset.refreshUrl;
  const scrollBox =
    container.querySelector(".kanban-board");
  const scrollLeft =
    scrollBox ? scrollBox.scrollLeft : 0;

  if (!refreshUrl) {
    return Promise.reject(
      new Error(
        "Не указан адрес обновления доски.",
      ),
    );
  }

  return fetch(refreshUrl)
    .then(function (response) {
      if (!response.ok) {
        throw new Error(
          "Не удалось обновить доску. " +
          "Обнови страницу вручную.",
        );
      }

      return response.text();
    })
    .then(function (html) {
      container.innerHTML = html;

      // После замены HTML старые обработчики исчезли.
      attachDragHandlers(container);

      if (typeof lucide !== "undefined") {
        lucide.createIcons();
      }

      const newScrollBox =
        container.querySelector(".kanban-board");

      if (newScrollBox) {
        newScrollBox.scrollLeft = scrollLeft;
      }
    });
}

function getCsrfCookie() {
  const value = "; " + document.cookie;
  const parts = value.split("; csrftoken=");
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
  return "";
}

function showMoveError(message) {
  if (typeof toast === "function") {
    toast(message, "error");
  } else {
    alert(message);
  }
}

document.addEventListener("DOMContentLoaded", initKanban);
