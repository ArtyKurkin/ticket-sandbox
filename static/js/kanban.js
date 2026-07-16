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

function initKanban() {
  const container = document.getElementById("kanban-board-container");
  if (!container) return;
  attachDragHandlers(container);
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

  const journeyId = card.dataset.journeyId;
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

    if (maxScrollLeft === 0) {
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

  function finishPointerDrag(event) {
    if (event && "pointerId" in event && event.pointerId !== pointerId) return;

    document.removeEventListener("pointermove", onPointerMove);
    document.removeEventListener("pointerup", finishPointerDrag);
    document.removeEventListener("pointercancel", finishPointerDrag);
    window.removeEventListener("blur", finishPointerDrag);

    stopAutoscroll();
    card.classList.remove("is-dragging");
    scrollBox.classList.remove("is-dragging");

    try {
      if (card.hasPointerCapture(pointerId)) {
        card.releasePointerCapture(pointerId);
      }
    } catch (error) {
      // Ничего не делаем, если браузер уже освободил pointer capture.
    }

    if (ghost) {
      ghost.remove();
    }

    clearDropTargetHighlight(container);

    if (!dragStarted || !currentDropColumn) {
      return;
    }

    const stageId = currentDropColumn.dataset.stageId;
    moveTraineeStage(journeyId, stageId, container);
  }

  document.addEventListener("pointermove", onPointerMove, { passive: false });
  document.addEventListener("pointerup", finishPointerDrag);
  document.addEventListener("pointercancel", finishPointerDrag);
  window.addEventListener("blur", finishPointerDrag);
}

function findDropColumn(pointerX, pointerY, ghost) {
  if (ghost) {
    ghost.style.display = "none";
  }

  const elementUnderPointer = document.elementFromPoint(pointerX, pointerY);

  if (ghost) {
    ghost.style.display = "";
  }

  return elementUnderPointer
    ? elementUnderPointer.closest(".kanban-column-body")
    : null;
}

function clearDropTargetHighlight(container) {
  container.querySelectorAll(".kanban-column-body.is-drop-target").forEach(function (element) {
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

function moveTraineeStage(journeyId, stageId, container) {
  fetch("/diary/trainees/" + journeyId + "/move/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfCookie(),
    },
    body: JSON.stringify({ stage_id: stageId }),
  })
    .then(function (response) {
      return response.json().then(function (data) {
        return { status: response.status, data: data };
      });
    })
    .then(function (result) {
      if (result.status === 200) {
        refreshKanbanBoard(container);
      } else {
        showMoveError(result.data.error || "Не удалось изменить этап.");
      }
    })
    .catch(function () {
      showMoveError("Ошибка соединения с сервером.");
    });
}

function refreshKanbanBoard(container) {
  const scrollBox = container.querySelector(".kanban-board");
  const scrollLeft = scrollBox ? scrollBox.scrollLeft : 0;

  fetch("/diary/trainees/board-fragment/")
    .then(function (response) {
      return response.text();
    })
    .then(function (html) {
      container.innerHTML = html;
      attachDragHandlers(container);

      if (typeof lucide !== "undefined") {
        lucide.createIcons();
      }

      const newScrollBox = container.querySelector(".kanban-board");
      if (newScrollBox) {
        newScrollBox.scrollLeft = scrollLeft;
      }
    })
    .catch(function () {
      showMoveError("Не удалось обновить доску. Обнови страницу вручную.");
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
