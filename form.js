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
  const HEADERLESS_SEQUENCE_ID_LENGTH = 6;
  const AMINO_ACID_SEQUENCE_PATTERN = /^[ACDEFGHIKLMNPQRSTVWYX]+$/;
  const ENTITY_TYPES = new Set(["protein", "ccd", "smiles", "dna", "rna"]);
  const NON_PROTEIN_METHODS = new Set(["alphafold3", "boltz"]);
  const METHOD_TOKEN_LIMITS = {
    boltz: {
      title: "Boltz",
      limit: 5000
    },
    alphafold3: {
      title: "AlphaFold3",
      limit: 5000,
    },
    alphafold2: {
      title: "AlphaFold2",
      limit: 4000
    },
    colabfold: {
      title: "ColabFold",
      limit: 4000
    },
    esmfold: {
      title: "ESMFold",
      limit: 600
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
        ${info.title} approximate length limit: <strong>${info.limit.toLocaleString()}</strong>
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

  const initInputPreflight = () => {
    const input = getFieldControl("samplesheet");
    if (!input || input.dataset.oodInputPreflightBound === "1") return;
    input.dataset.oodInputPreflightBound = "1";

    const methodControl = getFieldControl("af_method", "select");
    const fieldContainer = getFieldContainer(input);
    const fileKinds = [
      [/\.fa(?:sta)?$/i, "fasta"],
      [/\.ya?ml$/i, "yaml"],
      [/\.csv$/i, "csv"]
    ];
    const boltzEntityTypes = new Set(["protein", "dna", "rna", "ligand"]);
    const entityPatterns = {
      dna: /^[ACTGN]+$/,
      rna: /^[ACUGN]+$/,
      smiles: /^[A-Za-z0-9@+\-\[\]()=#$%]+$/
    };
    const severityOrder = { pass: 0, adjustment: 1, review: 2, error: 3 };
    let marker = document.getElementById("ood-proteinfold-input-warning");
    let summary = document.getElementById("ood-proteinfold-input-warning-summary");

    if (!marker) {
      marker = document.createElement("button");
      marker.id = "ood-proteinfold-input-warning";
      marker.type = "button";
      marker.hidden = true;
      marker.setAttribute("aria-label", "Input warnings");
      marker.style.cssText = "margin-left: 0.5rem; border: 0; border-radius: 50%; width: 1.4rem; height: 1.4rem; padding: 0; background: #ffc107; color: #212529; font-weight: 700; cursor: help;";
      input.insertAdjacentElement("afterend", marker);
    }
    if (!summary) {
      summary = document.createElement("div");
      summary.id = "ood-proteinfold-input-warning-summary";
      summary.hidden = true;
      summary.setAttribute("role", "alert");
      summary.style.marginTop = "0.5rem";
      marker.insertAdjacentElement("afterend", summary);
    }

    const getInputKind = (path) =>
      fileKinds.find(([pattern]) => pattern.test(path))?.[1] || null;
    const removeWhitespace = (value) =>
      value.replace(/[\s\uFEFF\u200B]/gu, "");
    const stripTerminalStops = (sequence) =>
      sequence
        .split(":")
        .map((chain) => (chain.endsWith("*") ? chain.slice(0, -1) : chain))
        .join(":");
    const isSubsetOf = (value, alphabet) =>
      [...value].every((character) => alphabet.includes(character));
    const increaseSeverity = (current, candidate) =>
      severityOrder[candidate] > severityOrder[current] ? candidate : current;
    const errorResult = (message) => ({ messages: [message], severity: "error" });

    const render = ({ messages = [], severity = "pass", checked = true }) => {
      const message = messages.join("\n");
      const hasWarnings = messages.length > 0;
      const needsAttention = severity === "error";
      marker.hidden = !checked && !hasWarnings;
      marker.textContent = hasWarnings ? "!" : "\u2713";
      marker.style.fontSize = "1rem";
      marker.title = message || "Input checked; no sanitisation is required.";
      marker.setAttribute("aria-label", marker.title);
      marker.style.background = needsAttention
        ? "#dc3545"
        : (hasWarnings ? "#ffc107" : "#198754");
      marker.style.color = hasWarnings && !needsAttention ? "#212529" : "#ffffff";
      summary.hidden = !hasWarnings;
      summary.className = needsAttention ? "alert alert-danger" : "alert alert-warning";
      summary.replaceChildren();
      if (hasWarnings) {
        const heading = document.createElement("strong");
        heading.textContent = needsAttention
          ? "Input needs attention before the run"
          : (severity === "review"
              ? "Review input before the run"
              : "Input will be adjusted before the run");
        const list = document.createElement("ul");
        list.style.margin = "0.5rem 0 0";
        messages.forEach((warning) => {
          const item = document.createElement("li");
          item.textContent = warning;
          list.appendChild(item);
        });
        summary.append(heading, list);
      }
      fieldContainer?.classList.toggle("has-warning", hasWarnings && !needsAttention);
      fieldContainer?.classList.toggle("has-error", needsAttention);
    };

    const renderChecking = () => {
      marker.hidden = false;
      marker.textContent = "...";
      marker.title = "Checking input";
      marker.setAttribute("aria-label", marker.title);
      marker.style.background = "#6c757d";
      marker.style.color = "#ffffff";
      marker.style.fontSize = "0.7rem";
      summary.hidden = false;
      summary.className = "alert alert-info";
      summary.replaceChildren("Checking input...");
    };

    const parseSamplesheet = (contents) => {
      const rows = [];
      let row = [];
      let field = "";
      let quoted = false;
      for (let index = 0; index < contents.length; index += 1) {
        const character = contents[index];
        if (character === "\"") {
          if (quoted && contents[index + 1] === "\"") {
            field += "\"";
            index += 1;
          } else {
            quoted = !quoted;
          }
        } else if (character === "," && !quoted) {
          row.push(field);
          field = "";
        } else if (/[\r\n]/.test(character) && !quoted) {
          if (character === "\r" && contents[index + 1] === "\n") index += 1;
          row.push(field);
          if (row.some((value) => value.trim())) rows.push(row);
          row = [];
          field = "";
        } else {
          field += character;
        }
      }
      if (quoted) throw new Error("Samplesheet contains an unterminated quoted field.");
      row.push(field);
      if (row.some((value) => value.trim())) rows.push(row);
      const header = rows.shift() || [];
      if (header.slice(0, 2).map((value) => value.trim()).join(",") !== "id,fasta") {
        throw new Error("Samplesheet must start with the required columns: id,fasta.");
      }
      return rows.map((values, index) => {
        const path = (values[1] || "").trim();
        if (!path) throw new Error(`Samplesheet row ${index + 2} is missing an input path.`);
        return { path, rowNumber: index + 2 };
      });
    };

    const resolveSamplesheetPath = (samplesheetPath, referencedPath) => {
      const parts = referencedPath.startsWith("/")
        ? []
        : samplesheetPath.slice(0, samplesheetPath.lastIndexOf("/")).split("/");
      referencedPath.split("/").forEach((part) => {
        if (part === "..") parts.pop();
        else if (part && part !== ".") parts.push(part);
      });
      return `/${parts.filter(Boolean).join("/")}`;
    };

    const validateBoltzYaml = (contents, label) => {
      const entries = [];
      let sequencesIndent = null;
      let entryIndent = null;
      let currentEntry = null;
      contents.split(/\r\n|\r|\n/).forEach((rawLine) => {
        const line = rawLine.replace(/\s+#.*$/, "");
        if (!line.trim()) return;
        const indent = line.length - line.trimStart().length;
        if (/^sequences:\s*$/.test(line)) {
          sequencesIndent = indent;
          entryIndent = null;
          currentEntry = null;
        } else if (sequencesIndent !== null && indent <= sequencesIndent) {
          sequencesIndent = null;
          currentEntry = null;
        } else if (sequencesIndent !== null) {
          const entity = line.trim().match(/^-\s+([^:]+):\s*$/);
          const field = line.trim().match(/^(id|sequence|smiles|ccd):\s*(.+)$/);
          if (entity && (entryIndent === null || indent === entryIndent)) {
            entryIndent ??= indent;
            currentEntry = { type: entity[1], fields: {} };
            entries.push(currentEntry);
          } else if (currentEntry && field) {
            currentEntry.fields[field[1]] = field[2].trim();
          }
        }
      });
      if (!entries.length) {
        throw new Error(`${label} must contain a non-empty sequences list.`);
      }
      entries.forEach(({ type, fields }, index) => {
        const entry = `${label} ${type} entry ${index + 1}`;
        if (!boltzEntityTypes.has(type)) {
          throw new Error(`${label} has unsupported Boltz entity type: ${type}.`);
        }
        if (!fields.id || fields.id === "[]") {
          throw new Error(`${entry} is missing id.`);
        }
        if (["protein", "dna", "rna"].includes(type) && !fields.sequence) {
          throw new Error(`${entry} is missing sequence.`);
        }
        if (type === "ligand" && Boolean(fields.smiles) === Boolean(fields.ccd)) {
          throw new Error(`${entry} must contain exactly one of smiles or ccd.`);
        }
      });
    };

    const inferEntityType = (header, sequence) => {
      const proteinAlphabet = "ACDEFGHIKLMNPQRSTVWYX";
      const taggedType = header?.toLowerCase().split("|")[1];
      if (ENTITY_TYPES.has(taggedType)) return taggedType;
      if (sequence.includes(":")) {
        return sequence.split(":").every(
          (chain) => chain && isSubsetOf(chain, proteinAlphabet)
        ) ? "protein" : "unknown";
      }
      if (isSubsetOf(sequence, "ACUGN")) return "rna";
      if (isSubsetOf(sequence, "ACTGN")) return "dna";
      if (
        isSubsetOf(sequence, proteinAlphabet) &&
        !isSubsetOf(sequence, "ACUGTN")
      ) return "protein";
      return entityPatterns.smiles.test(sequence) ? "smiles" : "unknown";
    };

    const validateEntitySequence = (entityType, sequence, label) => {
      if (entityType === "protein") {
        const invalidResidues = [...new Set(sequence.replace(/:/g, ""))]
          .filter((residue) => !AMINO_ACID_SEQUENCE_PATTERN.test(residue))
          .sort()
          .join("");
        if (sequence.split(":").some((chain) => !chain) || invalidResidues) {
          throw new Error(
            `${label} contains invalid amino acid character(s): ${invalidResidues || ":"}.`
          );
        }
      } else if (entityPatterns[entityType] && !entityPatterns[entityType].test(sequence)) {
        throw new Error(`${label} contains invalid ${entityType} characters.`);
      }
    };

    const parseFasta = (contents, label) => {
      const records = [];
      const changes = {
        blankLines: 0,
        trailingBlankLines: 0,
        headers: 0,
        sequenceLines: 0,
        lineEndings: 0,
        whitespace: 0,
        terminalStops: 0,
        addedHeader: ""
      };
      let header = null;
      let sequence = "";
      let hasRecord = false;

      const finishRecord = () => {
        const chains = sequence.split(":");
        const withoutStops = stripTerminalStops(sequence);
        if (withoutStops && inferEntityType(header, withoutStops) === "protein") {
          changes.terminalStops += chains.filter((chain) => chain.endsWith("*")).length;
          sequence = withoutStops;
        }
        if (!sequence) throw new Error(`${label} has a FASTA record with no sequence.`);
        const entityType = inferEntityType(header, sequence);
        if (entityType === "unknown") {
          throw new Error(`${label} contains an unsupported entity sequence.`);
        }
        validateEntitySequence(entityType, sequence, label);
        records.push({ sequence, entityType });
      };

      for (const match of contents.matchAll(/([^\r\n]*)(\r\n|\r|\n|$)/g)) {
        if (!match[0]) continue;
        const [, rawText, ending] = match;
        if (ending === "\r\n" || ending === "\r") changes.lineEndings += 1;
        const line = rawText.trim();
        if (!line) {
          changes.blankLines += 1;
          changes.trailingBlankLines += 1;
          continue;
        }
        changes.trailingBlankLines = 0;
        if (line.startsWith(">")) {
          if (hasRecord) finishRecord();
          header = line.slice(1).trim();
          if (!header) throw new Error(`${label} has an empty FASTA header.`);
          if (rawText !== `>${header}`) changes.headers += 1;
          sequence = "";
          hasRecord = true;
          continue;
        }

        const normalisedLine = removeWhitespace(rawText);
        if (!normalisedLine) continue;
        if (!hasRecord) {
          changes.addedHeader = normalisedLine.slice(0, HEADERLESS_SEQUENCE_ID_LENGTH);
          header = null;
          hasRecord = true;
        }
        if (rawText !== normalisedLine) {
          changes.sequenceLines += 1;
          changes.whitespace += rawText.length - normalisedLine.length;
        }
        sequence += normalisedLine;
      }

      if (!hasRecord) throw new Error(`${label} has no FASTA header.`);
      finishRecord();
      const warnings = [];
      const internalBlankLines = changes.blankLines - changes.trailingBlankLines;
      if (internalBlankLines) warnings.push(`remove ${internalBlankLines} blank line(s)`);
      if (changes.lineEndings) {
        warnings.push(`standardise line endings in ${changes.lineEndings} line(s)`);
      }
      if (changes.headers) warnings.push(`tidy ${changes.headers} FASTA header(s)`);
      if (changes.addedHeader) warnings.push(`add FASTA header ${changes.addedHeader}`);
      if (changes.terminalStops) {
        warnings.push(
          `remove terminal stop codon from ${changes.terminalStops} FASTA record(s)`
        );
      }
      if (changes.sequenceLines) {
        const count = changes.whitespace
          ? ` (${changes.whitespace} whitespace character(s))`
          : "";
        warnings.push(`remove whitespace from ${changes.sequenceLines} sequence line(s)${count}`);
      }
      return {
        sequenceKey: JSON.stringify(records.map((record) => record.sequence)),
        sequenceLength: records.reduce((total, record) => total + record.sequence.length, 0),
        entityTypes: [...new Set(records.map((record) => record.entityType))],
        hasUnknownProteinResidue: records.some(
          (record) => record.entityType === "protein" && record.sequence.includes("X")
        ),
        changes: warnings
      };
    };

    const analyseManualInput = (value) => {
      const whitespace = value.match(/[\s\uFEFF\u200B]/gu) || [];
      const compact = removeWhitespace(value);
      const terminalStops = compact.split(":").filter((chain) => chain.endsWith("*")).length;
      const sequence = stripTerminalStops(compact);
      if (!sequence) return { checked: false };
      if (!sequence.split(":").every((chain) => AMINO_ACID_SEQUENCE_PATTERN.test(chain))) {
        return errorResult("Enter a valid amino-acid sequence or an absolute input path.");
      }
      if (methodControl?.value === "alphafold2" && sequence.includes("X")) {
        return errorResult("AlphaFold2 cannot run sequences containing X.");
      }

      const messages = [];
      if (whitespace.length) {
        messages.push(`Manual sequence: remove ${whitespace.length} whitespace character(s).`);
      }
      if (terminalStops) {
        messages.push(`Manual sequence: remove terminal stop codon from ${terminalStops} chain(s).`);
      }
      const limit = METHOD_TOKEN_LIMITS[methodControl?.value];
      const length = sequence.replace(/:/g, "").length;
      if (limit && length > limit.limit) {
        messages.push(
          `Manual sequence length ${length.toLocaleString()} residues exceeds the ${limit.title} approximate limit of ${limit.limit.toLocaleString()}.`
        );
      }
      return { messages, severity: messages.length ? "review" : "pass" };
    };

    const unsupportedEntityTypes = (file) =>
      (file.entityTypes || []).filter(
        (type) => type !== "protein" && !NON_PROTEIN_METHODS.has(methodControl?.value)
      );

    const analyseFiles = (files) => {
      const messages = [];
      const seen = new Map();
      const limit = METHOD_TOKEN_LIMITS[methodControl?.value];
      const collection = files.some((file) => file.collectionInput);
      let runnableInputs = 0;
      let severity = "pass";
      const add = (message, candidate = "adjustment") => {
        messages.push(message);
        severity = increaseSeverity(severity, candidate);
      };

      files.forEach((file) => {
        if (file.ignoredForMethod) {
          add(`${file.label}: YAML input will be ignored unless Boltz is selected.`, "review");
          return;
        }
        if (file.symbolicLink) {
          runnableInputs += 1;
          add(
            `${file.label}: symbolic link; its target will be followed when the run starts.`,
            "review"
          );
          return;
        }
        if (file.error) {
          add(file.error, "error");
          return;
        }
        if (file.kind === "yaml") {
          if (methodControl?.value === "boltz") {
            runnableInputs += 1;
          } else {
            add(`${file.label}: YAML input is only supported by Boltz.`, "error");
          }
          return;
        }
        if (methodControl?.value === "alphafold2" && file.hasUnknownProteinResidue) {
          add(
            file.collectionInput
              ? `${file.label}: contains X; this file will be ignored while AlphaFold2 is selected.`
              : `${file.label}: AlphaFold2 cannot run sequences containing X.`,
            file.collectionInput ? "review" : "error"
          );
          return;
        }

        const unsupportedTypes = unsupportedEntityTypes(file);
        if (unsupportedTypes.length) {
          add(
            file.collectionInput
              ? `${file.label}: ${unsupportedTypes.join(", ")} input will be ignored unless AlphaFold3 or Boltz is selected.`
              : `${file.label}: ${unsupportedTypes.join(", ")} input is only supported by AlphaFold3 or Boltz.`,
            file.collectionInput ? "review" : "error"
          );
          return;
        }
        runnableInputs += 1;
        const original = seen.get(file.sequenceKey);
        if (original) {
          add(`${file.label}: duplicate sequence of ${original}; this file will be skipped.`);
          return;
        }
        seen.set(file.sequenceKey, file.label);
        if (file.changes.length) add(`${file.label}: ${file.changes.join(", ")}.`);
        if (limit && file.sequenceLength > limit.limit) {
          add(
            `${file.label}: total sequence length ${file.sequenceLength.toLocaleString()} residues exceeds the ${limit.title} approximate limit of ${limit.limit.toLocaleString()}.`,
            "review"
          );
        }
      });
      if (collection && !runnableInputs) severity = "error";
      return { messages, severity };
    };

    const isSymbolicLink = (mode) => {
      const values = [Number(mode)];
      if (typeof mode === "string" && /^[0-7]+$/.test(mode)) {
        values.push(Number.parseInt(mode, 8));
      }
      return values.some((value) => (value & 0o170000) === 0o120000);
    };
    const buildFilesUrl = (path) => {
      const segments = path
        .replace(/^\/+/, "")
        .split("/")
        .filter(Boolean)
        .map(encodeURIComponent)
        .join("/");
      return `/pun/sys/dashboard/files/fs/${segments}`;
    };
    const getDirectoryFiles = async (path, signal, cache) => {
      if (cache.has(path)) return cache.get(path);
      const request = fetch(buildFilesUrl(path), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal
      }).then(async (response) => {
        if (!response.ok) throw new Error(`Could not list ${path} (${response.status}).`);
        const listing = await response.json();
        return (listing.files || [])
          .filter((file) => file.type === "f" && file.url)
          .map((file) => ({
            url: file.url,
            label: file.name,
            kind: getInputKind(file.name),
            symbolicLink:
              file.symlink === true ||
              file.symbolic_link === true ||
              isSymbolicLink(file.mode)
          }))
          .sort((left, right) => left.label.localeCompare(right.label));
      });
      cache.set(path, request);
      return request;
    };
    const getDirectInputFile = async (path, signal, cache) => {
      const separator = path.lastIndexOf("/");
      const directory = separator === 0 ? "/" : path.slice(0, separator);
      const name = path.slice(separator + 1);
      const file = (await getDirectoryFiles(directory, signal, cache))
        .find((candidate) => candidate.label === name);
      if (!file) throw new Error(`File not found: ${path}`);
      return file;
    };
    const fetchText = async (file, signal) => {
      const response = await fetch(file.url, { credentials: "same-origin", signal });
      if (!response.ok) throw new Error(`Could not read ${file.label} (${response.status}).`);
      return response.text();
    };
    const prepareCollection = (files) =>
      files
        .filter((file) => file.kind === "fasta" || file.kind === "yaml")
        .map((file) => ({
          ...file,
          collectionInput: true,
          ignoredForMethod: file.kind === "yaml" && methodControl?.value !== "boltz"
        }));
    const mapWithConcurrency = async (items, callback, limit = 6) => {
      const results = Array(items.length);
      let nextIndex = 0;
      const worker = async () => {
        while (nextIndex < items.length) {
          const index = nextIndex++;
          results[index] = await callback(items[index]);
        }
      };
      await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
      return results;
    };

    const loadInputFiles = async (path, signal) => {
      const cache = new Map();
      const kind = getInputKind(path);
      if (!kind) return prepareCollection(await getDirectoryFiles(path, signal, cache));

      const selected = await getDirectInputFile(path, signal, cache);
      if (kind !== "csv") return [selected];
      const rows = parseSamplesheet(await fetchText(selected, signal));
      return prepareCollection(await mapWithConcurrency(rows, async (row) => {
        const referencedPath = resolveSamplesheetPath(path, row.path);
        const file = await getDirectInputFile(referencedPath, signal, cache);
        if (file.kind !== "fasta" && file.kind !== "yaml") {
          throw new Error(
            `Samplesheet row ${row.rowNumber} has unsupported input type: ${row.path}.`
          );
        }
        return { ...file, label: `${file.label} (samplesheet row ${row.rowNumber})` };
      }));
    };

    const checkFile = async (file, signal) => {
      if (file.ignoredForMethod || file.symbolicLink) return file;
      try {
        const contents = await fetchText(file, signal);
        if (file.kind === "yaml") {
          validateBoltzYaml(contents, file.label);
          return file;
        }
        return { ...file, ...parseFasta(contents, file.label) };
      } catch (error) {
        if (error.name === "AbortError") throw error;
        return { ...file, error: error.message };
      }
    };

    let requestNumber = 0;
    let preflightTimer = null;
    let activeController = null;
    let lastCheckedFiles = null;

    const preflight = async (request, controller) => {
      const rawInput = input.value;
      const path = rawInput.trim();
      if (!path.startsWith("/")) {
        lastCheckedFiles = null;
        render(analyseManualInput(rawInput));
        return;
      }

      try {
        const files = await loadInputFiles(path, controller.signal);
        if (request !== requestNumber) return;
        if (!files.length) {
          const expected = methodControl?.value === "boltz"
            ? "FASTA or YAML input files"
            : "FASTA files (.fa or .fasta)";
          lastCheckedFiles = null;
          render(errorResult(`No compatible ${expected} were found in this input.`));
          return;
        }
        const checkedFiles = await mapWithConcurrency(
          files,
          (file) => checkFile(file, controller.signal)
        );
        if (request !== requestNumber) return;
        lastCheckedFiles = checkedFiles;
        render(analyseFiles(checkedFiles));
      } catch (error) {
        if (error.name === "AbortError" || request !== requestNumber) return;
        lastCheckedFiles = null;
        render(errorResult(`Could not check this input: ${error.message}`));
      }
    };

    const schedulePreflight = () => {
      const request = ++requestNumber;
      activeController?.abort();
      if (preflightTimer) window.clearTimeout(preflightTimer);
      const controller = new AbortController();
      activeController = controller;
      renderChecking();
      preflightTimer = window.setTimeout(
        () => preflight(request, controller),
        250
      );
    };

    input.addEventListener("input", schedulePreflight);
    if (methodControl && methodControl.dataset.oodInputLengthBound !== "1") {
      methodControl.addEventListener("change", () => {
        const path = input.value.trim();
        const kind = getInputKind(path);
        if (path.startsWith("/") && (!kind || kind === "csv")) {
          schedulePreflight();
        } else if (lastCheckedFiles) {
          render(analyseFiles(lastCheckedFiles));
        } else {
          schedulePreflight();
        }
      });
      methodControl.dataset.oodInputLengthBound = "1";
    }
    if (input.value.trim()) schedulePreflight();
  };

  document.addEventListener("DOMContentLoaded", initInputPreflight);
  document.addEventListener("turbo:load", initInputPreflight);
  document.addEventListener("page:load", initInputPreflight);
})();
