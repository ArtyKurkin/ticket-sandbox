document.addEventListener(
  "DOMContentLoaded",
  () => {
    initQuestionEditor();
    initDynamicFormsets();
    initDiagnosticFormsets();
  }
);


function initQuestionEditor() {
  const editor = document.querySelector(
    "[data-question-editor]"
  );

  if (!editor) {
    return;
  }

  const typeSelect = editor.querySelector(
    "[name='answer_type']"
  );

  const sections = [
    ...editor.querySelectorAll(
      "[data-answer-editor]"
    ),
  ];

  if (!typeSelect) {
    return;
  }


  const updateEditors = () => {
    const selected = typeSelect.value;

    sections.forEach((section) => {
      const supportedTypes = (
        section.dataset.answerEditor
          .split(",")
      );

      const active = (
        supportedTypes.includes(
          selected
        )
      );

      section.hidden = !active;

      section
        .querySelectorAll(
          "input:not([type='hidden']), textarea, select"
        )
        .forEach((field) => {
          field.disabled = !active;
        });
    });
  };


  typeSelect.addEventListener(
    "change",
    updateEditors
  );

  updateEditors();
}


function initDynamicFormsets() {
  document
    .querySelectorAll("[data-formset]")
    .forEach((formset) => {
      initDynamicFormset(formset);
    });
}


function initDynamicFormset(formset) {
  const prefix = (
    formset.dataset.formsetPrefix
  );

  const rowsContainer = (
    formset.querySelector(
      "[data-formset-rows]"
    )
  );

  const template = (
    formset.querySelector(
      "template[data-empty-form]"
    )
  );

  const addButton = (
    formset.querySelector(
      "[data-add-form]"
    )
  );

  const totalForms = (
    formset.querySelector(
      `input[name="${prefix}-TOTAL_FORMS"]`
    )
  );

  if (
    !prefix
    || !rowsContainer
    || !template
    || !addButton
    || !totalForms
  ) {
    return;
  }


  const updateOrders = () => {
    let position = 1;

    rowsContainer
      .querySelectorAll("[data-form-row]")
      .forEach((row) => {
        const deleteInput = (
          row.querySelector(
            'input[name$="-DELETE"]'
          )
        );

        if (
          deleteInput
          && deleteInput.checked
        ) {
          return;
        }

        const orderInput = (
          row.querySelector(
            'input[name$="-order"]'
          )
        );

        if (orderInput) {
          orderInput.value = (
            position * 10
          );
        }

        position += 1;
      });
  };


  const updateDeleteButton = (
    row,
    deleted
  ) => {
    row.classList.toggle(
      "is-deleted",
      deleted
    );

    const button = row.querySelector(
      "[data-remove-form]"
    );

    if (!button) {
      return;
    }

    const label = button.querySelector(
      "span"
    );

    if (label) {
      label.textContent = (
        deleted
          ? "Вернуть"
          : "Удалить"
      );
    }
  };


  rowsContainer
    .querySelectorAll("[data-form-row]")
    .forEach((row) => {
      const deleteInput = (
        row.querySelector(
          'input[name$="-DELETE"]'
        )
      );

      if (
        deleteInput
        && deleteInput.checked
      ) {
        updateDeleteButton(
          row,
          true
        );
      }
    });


  addButton.addEventListener(
    "click",
    () => {
      const index = Number(
        totalForms.value
      );

      if (!Number.isFinite(index)) {
        return;
      }

      const html = (
        template.innerHTML.replaceAll(
          "__prefix__",
          String(index)
        )
      );

      rowsContainer.insertAdjacentHTML(
        "beforeend",
        html
      );

      totalForms.value = String(
        index + 1
      );

      updateOrders();

      if (
        window.lucide
        && window.lucide.createIcons
      ) {
        window.lucide.createIcons();
      }

      const rows = (
        rowsContainer.querySelectorAll(
          "[data-form-row]"
        )
      );

      const lastRow = rows[
        rows.length - 1
      ];

      const firstField = (
        lastRow?.querySelector(
          "input[type='text'], textarea, select"
        )
      );

      if (firstField) {
        firstField.focus();
      }
    }
  );


  rowsContainer.addEventListener(
    "click",
    (event) => {
      const button = (
        event.target.closest(
          "[data-remove-form]"
        )
      );

      if (!button) {
        return;
      }

      const row = button.closest(
        "[data-form-row]"
      );

      if (!row) {
        return;
      }

      const deleteInput = (
        row.querySelector(
          'input[name$="-DELETE"]'
        )
      );

      if (!deleteInput) {
        return;
      }

      deleteInput.checked = (
        !deleteInput.checked
      );

      updateDeleteButton(
        row,
        deleteInput.checked
      );

      updateOrders();
    }
  );


  const parentForm = formset.closest(
    "form"
  );

  if (parentForm) {
    parentForm.addEventListener(
      "submit",
      updateOrders
    );
  }


  updateOrders();
}

