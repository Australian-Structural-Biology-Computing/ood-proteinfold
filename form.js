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
  const METHOD_TOKEN_LIMITS = {
    boltz: {
      title: "Boltz",
      limit: "5,000"
    },
    alphafold3: {
      title: "AlphaFold3",
      limit: "5,000",
    },
    alphafold2: {
      title: "AlphaFold2",
      limit: "4,000"
    },
    colabfold: {
      title: "ColabFold",
      limit: "4,000"
    },
    esmfold: {
      title: "ESMFold",
      limit: "600"
    }
  };

  const escapeForSelector = (value) => {
    if (window.CSS && typeof window.CSS.escape === "function") {
      return window.CSS.escape(value);
    }
    return value.replace(/([ #;?%&,.+*~':"!^$\[\]()=>|/@])/g, "\\$1");
  };

  const parseTruthy = (value) => {
    if (value === null || value === undefined) return false;
    const normalised = String(value).trim().toLowerCase();
    return normalised === "" || normalised === "true" || normalised === "1" || normalised === "yes" || normalised === "on";
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

  const getFieldControl = (fieldName, selector = "input, select, textarea") => {
    const elements = getFieldElements(fieldName);
    for (const element of elements) {
      if (element.matches && element.matches(selector)) return element;
      const nested = element.querySelector && element.querySelector(selector);
      if (nested) return nested;
    }
    return null;
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

  const getFieldLabel = (element) => {
    if (!element || !element.id) return null;
    return document.querySelector(`label[for='${element.id}']`);
  };

  const getFieldCheckbox = (fieldName) => getFieldControl(fieldName, "input[type='checkbox']");

  const isHelpSibling = (element) => {
    if (!element || element.nodeType !== Node.ELEMENT_NODE) return false;
    if (element.matches(".form-text, .help-block, .text-muted, small")) return true;

    const className = element.className || "";
    if (typeof className === "string" && /(help|hint|description|text-muted)/i.test(className)) {
      return true;
    }

    return !element.querySelector("input, select, textarea, label");
  };

  const getVisibilityTargets = (element) => {
    const targets = [];
    const container = getFieldContainer(element);
    if (container) targets.push(container);

    const label = getFieldLabel(element);
    if (label) {
      targets.push(label);

      let sibling = label.nextElementSibling;
      while (sibling && isHelpSibling(sibling)) {
        targets.push(sibling);
        sibling = sibling.nextElementSibling;
      }
    }

    if (container) {
      let sibling = container.nextElementSibling;
      while (sibling && isHelpSibling(sibling)) {
        targets.push(sibling);
        sibling = sibling.nextElementSibling;
      }
    }

    return Array.from(new Set(targets));
  };

  const setFieldVisibility = (fieldName, hidden) => {
    const elements = getFieldElements(fieldName);
    const pathSelectorId = `${CONTEXT_PREFIX}_${fieldName}_path_selector`;
    const pathSelectorModal = document.getElementById(pathSelectorId);
    const pathSelectorButton = document.querySelector(`[data-bs-target='#${pathSelectorId}']`) ||
      document.querySelector(`[data-target='#${pathSelectorId}']`);
    const pathSelectorWrappers = [
      pathSelectorButton ? pathSelectorButton.closest(".form-group, .mb-3, .form-item, .control-group") : null,
      pathSelectorModal ? pathSelectorModal.closest(".form-group, .mb-3, .form-item, .control-group") : null
    ].filter((element, index, array) => element && array.indexOf(element) === index);

    elements.forEach((element) => {
      const container = getFieldContainer(element);
      const scope = container || element;
      const controls = [element, ...Array.from(scope.querySelectorAll("input, select, textarea"))]
        .filter((control, index, array) => array.indexOf(control) === index);

      getVisibilityTargets(element).forEach((target) => {
        target.hidden = hidden;
        target.setAttribute("aria-hidden", hidden ? "true" : "false");
      });

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

    pathSelectorWrappers.forEach((wrapper) => {
      wrapper.hidden = hidden;
      wrapper.setAttribute("aria-hidden", hidden ? "true" : "false");
      wrapper.classList.toggle("d-none", hidden);
    });

    if (pathSelectorButton) pathSelectorButton.disabled = hidden;
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

      const methodControl = getFieldControl("af_method", "select");
      const advancedCheckbox = getFieldCheckbox("colabfold_advanced_options");
      const showAdvancedColabfoldOptions =
        methodControl &&
        methodControl.value === "colabfold" &&
        advancedCheckbox &&
        advancedCheckbox.checked;

      COLABFOLD_ADVANCED_HIDE_TARGETS.forEach((target) => {
        const previous = fieldHiddenState.get(target) || false;
        fieldHiddenState.set(target, previous || !showAdvancedColabfoldOptions);
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

  const initMethodTokenLimitPanel = () => {
    const methodControl = getFieldControl("af_method", "select");
    if (!methodControl) return;

    const container = getFieldContainer(methodControl);
    if (!container) return;

    let panel = document.getElementById("af_method_token_limits_panel");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "af_method_token_limits_panel";
      panel.className = "alert alert-info mt-2";
      panel.setAttribute("role", "status");
      panel.setAttribute("aria-live", "polite");
      container.insertAdjacentElement("afterend", panel);
    }

    const update = () => {
      const info = METHOD_TOKEN_LIMITS[methodControl.value];
      if (!info) {
        panel.hidden = true;
        panel.innerHTML = "";
        return;
      }

      const noteHtml = info.note ? `<div>${info.note}</div>` : "";
      panel.innerHTML = `
        ${info.title} approximate length limit: <strong>${info.limit}</strong>
        ${noteHtml}
      `;
      panel.hidden = false;
    };

    if (methodControl.dataset.oodTokenPanelBound !== "1") {
      methodControl.addEventListener("change", update);
      methodControl.dataset.oodTokenPanelBound = "1";
    }

    update();
  };

  document.addEventListener("DOMContentLoaded", initMethodTokenLimitPanel);
  document.addEventListener("turbo:load", initMethodTokenLimitPanel);
  document.addEventListener("page:load", initMethodTokenLimitPanel);

  const initSaveIntermediatesWarning = () => {
    const checkbox = getFieldCheckbox('save_intermediates');
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
    const advCheckbox = getFieldCheckbox('colabfold_advanced_options');
    if (!advCheckbox) return;

    const methodControl = getFieldControl('af_method', 'select');
    if (!methodControl) return;

    const saveCheckbox = getFieldCheckbox('save_intermediates');
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
