document.addEventListener(
  "DOMContentLoaded",
  () => {
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
);