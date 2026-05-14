const HTML_ESCAPE = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

const ESCAPED_CHAR = {
  "&": "&amp;",
  "%": "%",
  "$": "$",
  "#": "#",
  "_": "_",
  "{": "{",
  "}": "}",
  "~": "~",
  "^": "^",
  "\\": "\\",
};

const SYMBOLS = {
  alpha: "α",
  beta: "β",
  gamma: "γ",
  delta: "δ",
  epsilon: "ε",
  varepsilon: "ε",
  zeta: "ζ",
  eta: "η",
  theta: "θ",
  vartheta: "ϑ",
  iota: "ι",
  kappa: "κ",
  lambda: "λ",
  mu: "μ",
  nu: "ν",
  xi: "ξ",
  pi: "π",
  rho: "ρ",
  sigma: "σ",
  tau: "τ",
  upsilon: "υ",
  phi: "φ",
  varphi: "φ",
  chi: "χ",
  psi: "ψ",
  omega: "ω",
  Gamma: "Γ",
  Delta: "Δ",
  Theta: "Θ",
  Lambda: "Λ",
  Xi: "Ξ",
  Pi: "Π",
  Sigma: "Σ",
  Phi: "Φ",
  Psi: "Ψ",
  Omega: "Ω",
  times: "×",
  cdot: "·",
  pm: "±",
  mp: "∓",
  leq: "≤",
  geq: "≥",
  neq: "≠",
  approx: "≈",
  sim: "∼",
  infty: "∞",
  to: "→",
  rightarrow: "→",
  leftarrow: "←",
  leftrightarrow: "↔",
  mapsto: "↦",
  forall: "∀",
  exists: "∃",
  in: "∈",
  notin: "∉",
  subset: "⊂",
  subseteq: "⊆",
  cup: "∪",
  cap: "∩",
  emptyset: "∅",
  degree: "°",
  circ: "°",
  textbackslash: "\\",
  LaTeX: "LaTeX",
};

const TEXT_WRAPPERS = {
  texttt: "latex-mono",
  textsf: "latex-sans",
  textsc: "latex-smallcaps",
  emph: "latex-italic",
  textit: "latex-italic",
  textbf: "latex-bold",
  underline: "latex-underline",
};

const TRANSPARENT_COMMANDS = new Set([
  "textrm",
  "textnormal",
  "text",
  "mathrm",
  "mathbf",
  "mathit",
  "mathsf",
  "mathtt",
  "operatorname",
  "mbox",
]);

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => HTML_ESCAPE[char]);
}

function collapseWhitespace(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();
}

