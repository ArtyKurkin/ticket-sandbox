document.addEventListener("DOMContentLoaded", () => {
  initQuestionTimer();
  initOrdering();
});


function initQuestionTimer() {
  const timer = document.querySelector(
    "[data-question-timer]"
  );

  const form = document.querySelector(
    "[data-question-form]"
  );

  if (!timer || !form) {
    return;
  }

  const value = timer.querySelector(
    "[data-timer-value]"
  );

  const initialMs = Number(
    timer.dataset.remainingMs
  );

  if (!Number.isFinite(initialMs)) {
    return;
  }

  const startedAt = performance.now();

  let submitted = false;

  form.addEventListener("submit", () => {
    submitted = true;
  });

  const render = () => {
    const elapsed = (
      performance.now() - startedAt
    );

    const remaining = Math.max(
      0,
      initialMs - elapsed
    );

    const totalSeconds = Math.ceil(
      remaining / 1000
    );

    const minutes = Math.floor(
      totalSeconds / 60
    );

    const seconds = (
      totalSeconds % 60
    );

    value.textContent = (
      String(minutes).padStart(2, "0")
      + ":"
      + String(seconds).padStart(2, "0")
    );

    timer.classList.toggle(
      "is-warning",
      totalSeconds <= 30
      && totalSeconds > 10
    );

    timer.classList.toggle(
      "is-danger",
      totalSeconds <= 10
    );

    if (
      remaining <= 0
      && !submitted
    ) {
      submitted = true;

      value.textContent = "00:00";

      window.setTimeout(() => {
        form.requestSubmit();
      }, 150);
    }
  };

  render();

  const interval = window.setInterval(
    () => {
      render();

      if (submitted) {
        window.clearInterval(interval);
      }
    },
    250
  );
}


function initOrdering() {
  const list = document.querySelector(
    "[data-ordering-list]"
  );

  if (!list) {
    return;
  }

  let draggedItem = null;


  const updateNumbers = () => {
    const items = list.querySelectorAll(
      "[data-ordering-item]"
    );

    items.forEach((item, index) => {
      const number = item.querySelector(
        "[data-order-number]"
      );

      if (number) {
        number.textContent = String(
          index + 1
        );
      }
    });
  };


  const getDragAfterElement = (
    container,
    y
  ) => {
    const elements = [
      ...container.querySelectorAll(
        "[data-ordering-item]:not(.is-dragging)"
      ),
    ];

    return elements.reduce(
      (closest, child) => {
        const box = (
          child.getBoundingClientRect()
        );

        const offset = (
          y
          - box.top
          - box.height / 2
        );

        if (
          offset < 0
          && offset > closest.offset
        ) {
          return {
            offset,
            element: child,
          };
        }

        return closest;
      },
      {
        offset: Number.NEGATIVE_INFINITY,
        element: null,
      }
    ).element;
  };


  list.querySelectorAll(
    "[data-ordering-item]"
  ).forEach((item) => {

    item.addEventListener(
      "dragstart",
      () => {
        draggedItem = item;

        item.classList.add(
          "is-dragging"
        );
      }
    );

    item.addEventListener(
      "dragend",
      () => {
        item.classList.remove(
          "is-dragging"
        );

        draggedItem = null;

        updateNumbers();
      }
    );
  });


  list.addEventListener(
    "dragover",
    (event) => {
      event.preventDefault();

      if (!draggedItem) {
        return;
      }

      const afterElement = (
        getDragAfterElement(
          list,
          event.clientY
        )
      );

      if (afterElement === null) {
        list.appendChild(
          draggedItem
        );
      } else {
        list.insertBefore(
          draggedItem,
          afterElement
        );
      }
    }
  );


  list.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest(
        "[data-move]"
      );

      if (!button) {
        return;
      }

      const item = button.closest(
        "[data-ordering-item]"
      );

      if (!item) {
        return;
      }

      if (
        button.dataset.move === "up"
        && item.previousElementSibling
      ) {
        list.insertBefore(
          item,
          item.previousElementSibling
        );
      }

      if (
        button.dataset.move === "down"
        && item.nextElementSibling
      ) {
        list.insertBefore(
          item.nextElementSibling,
          item
        );
      }

      updateNumbers();
    }
  );


  updateNumbers();
}