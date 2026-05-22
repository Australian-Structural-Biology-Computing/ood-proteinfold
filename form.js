(() => {
  const CONTEXT_PREFIX = "batch_connect_session_context";
  const COLABFOLD_ADVANCED_HIDE_TARGETS = [
    "colabfold_num_seeds",
    "colabfold_use_dropout",
    "colabfold_max_msa"
  ];
  const CHECKBOX_HIDE_RULES = {
    colabfold_advanced_options: {
      hideWhenChecked: new Set(),
      hideWhenUnchecked: new Set(COLABFOLD_ADVANCED_HIDE_TARGETS)
    },
  };

  const escapeForSelector = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return value.replace(/([ #;?%&,.+*~':"!^$\[\]()=>|/@])/g, "\\$1");
  };

  const parseTruthy = (value) => {
    if (value === null || value === undefined) return false;
    const normalized = String(value).trim().toLowerCase();
    return normalized === "" || normalized === "true" || normalized === "1" || normalized === "yes" || normalized === "on";
  };

  const hasHideAttribute = (element) =>
    Array.from(element.attributes).some((attribute) => attribute.name.startsWith("data-hide-"));

  const getOptionHideTargets = (option) => {
    const targets = new Set();
    if (!option) return targets;

    Array.from(option.attributes).forEach((attribute) => {
      if (!attribute.name.startsWith("data-hide-")) return;
      if (!parseTruthy(attribute.value)) return;
      const target = attribute.name.replace("data-hide-", "").trim();
      if (target) targets.add(target);
    });

    return targets;
  };

  const getAllHideTargetsForSelect = (select) => {
    const targets = new Set();
    Array.from(select.options).forEach((option) => {
      Array.from(option.attributes).forEach((attribute) => {
        if (!attribute.name.startsWith("data-hide-")) return;
        const target = attribute.name.replace("data-hide-", "").trim();
        if (target) targets.add(target);
      });
    });
    return targets;
  };

  const getFieldNameForControl = (element) => {
    if (!element) return "";

    const nameAttribute = element.getAttribute("name") || "";
    const contextMatch = nameAttribute.match(/\[([^\]]+)\]$/);
    if (contextMatch && contextMatch[1]) return contextMatch[1];

    const idAttribute = element.getAttribute("id") || "";
    const contextPrefix = `${CONTEXT_PREFIX}_`;
    if (idAttribute.startsWith(contextPrefix)) {
      return idAttribute.slice(contextPrefix.length).replace(/_id$/, "");
    }

    return idAttribute.replace(/_id$/, "");
  };

  const getFieldElements = (fieldName) => {
    const escaped = escapeForSelector(fieldName);
    const selectors = [
      `#${CONTEXT_PREFIX}_${escaped}`,
      `[name='${CONTEXT_PREFIX}[${fieldName}]']`,
      `#${escaped}`,
      `[name='${fieldName}']`
    ];

    const elements = selectors
      .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
      .filter((element, index, array) => array.indexOf(element) === index);

    if (elements.length > 0) return elements;

    const label = document.querySelector(`label[for$='_${escaped}'], label[for='${escaped}']`);
    if (!label) return [];
    const forId = label.getAttribute("for");
    if (!forId) return [];
    const fallback = document.getElementById(forId);
    return fallback ? [fallback] : [];
  };

  const getFieldContainer = (element) => {
    if (!element) return null;
    const container = element.closest(".form-group, .mb-3, .form-item");
    if (container) return container;

    const byLabel = document.querySelector(`label[for='${element.id}']`);
    if (byLabel) {
      const labelContainer = byLabel.closest(".form-group, .mb-3, .form-item");
      if (labelContainer) return labelContainer;
    }

    return element.parentElement;
  };

  const setFieldVisibility = (fieldName, hidden) => {
    const elements = getFieldElements(fieldName);
    elements.forEach((element) => {
      const container = getFieldContainer(element);
      const scope = container || element;
      const controls = [element, ...Array.from(scope.querySelectorAll("input, select, textarea"))]
        .filter((control, index, array) => array.indexOf(control) === index);

      if (container) {
        container.hidden = hidden;
        container.setAttribute("aria-hidden", hidden ? "true" : "false");
      }

      controls.forEach((control) => {
        if (hidden) {
          if (control.required) control.dataset.oodWasRequired = "1";
          if (control.disabled && control.dataset.oodHiddenDisabled !== "1") {
            control.dataset.oodWasDisabled = "1";
          }
          control.required = false;
          control.disabled = true;
          control.dataset.oodHiddenDisabled = "1";
        } else {
          if (control.dataset.oodWasRequired === "1") {
            control.required = true;
            delete control.dataset.oodWasRequired;
          }

          if (control.dataset.oodWasDisabled === "1") {
            delete control.dataset.oodWasDisabled;
          } else {
            control.disabled = false;
          }

          delete control.dataset.oodHiddenDisabled;
        }
      });
    });
  };

  const initDynamicHide = () => {
    const selectControllers = Array.from(document.querySelectorAll("select")).filter((select) =>
      Array.from(select.options).some(hasHideAttribute)
    );
    const checkboxControllers = Array.from(document.querySelectorAll("input[type='checkbox']")).filter((checkbox) => {
      const fieldName = getFieldNameForControl(checkbox);
      return Boolean(fieldName && CHECKBOX_HIDE_RULES[fieldName]);
    });
    const controllers = [...selectControllers, ...checkboxControllers];

    if (controllers.length === 0) return;

    const evaluate = () => {
      const fieldHiddenState = new Map();

      selectControllers.forEach((select) => {
        const allTargets = getAllHideTargetsForSelect(select);
        const selectedOption = select.selectedOptions && select.selectedOptions.length > 0
          ? select.selectedOptions[0]
          : select.options[select.selectedIndex];
        const selectedHiddenTargets = getOptionHideTargets(selectedOption);

        allTargets.forEach((target) => {
          const shouldHide = selectedHiddenTargets.has(target);
          const previous = fieldHiddenState.get(target) || false;
          fieldHiddenState.set(target, previous || shouldHide);
        });
      });

      checkboxControllers.forEach((checkbox) => {
        const fieldName = getFieldNameForControl(checkbox);
        const rules = CHECKBOX_HIDE_RULES[fieldName];
        if (!rules) return;

        const allTargets = new Set([...rules.hideWhenChecked, ...rules.hideWhenUnchecked]);
        const selectedHiddenTargets = checkbox.checked ? rules.hideWhenChecked : rules.hideWhenUnchecked;

        allTargets.forEach((target) => {
          const shouldHide = selectedHiddenTargets.has(target);
          const previous = fieldHiddenState.get(target) || false;
          fieldHiddenState.set(target, previous || shouldHide);
        });
      });

      fieldHiddenState.forEach((hidden, fieldName) => {
        setFieldVisibility(fieldName, hidden);
      });
    };

    controllers.forEach((controller) => {
      if (controller.dataset.oodHideBound === "1") return;
      controller.addEventListener("change", evaluate);
      controller.dataset.oodHideBound = "1";
    });

    evaluate();
  };

  document.addEventListener("DOMContentLoaded", initDynamicHide);
  document.addEventListener("turbo:load", initDynamicHide);
  document.addEventListener("page:load", initDynamicHide);

  const initSaveIntermediatesWarning = () => {
    const elements = getFieldElements('save_intermediates');
    if (!elements || elements.length === 0) return;

    let checkbox = null;
    for (const el of elements) {
      if (el.type === 'checkbox') { checkbox = el; break; }
      const cb = el.querySelector && el.querySelector("input[type='checkbox']");
      if (cb) { checkbox = cb; break; }
    }

    if (!checkbox) {
      const fallback = document.querySelector("input[name$='[save_intermediates]'], input[name='save_intermediates']");
      if (fallback && fallback.type === 'checkbox') checkbox = fallback;
    }

    if (!checkbox) return;

    const warning = document.getElementById(`${CONTEXT_PREFIX}_save_intermediates_warning`) || document.getElementById('save_intermediates_warning');
    if (!warning) return;

    const update = () => {
      if (checkbox.checked) warning.classList.remove('d-none');
      else warning.classList.add('d-none');
    };

    checkbox.addEventListener('change', update);
    update();
  };

  document.addEventListener("DOMContentLoaded", initSaveIntermediatesWarning);
  document.addEventListener("turbo:load", initSaveIntermediatesWarning);
  document.addEventListener("page:load", initSaveIntermediatesWarning);

  const initColabfoldAdvancedEnforce = () => {
    const advEls = getFieldElements('colabfold_advanced_options');
    if (!advEls || advEls.length === 0) return;

    let advCheckbox = null;
    for (const el of advEls) {
      if (el.type === 'checkbox') { advCheckbox = el; break; }
      const cb = el.querySelector && el.querySelector("input[type='checkbox']");
      if (cb) { advCheckbox = cb; break; }
    }
    if (!advCheckbox) return;

    const methodEls = getFieldElements('af_method');
    if (!methodEls || methodEls.length === 0) return;

    let methodControl = null;
    for (const el of methodEls) {
      if (el.tagName === 'SELECT') { methodControl = el; break; }
      if ((el.type === 'radio' || el.type === 'checkbox') && el.checked) { methodControl = el; break; }
      if (el.type !== 'radio' && el.type !== 'checkbox') { methodControl = el; break; }
    }
    if (!methodControl) return;

    const saveEls = getFieldElements('save_intermediates');
    if (!saveEls || saveEls.length === 0) return;

    let saveCheckbox = null;
    for (const el of saveEls) {
      if (el.type === 'checkbox') { saveCheckbox = el; break; }
      const cb = el.querySelector && el.querySelector("input[type='checkbox']");
      if (cb) { saveCheckbox = cb; break; }
    }
    if (!saveCheckbox) return;

    const enforcedNotice = document.getElementById('save_intermediates_enforced');

    const applyLock = () => {
      saveCheckbox.checked = true;
      saveCheckbox.disabled = true;
      if (enforcedNotice) enforcedNotice.classList.remove('d-none');
    };

    const releaseLock = () => {
      saveCheckbox.disabled = false;
      if (enforcedNotice) enforcedNotice.classList.add('d-none');
    };

    const evaluate = () => {
      const isColabfold = methodControl.value === 'colabfold';
      if (advCheckbox.checked && isColabfold) applyLock(); else releaseLock();
    };

    if (advCheckbox.dataset.oodEnforceBound !== '1') {
      advCheckbox.addEventListener('change', evaluate);
      advCheckbox.dataset.oodEnforceBound = '1';
    }

    if (methodControl.dataset.oodEnforceBound !== '1') {
      methodControl.addEventListener('change', evaluate);
      methodControl.dataset.oodEnforceBound = '1';
    }

    // run once to sync state
    evaluate();
  };

  document.addEventListener("DOMContentLoaded", initColabfoldAdvancedEnforce);
  document.addEventListener("turbo:load", initColabfoldAdvancedEnforce);
  document.addEventListener("page:load", initColabfoldAdvancedEnforce);
})();