function initDiagnosticFormsets() {
  document
    .querySelectorAll(
      "[data-diagnostic-formset]"
    )
    .forEach((formset) => {
      initDiagnosticFormset(formset);
    });
}


function initDiagnosticFormset(formset) {
  const prefix = (
    formset.dataset.formsetPrefix
  );

  const rowsContainer = (
    formset.querySelector(
      "[data-diagnostic-rows]"
    )
  );

  const template = (
    formset.querySelector(
      "template[data-diagnostic-empty-form]"
    )
  );

  const totalForms = (
    formset.querySelector(
      `input[name="${prefix}-TOTAL_FORMS"]`
    )
  );

  if (
    !prefix
    || !rowsContainer
    || !template
    || !totalForms
  ) {
    return;
  }


  const syncRowType = (row) => {
    const typeInput = (
      row.querySelector(
        'input[name$="-block_type"]'
      )
    );

    const label = (
      row.querySelector(
        "[data-diagnostic-type-label]"
      )
    );

    const textarea = (
      row.querySelector("textarea")
    );

    if (!typeInput) {
      return;
    }

    const isCode = (
      typeInput.value === "code"
    );

    row.classList.toggle(
      "is-code",
      isCode
    );

    row.classList.toggle(
      "is-text",
      !isCode
    );

    if (label) {
      label.textContent = (
        isCode
          ? "Код / лог"
          : "Текст"
      );
    }

    if (textarea) {
      textarea.placeholder = (
        isCode
          ? "Вставь вывод команды, лог или конфигурацию..."
          : "Добавь пояснение к следующим диагностическим данным..."
      );
    }
  };


  const updateOrders = () => {
    let position = 1;

    rowsContainer
      .querySelectorAll(
        "[data-diagnostic-row]"
      )
      .forEach((row) => {
        const deleteInput = (
          row.querySelector(
            'input[name$="-DELETE"]'
          )
        );

        if (
          deleteInput
          && deleteInput.checked
        ) {
          return;
        }

        const orderInput = (
          row.querySelector(
            'input[name$="-order"]'
          )
        );

        if (orderInput) {
          orderInput.value = (
            position * 10
          );
        }

        position += 1;
      });
  };


  const updateDeleteState = (
    row,
    deleted
  ) => {
    row.classList.toggle(
      "is-deleted",
      deleted
    );

    const button = (
      row.querySelector(
        "[data-remove-diagnostic]"
      )
    );

    const label = (
      button?.querySelector("span")
    );

    if (label) {
      label.textContent = (
        deleted
          ? "Вернуть"
          : "Удалить"
      );
    }
  };


  rowsContainer
    .querySelectorAll(
      "[data-diagnostic-row]"
    )
    .forEach((row) => {
      syncRowType(row);

      const deleteInput = (
        row.querySelector(
          'input[name$="-DELETE"]'
        )
      );

      if (
        deleteInput
        && deleteInput.checked
      ) {
        updateDeleteState(
          row,
          true
        );
      }
    });


  formset.addEventListener(
    "click",
    (event) => {
      const addButton = (
        event.target.closest(
          "[data-add-diagnostic]"
        )
      );

      if (addButton) {
        const type = (
          addButton.dataset.addDiagnostic
        );

        const index = Number(
          totalForms.value
        );

        if (!Number.isFinite(index)) {
          return;
        }

        const html = (
          template.innerHTML.replaceAll(
            "__prefix__",
            String(index)
          )
        );

        rowsContainer.insertAdjacentHTML(
          "beforeend",
          html
        );

        totalForms.value = String(
          index + 1
        );

        const rows = (
          rowsContainer.querySelectorAll(
            "[data-diagnostic-row]"
          )
        );

        const row = (
          rows[rows.length - 1]
        );

        const typeInput = (
          row.querySelector(
            'input[name$="-block_type"]'
          )
        );

        if (typeInput) {
          typeInput.value = type;
        }

        syncRowType(row);
        updateOrders();

        if (
          window.lucide
          && window.lucide.createIcons
        ) {
          window.lucide.createIcons();
        }

        const textarea = (
          row.querySelector("textarea")
        );

        if (textarea) {
          textarea.focus();
        }

        return;
      }


      const removeButton = (
        event.target.closest(
          "[data-remove-diagnostic]"
        )
      );

      if (!removeButton) {
        return;
      }

      const row = (
        removeButton.closest(
          "[data-diagnostic-row]"
        )
      );

      if (!row) {
        return;
      }

      const deleteInput = (
        row.querySelector(
          'input[name$="-DELETE"]'
        )
      );

      if (!deleteInput) {
        return;
      }

      deleteInput.checked = (
        !deleteInput.checked
      );

      updateDeleteState(
        row,
        deleteInput.checked
      );

      updateOrders();
    }
  );


  const parentForm = (
    formset.closest("form")
  );

  if (parentForm) {
    parentForm.addEventListener(
      "submit",
      updateOrders
    );
  }

  updateOrders();
}