function findBalancedBrace(text, openIndex) {
  let depth = 0;
  for (let index = openIndex; index < text.length; index += 1) {
    const char = text[index];
    if (char === "\\" && index + 1 < text.length) {
      index += 1;
      continue;
    }
    if (char === "{") depth += 1;
    if (char === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  return -1;
}

function readAtom(text, index, mode) {
  if (text[index] === "{") {
    const close = findBalancedBrace(text, index);
    if (close !== -1) {
      return {
        value: renderLatexSegment(text.slice(index + 1, close), mode),
        next: close + 1,
      };
    }
  }
  return {
    value: renderLatexSegment(text[index] || "", mode),
    next: index + 1,
  };
}

function wrapCommand(command, inner, mode) {
  if (command === "texttt" || (mode === "math" && command === "mathtt")) {
    return `<code class="latex-mono">${inner}</code>`;
  }
  if (command === "textsc") return `<span class="${TEXT_WRAPPERS[command]}">${inner}</span>`;
  if (command === "emph" || command === "textit" || (mode === "math" && command === "mathit")) {
    return `<em>${inner}</em>`;
  }
  if (command === "textbf" || (mode === "math" && command === "mathbf")) {
    return `<strong>${inner}</strong>`;
  }
  if (TEXT_WRAPPERS[command]) return `<span class="${TEXT_WRAPPERS[command]}">${inner}</span>`;
  if (TRANSPARENT_COMMANDS.has(command)) return inner;
  if (command === "frac") return inner;
  return inner;
}

function renderLatexSegment(text, mode = "text") {
  let html = "";
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];

    if (mode === "math" && (char === "^" || char === "_")) {
      const atom = readAtom(text, index + 1, mode);
      html += char === "^" ? `<sup>${atom.value}</sup>` : `<sub>${atom.value}</sub>`;
      index = atom.next - 1;
      continue;
    }

    if (char === "\\" && index + 1 < text.length) {
      const next = text[index + 1];
      if (ESCAPED_CHAR[next]) {
        html += ESCAPED_CHAR[next];
        index += 1;
        continue;
      }

      const commandMatch = text.slice(index + 1).match(/^([A-Za-z]+)/);
      if (commandMatch) {
        const command = commandMatch[1];
        const afterCommand = index + command.length + 1;
        let cursor = afterCommand;
        while (text[cursor] === " ") cursor += 1;

        if (command === "frac" && text[cursor] === "{") {
          const numeratorClose = findBalancedBrace(text, cursor);
          let denominatorOpen = numeratorClose + 1;
          while (text[denominatorOpen] === " ") denominatorOpen += 1;
          if (numeratorClose !== -1 && text[denominatorOpen] === "{") {
            const denominatorClose = findBalancedBrace(text, denominatorOpen);
            if (denominatorClose !== -1) {
              const numerator = renderLatexSegment(text.slice(cursor + 1, numeratorClose), mode);
              const denominator = renderLatexSegment(text.slice(denominatorOpen + 1, denominatorClose), mode);
              html += `<span class="math-fraction"><sup>${numerator}</sup>/<sub>${denominator}</sub></span>`;
              index = denominatorClose;
              continue;
            }
          }
        }

        if (cursor < text.length && text[cursor] === "{") {
          const close = findBalancedBrace(text, cursor);
          if (close !== -1) {
            const inner = renderLatexSegment(text.slice(cursor + 1, close), mode);
            html += wrapCommand(command, inner, mode);
            index = close;
            continue;
          }
        }

        html += SYMBOLS[command] || escapeHtml(command);
        index = afterCommand - 1;
        continue;
      }

      if (next === "," || next === ":" || next === ";" || next === "!") {
        html += " ";
        index += 1;
        continue;
      }
    }

    if (char === "~") {
      html += "&nbsp;";
    } else if (char === "{" || char === "}") {
      html += "";
    } else {
      html += escapeHtml(char);
    }
  }
  return html;
}

function findClosingMath(text, start, delimiter) {
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === "\\" && index + 1 < text.length) {
      index += 1;
      continue;
    }
    if (delimiter === "$" && text[index] === "$") return index;
    if (delimiter !== "$" && text.startsWith(delimiter, index)) return index;
  }
  return -1;
}

function renderMath(content, block = false) {
  const body = renderLatexSegment(content.trim(), "math").replace(/\s+/g, " ");
  const className = block ? "math-block" : "math-inline";
  return `<span class="${className}">${body}</span>`;
}

function renderTextSegment(text) {
  return renderLatexSegment(text, "text");
}

export function renderAcademicText(value) {
  const text = collapseWhitespace(value);
  if (!text) return "";

  let html = "";
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "$") {
      const close = findClosingMath(text, index + 1, "$");
      if (close !== -1) {
        html += renderMath(text.slice(index + 1, close));
        index = close;
        continue;
      }
    }

    if (text.startsWith("\\(", index)) {
      const close = findClosingMath(text, index + 2, "\\)");
      if (close !== -1) {
        html += renderMath(text.slice(index + 2, close));
        index = close + 1;
        continue;
      }
    }

    if (text.startsWith("\\[", index)) {
      const close = findClosingMath(text, index + 2, "\\]");
      if (close !== -1) {
        html += renderMath(text.slice(index + 2, close), true);
        index = close + 1;
        continue;
      }
    }

    let next = text.length;
    const candidates = [text.indexOf("$", index + 1), text.indexOf("\\(", index + 1), text.indexOf("\\[", index + 1)];
    for (const candidate of candidates) {
      if (candidate !== -1 && candidate < next) next = candidate;
    }
    html += renderTextSegment(text.slice(index, next));
    index = next - 1;
  }

  return html;
}
