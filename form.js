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
    if (!input) return;

    const urlTemplate = "/pun/sys/dashboard/files/fs/__PATH_SEGMENTS__";
    const fieldContainer = getFieldContainer(input);
    let marker = document.getElementById("ood-proteinfold-input-warning");
    let summary = document.getElementById("ood-proteinfold-input-warning-summary");

    if (!marker) {
      marker = document.createElement("button");
      marker.id = "ood-proteinfold-input-warning";
      marker.type = "button";
      marker.textContent = "!";
      marker.hidden = true;
      marker.setAttribute("aria-label", "Input warnings");
      marker.style.cssText = "margin-left: 0.5rem; border: 0; border-radius: 50%; width: 1.4rem; height: 1.4rem; padding: 0; background: #ffc107; color: #212529; font-weight: 700; cursor: help;";
      input.insertAdjacentElement("afterend", marker);
    }

    if (!summary) {
      summary = document.createElement("div");
      summary.id = "ood-proteinfold-input-warning-summary";
      summary.hidden = true;
      summary.className = "alert alert-warning";
      summary.setAttribute("role", "alert");
      summary.style.marginTop = "0.5rem";
      marker.insertAdjacentElement("afterend", summary);
    }

    const buildFilesUrl = (path) => {
      const withoutLeadingSlash = path.replace(/^\/+/, "");
      const segments = withoutLeadingSlash
        .split("/")
        .filter(Boolean)
        .map(encodeURIComponent)
        .join("/");
      return urlTemplate.replace(/__PATH_SEGMENTS__/g, segments);
    };

    const isFastaPath = (path) => /\.fa(?:sta)?$/i.test(path);
    const isYamlPath = (path) => /\.ya?ml$/i.test(path);
    const isCsvPath = (path) => /\.csv$/i.test(path);
    const isDirectInputPath = (path) =>
      isFastaPath(path) || isYamlPath(path) || isCsvPath(path);
    const getInputKind = (path) => {
      if (isFastaPath(path)) return "fasta";
      if (isYamlPath(path)) return "yaml";
      if (isCsvPath(path)) return "csv";
      return null;
    };
    const isSymbolicLink = (mode) => {
      const values = [Number(mode)];
      if (typeof mode === "string" && /^[0-7]+$/.test(mode)) {
        values.push(Number.parseInt(mode, 8));
      }
      return values.some((value) => (value & 0o170000) === 0o120000);
    };
    const inferEntityType = (header, sequence) => {
      const proteinAlphabet = "ACDEFGHIKLMNPQRSTVWYX";
      const isSubsetOf = (value, alphabet) =>
        [...value].every((character) => alphabet.includes(character));
      const taggedEntityType = header?.toLowerCase().split("|")[1];
      if (ENTITY_TYPES.has(taggedEntityType)) return taggedEntityType;
      if (sequence.includes(":")) {
        return sequence.split(":").every(
          (chain) => chain && isSubsetOf(chain, proteinAlphabet)
        )
          ? "protein"
          : "unknown";
      }
      if (isSubsetOf(sequence, "ACUGN")) return "rna";
      if (isSubsetOf(sequence, "ACTGN")) return "dna";
      if (
        isSubsetOf(sequence, proteinAlphabet) &&
        !isSubsetOf(sequence, "ACUGTN")
      ) return "protein";
      if (/^[A-Za-z0-9@+\-\[\]()=#$%]+$/.test(sequence)) return "smiles";
      return "unknown";
    };
    const validateEntitySequence = (entityType, sequence, label) => {
      const patterns = {
        dna: /^[ACTGN]+$/,
        rna: /^[ACUGN]+$/,
        smiles: /^[A-Za-z0-9@+\-\[\]()=#$%]+$/
      };
      if (entityType === "protein") {
        const invalidResidues = [...new Set(sequence.replace(/:/g, ""))]
          .filter((residue) => !AMINO_ACID_SEQUENCE_PATTERN.test(residue))
          .sort()
          .join("");
        if (
          sequence.split(":").some((chain) => !chain) ||
          invalidResidues
        ) {
          throw new Error(
            `${label} contains invalid amino acid character(s): ${invalidResidues || ":"}.`
          );
        }
      } else if (patterns[entityType] && !patterns[entityType].test(sequence)) {
        throw new Error(`${label} contains invalid ${entityType} characters.`);
      }
    };

    const parseFasta = (contents, label) => {
      const records = [];
      let sequence = "";
      let hasHeader = false;
      let blankLines = 0;
      let trailingBlankLines = 0;
      let normalisedHeaders = 0;
      let normalisedSequenceLines = 0;
      let normalisedLineEndings = 0;
      let removedSequenceWhitespace = 0;
      let removedTerminalStops = 0;
      let addedHeader = "";
      let header = null;
      const linePattern = /([^\r\n]*)(\r\n|\r|\n|$)/g;
      const normaliseRecord = (record, recordHeader) => {
        let normalisedRecord = record;
        const chains = normalisedRecord.split(":");
        const strippedRecord = chains
          .map((chain) => (chain.endsWith("*") ? chain.slice(0, -1) : chain))
          .join(":");
        if (strippedRecord && inferEntityType(recordHeader, strippedRecord) === "protein") {
          removedTerminalStops += chains.filter((chain) => chain.endsWith("*")).length;
          normalisedRecord = strippedRecord;
        }
        if (!normalisedRecord) {
          throw new Error(`${label} has a FASTA record with no sequence.`);
        }
        const entityType = inferEntityType(recordHeader, normalisedRecord);
        if (entityType === "unknown") {
          throw new Error(`${label} contains an unsupported entity sequence.`);
        }
        validateEntitySequence(entityType, normalisedRecord, label);
        return { sequence: normalisedRecord, entityType };
      };

      while (linePattern.lastIndex < contents.length) {
        const match = linePattern.exec(contents);
        if (!match) break;
        const rawText = match[1];
        const ending = match[2];
        const rawLine = `${rawText}${ending}`;
        if (ending === "\r\n" || ending === "\r") normalisedLineEndings += 1;
        const line = rawLine.trim();
        if (!line) {
          blankLines += 1;
          trailingBlankLines += 1;
          continue;
        }
        trailingBlankLines = 0;
        if (line.startsWith(">")) {
          if (hasHeader && !sequence) {
            throw new Error(`${label} has a FASTA record with no sequence.`);
          }
          if (!line.slice(1).trim()) {
            throw new Error(`${label} has an empty FASTA header.`);
          }
          if (hasHeader) records.push(normaliseRecord(sequence, header));
          if (rawLine !== `>${line.slice(1).trim()}\n`) normalisedHeaders += 1;
          hasHeader = true;
          header = line.slice(1).trim();
          sequence = "";
          continue;
        }
        const normalisedSequence = rawLine.replace(/[\s\uFEFF\u200B]/gu, "");
        if (normalisedSequence) {
          if (!hasHeader) {
            addedHeader = normalisedSequence.slice(0, HEADERLESS_SEQUENCE_ID_LENGTH);
            hasHeader = true;
            header = null;
            sequence = "";
          }
          if (rawLine !== `${normalisedSequence}\n`) {
            normalisedSequenceLines += 1;
            removedSequenceWhitespace += rawText.length - normalisedSequence.length;
          }
          sequence += normalisedSequence;
        }
      }

      if (!hasHeader) throw new Error(`${label} has no FASTA header.`);
      if (!sequence) throw new Error(`${label} has a final FASTA record with no sequence.`);
      records.push(normaliseRecord(sequence, header));
      blankLines -= trailingBlankLines;
      const changes = [];
      if (blankLines) changes.push(`remove ${blankLines} blank line(s)`);
      if (normalisedLineEndings) changes.push(`standardise line endings in ${normalisedLineEndings} line(s)`);
      if (normalisedHeaders) changes.push(`tidy ${normalisedHeaders} FASTA header(s)`);
      if (addedHeader) changes.push(`add FASTA header ${addedHeader}`);
      if (removedTerminalStops) {
        changes.push(`remove terminal stop codon from ${removedTerminalStops} FASTA record(s)`);
      }
      if (normalisedSequenceLines) {
        const characterCount = removedSequenceWhitespace
          ? ` (${removedSequenceWhitespace} whitespace character(s))`
          : "";
        changes.push(`remove whitespace from ${normalisedSequenceLines} sequence line(s)${characterCount}`);
      }
      return {
        sequenceKey: JSON.stringify(records.map((record) => record.sequence)),
        sequenceLength: records.reduce((total, record) => total + record.sequence.length, 0),
        entityTypes: [...new Set(records.map((record) => record.entityType))],
        changes
      };
    };

    const setWarnings = (warnings, checked = false, needsAttention = false, requiresReview = false) => {
      const message = warnings.join("\n");
      marker.hidden = warnings.length === 0 && !checked;
      marker.textContent = warnings.length ? "!" : "\u2713";
      marker.style.fontSize = "1rem";
      marker.title = message || "Input checked; no sanitisation is required.";
      marker.setAttribute("aria-label", message || "Input checked; no sanitisation is required.");
      marker.style.background = needsAttention ? "#dc3545" : (warnings.length ? "#ffc107" : "#198754");
      marker.style.color = warnings.length && !needsAttention ? "#212529" : "#ffffff";
      summary.hidden = warnings.length === 0;
      summary.className = needsAttention ? "alert alert-danger" : "alert alert-warning";
      summary.replaceChildren();
      if (warnings.length) {
        const heading = document.createElement("strong");
        heading.textContent = needsAttention
          ? "Input needs attention before the run"
          : (requiresReview ? "Review input before the run" : "Input will be adjusted before the run");
        const list = document.createElement("ul");
        list.style.margin = "0.5rem 0 0";
        warnings.forEach((warning) => {
          const item = document.createElement("li");
          item.textContent = warning;
          list.appendChild(item);
        });
        summary.append(heading, list);
      }
      if (fieldContainer) fieldContainer.classList.toggle("has-warning", warnings.length > 0 && !needsAttention);
      if (fieldContainer) fieldContainer.classList.toggle("has-error", needsAttention);
    };

    const setChecking = () => {
      marker.hidden = false;
      marker.textContent = "...";
      marker.title = "Checking input";
      marker.setAttribute("aria-label", "Checking input");
      marker.style.background = "#6c757d";
      marker.style.color = "#ffffff";
      marker.style.fontSize = "0.7rem";
      summary.hidden = false;
      summary.className = "alert alert-info";
      summary.replaceChildren("Checking input...");
    };

    const methodControl = getFieldControl("af_method", "select");
    const stripTerminalStops = (sequence) =>
      sequence
        .split(":")
        .map((chain) => (chain.endsWith("*") ? chain.slice(0, -1) : chain))
        .join(":");
    const normaliseManualSequence = (value) =>
      stripTerminalStops(value.replace(/[\s\uFEFF\u200B]/gu, ""));
    const isManualSequence = (sequence) =>
      sequence.split(":").every((chain) => AMINO_ACID_SEQUENCE_PATTERN.test(chain));
    const getManualSequenceWarnings = (value) => {
      const removableCharacters = value.match(/[\s\uFEFF\u200B]/gu) || [];
      const sequence = normaliseManualSequence(value);
      const terminalStops = value
        .replace(/[\s\uFEFF\u200B]/gu, "")
        .split(":")
        .filter((chain) => chain.endsWith("*")).length;
      if (!sequence) return [];
      if (!isManualSequence(sequence)) {
        return ["Enter a valid amino-acid sequence or an absolute input path."];
      }
      const limit = METHOD_TOKEN_LIMITS[methodControl?.value];
      const sequenceLength = sequence.replace(/:/g, "").length;
      const warnings = [];
      if (removableCharacters.length) {
        warnings.push(
          `Manual sequence: remove ${removableCharacters.length} whitespace character(s).`
        );
      }
      if (terminalStops) {
        warnings.push(
          `Manual sequence: remove terminal stop codon from ${terminalStops} chain(s).`
        );
      }
      if (limit && sequenceLength > limit.limit) {
        warnings.push(
          `Manual sequence length ${sequenceLength.toLocaleString()} residues exceeds the ${limit.title} approximate limit of ${limit.limit.toLocaleString()}.`
        );
      }
      return warnings;
    };
    const unsupportedEntityTypes = (file) =>
      (file.entityTypes || []).filter(
        (entityType) =>
          entityType !== "protein" &&
          !NON_PROTEIN_METHODS.has(methodControl?.value)
      );
    const getFileSeverity = (file, limit) => {
      if (file.error) return "error";
      if (unsupportedEntityTypes(file).length) {
        return file.directoryInput ? "review" : "error";
      }
      if (
        file.kind === "yaml" &&
        methodControl?.value !== "boltz"
      ) {
        return file.ignoredForMethod ? "review" : "error";
      }
      if (
        file.symbolicLink ||
        file.ignoredForMethod ||
        (limit && file.sequenceLength > limit.limit)
      ) {
        return "review";
      }
      return "none";
    };
    const getCheckedFilesState = (checkedFiles) => {
      const limit = METHOD_TOKEN_LIMITS[methodControl?.value];
      let needsAttention = false;
      let requiresReview = false;
      checkedFiles.forEach((file) => {
        const severity = getFileSeverity(file, limit);
        needsAttention ||= severity === "error";
        requiresReview ||= severity === "review";
      });
      return { needsAttention, requiresReview };
    };
    const buildWarnings = (checkedFiles) => {
      const limit = METHOD_TOKEN_LIMITS[methodControl?.value];
      const seen = new Map();
      return checkedFiles.flatMap((file) => {
        if (file.ignoredForMethod) {
          return [`${file.label}: YAML input will be ignored unless Boltz is selected.`];
        }
        if (file.symbolicLink) {
          return [`${file.label}: symbolic link; its target will be followed when the run starts.`];
        }
        if (file.kind === "yaml") {
          return methodControl?.value === "boltz"
            ? []
            : [`${file.label}: YAML input is only supported by Boltz.`];
        }
        if (file.kind === "csv") return [];
        if (file.error) return [file.error];
        const unsupportedTypes = unsupportedEntityTypes(file);
        if (unsupportedTypes.length) {
          return [
            file.directoryInput
              ? `${file.label}: ${unsupportedTypes.join(", ")} input will be ignored unless AlphaFold3 or Boltz is selected.`
              : `${file.label}: ${unsupportedTypes.join(", ")} input is only supported by AlphaFold3 or Boltz.`
          ];
        }
        const original = seen.get(file.sequenceKey);
        if (original) {
          return [`${file.label}: duplicate sequence of ${original}; this file will be skipped.`];
        }
        seen.set(file.sequenceKey, file.label);
        const fileWarnings = file.changes.length
          ? [`${file.label}: ${file.changes.join(", ")}.`]
          : [];
        if (limit && file.sequenceLength > limit.limit) {
          fileWarnings.push(
            `${file.label}: total sequence length ${file.sequenceLength.toLocaleString()} residues exceeds the ${limit.title} approximate limit of ${limit.limit.toLocaleString()}.`
          );
        }
        return fileWarnings;
      });
    };
    const getDirectoryFiles = async (directoryPath, directoryUrl, signal) => {
      const response = await fetch(directoryUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal
      });
      if (!response.ok) throw new Error(`Could not list ${directoryPath} (${response.status}).`);

      const listing = await response.json();
      return (listing.files || [])
        .filter((file) => file.type === "f" && file.url)
        .map((file) => ({
          url: file.url,
          label: file.name,
          kind: getInputKind(file.name),
          symbolicLink: file.symlink === true || file.symbolic_link === true || isSymbolicLink(file.mode)
        }))
        .sort((left, right) => (left.label < right.label ? -1 : left.label > right.label ? 1 : 0));
    };

    const getDirectInputFile = async (path, signal) => {
      const separator = path.lastIndexOf("/");
      const directoryPath = separator === 0 ? "/" : path.slice(0, separator);
      const fileName = path.slice(separator + 1);
      const files = await getDirectoryFiles(
        directoryPath,
        buildFilesUrl(directoryPath),
        signal
      );
      const file = files.find((candidate) => candidate.label === fileName);
      if (!file) throw new Error(`File not found: ${path}`);
      return file;
    };

    const mapWithConcurrency = async (items, limit, callback) => {
      const results = Array(items.length);
      let nextIndex = 0;
      const worker = async () => {
        while (nextIndex < items.length) {
          const index = nextIndex;
          nextIndex += 1;
          results[index] = await callback(items[index]);
        }
      };
      await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
      return results;
    };

    let requestNumber = 0;
    let preflightTimer = null;
    let lastCheckedPath = null;
    let lastWarnings = null;
    let lastNeedsAttention = false;
    let lastRequiresReview = false;
    let lastCheckedFiles = null;
    let activeController = null;
    const preflight = async (forceRefresh = false) => {
      const request = ++requestNumber;
      const controller = new AbortController();
      activeController = controller;
      const rawInput = input.value;
      const path = rawInput.trim();
      if (!path.startsWith("/")) {
        const sequence = normaliseManualSequence(rawInput);
        lastCheckedPath = rawInput;
        lastWarnings = getManualSequenceWarnings(rawInput);
        lastNeedsAttention = Boolean(sequence) && !isManualSequence(sequence);
        lastRequiresReview = lastWarnings.length > 0 && !lastNeedsAttention;
        lastCheckedFiles = null;
        setWarnings(
          lastWarnings,
          Boolean(sequence),
          lastNeedsAttention,
          lastRequiresReview
        );
        return;
      }
      if (!forceRefresh && path === lastCheckedPath && lastWarnings !== null) {
        if (lastCheckedFiles) {
          lastWarnings = buildWarnings(lastCheckedFiles);
          const state = getCheckedFilesState(lastCheckedFiles);
          lastNeedsAttention = state.needsAttention;
          lastRequiresReview = state.requiresReview;
        }
        setWarnings(lastWarnings, true, lastNeedsAttention, lastRequiresReview);
        return;
      }

      try {
        const filesUrl = buildFilesUrl(path);
        const directInput = isDirectInputPath(path);
        const directoryFiles = directInput
          ? []
          : await getDirectoryFiles(path, filesUrl, controller.signal);
        const files = directInput
          ? [await getDirectInputFile(path, controller.signal)]
          : directoryFiles.filter((file) =>
            file.kind === "fasta" ||
            (file.kind === "yaml" && methodControl?.value === "boltz")
          );
        files.forEach((file) => {
          file.directoryInput = !directInput;
        });
        const ignoredYamlFiles = methodControl?.value === "boltz"
          ? []
          : directoryFiles
            .filter((file) => file.kind === "yaml")
            .map((file) => ({ ...file, ignoredForMethod: true }));
        if (request !== requestNumber) return;
        if (!files.length) {
          const yamlFiles = directoryFiles.filter((file) => file.kind === "yaml");
          const expectedInputs = methodControl?.value === "boltz"
            ? "FASTA or YAML input files"
            : "FASTA files (.fa or .fasta)";
          const warnings = yamlFiles.length && methodControl?.value !== "boltz"
            ? yamlFiles.map((file) => `${file.label}: YAML input is only supported by Boltz.`)
            : [`No compatible ${expectedInputs} were found in this directory.`];
          lastCheckedPath = path;
          lastWarnings = warnings;
          lastNeedsAttention = true;
          lastRequiresReview = false;
          lastCheckedFiles = yamlFiles.length ? yamlFiles : null;
          setWarnings(warnings, yamlFiles.length > 0, true);
          return;
        }

        const checkedFiles = await mapWithConcurrency(files, 6, async (file) => {
          if (file.kind !== "fasta") return file;
          if (file.symbolicLink) return { ...file, symbolicLink: true };
          try {
            const response = await fetch(file.url, {
              credentials: "same-origin",
              signal: controller.signal
            });
            if (!response.ok) throw new Error(`Could not read ${file.label} (${response.status}).`);
            return { ...file, ...parseFasta(await response.text(), file.label) };
          } catch (error) {
            if (error.name === "AbortError") throw error;
            return { ...file, error: error.message };
          }
        });
        if (request !== requestNumber) return;
        checkedFiles.push(...ignoredYamlFiles);

        const warnings = buildWarnings(checkedFiles);
        lastCheckedPath = path;
        lastWarnings = warnings;
        const state = getCheckedFilesState(checkedFiles);
        lastNeedsAttention = state.needsAttention;
        lastRequiresReview = state.requiresReview;
        lastCheckedFiles = checkedFiles;
        setWarnings(warnings, true, lastNeedsAttention, lastRequiresReview);
      } catch (error) {
        if (error.name === "AbortError") return;
        if (request !== requestNumber) return;
        const warnings = [`Could not check this input: ${error.message}`];
        lastCheckedPath = path;
        lastWarnings = warnings;
        lastNeedsAttention = true;
        lastRequiresReview = false;
        lastCheckedFiles = null;
        setWarnings(warnings, false, true);
      }
    };

    const schedulePreflight = (forceRefresh = false) => {
      requestNumber += 1;
      if (activeController) activeController.abort();
      if (preflightTimer) window.clearTimeout(preflightTimer);
      setChecking();
      preflightTimer = window.setTimeout(() => preflight(forceRefresh), 250);
    };

    if (input.dataset.oodInputPreflightBound !== "1") {
      input.addEventListener("input", () => schedulePreflight(true));
      input.dataset.oodInputPreflightBound = "1";
    }
    if (methodControl && methodControl.dataset.oodInputLengthBound !== "1") {
      methodControl.addEventListener("change", () => {
        const currentPath = input.value.trim();
        const isDirectoryPath =
          currentPath.startsWith("/") && !isDirectInputPath(currentPath);
        if (isDirectoryPath) {
          schedulePreflight(true);
        } else if (lastCheckedFiles) {
          lastWarnings = buildWarnings(lastCheckedFiles);
          const state = getCheckedFilesState(lastCheckedFiles);
          lastNeedsAttention = state.needsAttention;
          lastRequiresReview = state.requiresReview;
          setWarnings(lastWarnings, true, lastNeedsAttention, lastRequiresReview);
        } else {
          schedulePreflight();
        }
      });
      methodControl.dataset.oodInputLengthBound = "1";
    }

    if (input.value.trim() && input.dataset.oodInputPreflightInitialised !== "1") {
      input.dataset.oodInputPreflightInitialised = "1";
      schedulePreflight();
    }
  };

  document.addEventListener("DOMContentLoaded", initInputPreflight);
  document.addEventListener("turbo:load", initInputPreflight);
  document.addEventListener("page:load", initInputPreflight);
})();
