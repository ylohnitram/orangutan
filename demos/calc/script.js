const elements = {
  keypad: document.querySelector('.keypad'),
  mainDisplay: document.getElementById('main-display'),
  subDisplay: document.getElementById('sub-display'),
  status: document.getElementById('status'),
};

const state = {
  expression: '0',
  overwrite: true,
  lastResult: null,
};

const OPERATORS = new Set(['+', '-', '*', '/', '%']);

function updateDisplays(subText = state.expression, statusText = '') {
  elements.mainDisplay.value = state.expression;
  elements.mainDisplay.textContent = state.expression;
  elements.subDisplay.textContent = subText;
  elements.status.textContent = statusText;
}

function sanitizeExpression(expr) {
  return expr.replace(/[^\d+\-*/%.]/g, '');
}

function evaluateExpression(expr) {
  const sanitized = sanitizeExpression(expr);
  if (!sanitized) {
    throw new Error('Žádný výraz ke zpracování.');
  }

  const result = Function(`"use strict"; return (${sanitized});`)();
  if (!Number.isFinite(result)) {
    throw new Error('Výsledek není konečné číslo.');
  }
  return Number(result.toFixed(6));
}

function endsWithOperator() {
  return OPERATORS.has(state.expression.at(-1));
}

function appendDigit(value) {
  const shouldReplace = state.overwrite || state.expression === '0' && value !== '.';
  if (value === '.' && state.expression.split(/[^0-9.]/).pop().includes('.')) {
    return;
  }
  if (shouldReplace && value !== '.') {
    state.expression = value;
  } else if (shouldReplace && value === '.') {
    state.expression = '0.';
  } else {
    state.expression += value;
  }
  state.overwrite = false;
  updateDisplays();
}

function appendOperator(value) {
  if (state.overwrite && state.lastResult !== null) {
    state.overwrite = false;
  }
  if (endsWithOperator()) {
    state.expression = state.expression.slice(0, -1) + value;
  } else {
    state.expression += value;
  }
  updateDisplays();
}

function clearAll() {
  state.expression = '0';
  state.lastResult = null;
  state.overwrite = true;
  updateDisplays('0');
}

function deleteLast() {
  if (state.expression.length <= 1) {
    clearAll();
    return;
  }
  state.expression = state.expression.slice(0, -1);
  updateDisplays();
}

function invertSign() {
  const match = state.expression.match(/(-?\d*\.?\d+)(?!.*\d)/);
  if (!match) {
    return;
  }
  const start = match.index ?? 0;
  const number = match[0];
  const toggled = number.startsWith('-') ? number.slice(1) : `-${number}`;
  state.expression = `${state.expression.slice(0, start)}${toggled}${state.expression.slice(start + number.length)}`;
  updateDisplays();
}

function handleEquals() {
  try {
    const result = evaluateExpression(state.expression);
    elements.status.textContent = '';
    state.lastResult = result;
    state.expression = `${result}`;
    state.overwrite = true;
    updateDisplays(`${result}`, '');
  } catch (error) {
    state.overwrite = true;
    elements.status.textContent = error.message;
  }
}

function handleAction(action) {
  switch (action) {
    case 'clear':
      clearAll();
      break;
    case 'delete':
      deleteLast();
      break;
    case 'invert':
      invertSign();
      break;
    case 'equals':
      handleEquals();
      break;
    default:
      break;
  }
}

function handleButtonPress(button) {
  const { dataset } = button;
  if (dataset.type === 'digit') {
    appendDigit(dataset.value);
  } else if (dataset.type === 'operator') {
    if (state.overwrite && state.lastResult !== null) {
      state.overwrite = false;
    }
    appendOperator(dataset.value);
  } else if (dataset.type === 'action') {
    handleAction(dataset.action);
  }
}

elements.keypad.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) {
    return;
  }
  handleButtonPress(button);
});

updateDisplays();
