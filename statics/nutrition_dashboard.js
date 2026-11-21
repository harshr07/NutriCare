const photoInput = document.getElementById('label-photo');
const scanButton = document.getElementById('scan-label');
const scanStatus = document.getElementById('scan-status');
const scannedText = document.getElementById('scanned-text');

function normalizedText(text) {
  return text
    .replace(/,/g, '.')
    .replace(/[—–]/g, '-')
    .replace(/\bcalories\b/gi, ' calories ')
    .replace(/\n+/g, '\n');
}

function numberBeforeUnit(text, names, unit) {
  const namePattern = names.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
  const patterns = [
    new RegExp(`(?:${namePattern})\\s*[:=-]?\\s*(\\d+(?:\.\\d+)?)\\s*${unit}`, 'i'),
    new RegExp(`(?:${namePattern})[^\\d\\n]{0,20}(\\d+(?:\.\\d+)?)\\s*${unit}`, 'i')
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function numberAfterLabel(text, names) {
  for (const name of names) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`${escaped}[^\\d\\n]{0,12}(\\d+(?:\\.\\d+)?)`, 'i');
    const match = text.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function parseLabel(text) {
  const cleaned = normalizedText(text);
  const values = {};

  const fieldRules = {
    calories: {names: ['calories', 'energy', 'energy kcal'], unit: 'kcal'},
    protein: {names: ['protein'], unit: 'g'},
    carbs: {names: ['total carbohydrate', 'total carbs', 'carbohydrate'], unit: 'g'},
    fat: {names: ['total fat'], unit: 'g'},
    saturated_fat: {names: ['saturated fat'], unit: 'g'},
    fiber: {names: ['dietary fibre', 'dietary fiber', 'fibre', 'fiber'], unit: 'g'},
    sugar: {names: ['total sugars', 'total sugar', 'sugars'], unit: 'g'},
    added_sugar: {names: ['added sugars', 'added sugar'], unit: 'g'},
    sodium: {names: ['sodium'], unit: 'mg'},
    potassium: {names: ['potassium'], unit: 'mg'},
    calcium: {names: ['calcium'], unit: 'mg'},
    iron: {names: ['iron'], unit: 'mg'},
    vitamin_a: {names: ['vitamin a'], unit: 'µg|mcg|ug'},
    vitamin_c: {names: ['vitamin c'], unit: 'mg'},
    vitamin_d: {names: ['vitamin d'], unit: 'µg|mcg|ug'},
    vitamin_b12: {names: ['vitamin b12', 'vitamin b-12'], unit: 'µg|mcg|ug'}
  };

  for (const [field, rule] of Object.entries(fieldRules)) {
    const value = numberBeforeUnit(cleaned, rule.names, rule.unit) || numberAfterLabel(cleaned, rule.names);
    if (value !== null) values[field] = value;
  }

  const servingPatterns = [
    /(?:serving size|one serving|per serving)[^\d]{0,30}(\d+(?:\.\d+)?)\s*g/i,
    /(\d+(?:\.\d+)?)\s*g[^\n]{0,20}(?:per|\/)?\s*serving/i
  ];
  for (const pattern of servingPatterns) {
    const match = cleaned.match(pattern);
    if (match) {
      values.serving_g = match[1];
      values.label_basis = 'serving';
      break;
    }
  }

  const ingredientsMatch = cleaned.match(/ingredients?[^:]*:\s*([^\n]+)/i)
    || cleaned.match(/ingredients?\s+(.{10,500})/i);
  if (ingredientsMatch) values.ingredients = ingredientsMatch[1].replace(/\s+/g, ' ').trim();

  return values;
}

function fillForm(values) {
  for (const [field, value] of Object.entries(values)) {
    const input = document.querySelector(`[name="${field}"]`);
    if (input) input.value = value;
  }

  if (values.label_basis === 'serving') {
    const basis = document.getElementById('label-basis');
    basis.value = 'serving';
    basis.dispatchEvent(new Event('change'));
  }

  const status = Object.keys(values).length
    ? `Filled ${Object.keys(values).length} detected field(s). Please check every value.`
    : 'No nutrient values could be detected. Review the scanned text.';
  scanStatus.textContent = status;
}

photoInput.addEventListener('change', () => {
  scanButton.disabled = !photoInput.files.length;
  scanStatus.textContent = photoInput.files.length ? 'Photo ready to scan' : 'No photo selected';
});

scanButton.addEventListener('click', async () => {
  if (!photoInput.files.length || !window.Tesseract) {
    scanStatus.textContent = 'OCR is unavailable. Try reloading with an internet connection.';
    return;
  }

  scanButton.disabled = true;
  scanStatus.textContent = 'Scanning label… 0%';

  try {
    const result = await window.Tesseract.recognize(photoInput.files[0], 'eng', {
      logger: message => {
        if (message.status === 'recognizing text') {
          scanStatus.textContent = `Scanning label… ${Math.round(message.progress * 100)}%`;
        }
      }
    });
    scannedText.value = result.data.text;
    document.getElementById('scan-text-details').open = true;
    fillForm(parseLabel(result.data.text));
  } catch (error) {
    scanStatus.textContent = 'Could not scan this photo. Try a clearer, brighter image.';
  } finally {
    scanButton.disabled = false;
  }
});

document.getElementById('fill-from-text').addEventListener('click', () => {
  fillForm(parseLabel(scannedText.value));
});

const labelBasis = document.getElementById('label-basis');
const servingGroup = document.getElementById('serving-group');
function updateServing() {
  const visible = labelBasis.value === 'serving';
  servingGroup.classList.toggle('hidden', !visible);
  document.getElementById('serving-size').required = visible;
}
labelBasis.addEventListener('change', updateServing);
updateServing();

const chartData = document.getElementById('week-data');
const chartCanvas = document.getElementById('week-chart');
if (chartData && chartCanvas && window.Chart) {
  const week = JSON.parse(chartData.textContent);
  new Chart(chartCanvas, {
    type: 'bar',
    data: {
      labels: week.map(day => day.date),
      datasets: [{label: 'Calories (kcal)', data: week.map(day => day.calories), backgroundColor: '#71b38a'}]
    },
    options: {responsive: true, scales: {y: {beginAtZero: true}}}
  });
}
