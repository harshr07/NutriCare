const photoInput = document.getElementById('label-photo');
const scanButton = document.getElementById('scan-label');
const scanStatus = document.getElementById('scan-status');
const scannedText = document.getElementById('scanned-text');

function normalizedText(text) {
  return text
    .replace(/(\d),(\d)/g, '$1.$2')
    .replace(/[—–]/g, '-')
    .replace(/\bcalories\b/gi, ' calories ')
    .replace(/\n+/g, '\n');
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

function valueFromLabelLine(text, names, unit) {
  const escapedNames = names.map(name => name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const namePattern = new RegExp(`\\b(${escapedNames.join('|')})\\b`, 'i');
  const lines = text.split('\n');

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const nameMatch = line.match(namePattern);
    if (!nameMatch) continue;

    let remainder = line.slice(nameMatch.index + nameMatch[0].length);
    if (!/\d/.test(remainder) && lines[index + 1]) remainder += ` ${lines[index + 1]}`;
    const expectedUnit = new RegExp(`(?:^|\\s|\\()([0-9]+(?:\\.[0-9]+)?)\\s*(?:${unit})\\b`, 'i');
    const unitMatch = remainder.match(expectedUnit);
    if (unitMatch) return unitMatch[1];

    const numberMatch = remainder.match(/[^\d]{0,30}(\d+(?:\.\d+)?)/);
    if (numberMatch) return numberMatch[1];
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
    const value = valueFromLabelLine(cleaned, rule.names, rule.unit)
      || numberAfterLabel(cleaned, rule.names);
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

  const nonProductLine = /^(nutrition facts|nutrition information|nutritional information|ingredients?\b|serving size\b|amount per serving\b|per\s*\d+\s*g\b|calories?\b|energy\b|total fat\b|saturated fat\b|trans fat\b|cholesterol\b|sodium\b|total carbohydrate\b|carbohydrate\b|dietary fiber\b|fiber\b|total sugars?\b|added sugars?\b|protein\b|vitamin\b|calcium\b|iron\b|potassium\b)/i;
  const productLine = cleaned.split('\n')
    .map(line => line.trim())
    .find(line => line.length > 2 && line.length <= 120 && /[a-z]/i.test(line)
      && !nonProductLine.test(line) && !/^\d/.test(line));
  if (productLine) values.food_name = productLine;

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
    const quantity = document.querySelector('[name="quantity_g"]');
    if (quantity && !quantity.value && values.serving_g) quantity.value = values.serving_g;
  }

  const status = Object.keys(values).length
    ? `Filled ${Object.keys(values).length} detected field(s). Please check every value.`
    : 'No nutrient values could be detected. Review the scanned text.';
  scanStatus.textContent = status;
}

async function scanSelectedPhoto() {
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
    console.error('Nutrition label OCR failed:', error);
    scanStatus.textContent = 'Could not scan this photo. Try a clearer, brighter image.';
  } finally {
    scanButton.disabled = false;
  }
}

photoInput.addEventListener('change', () => {
  scanButton.disabled = !photoInput.files.length;
  if (photoInput.files.length) {
    scanSelectedPhoto();
  } else {
    scanStatus.textContent = 'No photo selected';
  }
});

scanButton.addEventListener('click', scanSelectedPhoto);

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

if (!window.Tesseract) {
  scanStatus.textContent = 'Scanner library did not load. Check your internet connection and reload.';
}
