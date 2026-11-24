const photoInput = document.getElementById('label-photo');
const scanButton = document.getElementById('scan-label');
const scanStatus = document.getElementById('scan-status');
const scannedText = document.getElementById('scanned-text');

const addForm = document.querySelector('#add-food form');
const rawLabelInput = document.getElementById('raw-label-text');
const safetyButton = document.getElementById('check-food-safety');
const safetyResult = document.getElementById('food-safety-result');

function normalizedText(text) {
    return String(text || '')
        .replace(/\r\n?/g, '\n')
        .replace(/[—–]/g, '-')
        .replace(/[ \t]+/g, ' ')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

function extractSection(text, startPattern, stopPattern) {
    const start = text.match(startPattern);
    if (!start) return '';
    const startIndex = start.index + start[0].length;
    const remainder = text.slice(startIndex);
    const stop = remainder.search(stopPattern);
    return (stop >= 0 ? remainder.slice(0, stop) : remainder)
        .replace(/\s+/g, ' ').trim();
}

function numberAfterLabel(text, names) {
    for (const name of names) {
        const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const match = text.match(new RegExp(`${escaped}[^\\d\\n]{0,12}(\\d+(?:\\.\\d+)?)`, 'i'));
        if (match) return match[1];
    }
    return null;
}

function parseLabel(text) {
    const cleaned = normalizedText(text);
    const values = {};
    const fieldRules = {
        calories: ['calories', 'energy'], protein: ['protein'],
        carbs: ['total carbohydrate', 'total carbs', 'carbohydrate'],
        fat: ['total fat'], saturated_fat: ['saturated fat'], trans_fat: ['trans fat'],
        fiber: ['dietary fibre', 'dietary fiber', 'fibre', 'fiber'],
        sugar: ['total sugars', 'total sugar', 'sugars'],
        added_sugar: ['added sugars', 'added sugar'], sodium: ['sodium'],
        potassium: ['potassium'], phosphorus: ['phosphorus'], calcium: ['calcium'],
        iron: ['iron'], vitamin_a: ['vitamin a'], vitamin_c: ['vitamin c'],
        vitamin_d: ['vitamin d'], vitamin_b12: ['vitamin b12', 'vitamin b-12']
    };
    for (const [field, names] of Object.entries(fieldRules)) {
        const value = numberAfterLabel(cleaned, names);
        if (value !== null) values[field] = value;
    }
    const serving = cleaned.match(/(?:serving size|one serving)[^\d]{0,30}(\d+(?:\.\d+)?)\s*g/i);
    if (serving) values.serving_g = serving[1];
    const stop = /\b(?:contains|may contain|allergen|nutrition facts|nutrition information|best before|expiry date|manufactured by|net weight|mrp|fssai)\b/i;
    values.ingredients = extractSection(cleaned, /\bingredients?(?:\s+list)?\s*:?\s+/i, stop);
    values.contains_text = extractSection(cleaned, /\bcontains\s*:?\s+/i, /\b(?:may\s+contain|nutrition facts|nutrition information|best before|expiry date|fssai)\b/i);
    values.may_contain_text = extractSection(cleaned, /\bmay\s+contain(?:\s+traces?\s+of)?\s*:?\s+/i, /\b(?:nutrition facts|nutrition information|best before|expiry date|fssai)\b/i);
    values.raw_label_text = text;
    return values;
}

function fillForm(values) {
    for (const [field, value] of Object.entries(values)) {
        const input = addForm.elements.namedItem(field);
        if (input) input.value = value;
    }
    rawLabelInput.value = scannedText.value;
    scanStatus.textContent = `Detected ${Object.keys(values).length} field(s). Verify every value manually.`;
}

async function scanSelectedPhotos() {
    if (!photoInput.files.length || !window.Tesseract) {
        scanStatus.textContent = 'OCR is unavailable. Reload the page and try again.';
        return;
    }
    scanButton.disabled = true;
    const files = Array.from(photoInput.files);
    const results = [];
    try {
        for (let index = 0; index < files.length; index += 1) {
            scanStatus.textContent = `Scanning photo ${index + 1} of ${files.length}...`;
            const result = await window.Tesseract.recognize(files[index], 'eng', {
                logger: message => {
                    if (message.status === 'recognizing text') scanStatus.textContent = `Photo ${index + 1}: ${Math.round(message.progress * 100)}%`;
                }
            });
            results.push(`\n--- PHOTO ${index + 1} ---\n${result.data.text}`);
        }
        scannedText.value = results.join('\n');
        rawLabelInput.value = scannedText.value;
        document.getElementById('scan-text-details').open = true;
        fillForm(parseLabel(scannedText.value));
    } catch (error) {
        console.error(error);
        scanStatus.textContent = 'Could not scan. Try clearer photos.';
    } finally {
        scanButton.disabled = false;
    }
}

photoInput.addEventListener('change', () => {
    scanButton.disabled = !photoInput.files.length;
    if (photoInput.files.length) scanSelectedPhotos();
});
scanButton.addEventListener('click', scanSelectedPhotos);
document.getElementById('fill-from-text').addEventListener('click', () => {
    rawLabelInput.value = scannedText.value;
    fillForm(parseLabel(scannedText.value));
});
scannedText.addEventListener('input', () => { rawLabelInput.value = scannedText.value; });

function renderFoodSafety(result) {
    safetyResult.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = `Overall status: ${result.overall_status}`;
    safetyResult.appendChild(heading);
    for (const finding of result.findings) {
        const item = document.createElement('div'); item.className = 'limit-row';
        const title = document.createElement('strong'); title.textContent = `${finding.status} — ${finding.category}`;
        const message = document.createElement('p'); message.textContent = finding.message;
        item.append(title, message);
        if (finding.nutrient) {
            const amount = document.createElement('small'); amount.textContent = `${finding.amount} ${finding.unit} in the consumed quantity`; item.appendChild(amount);
        }
        if (finding.reference_percent !== undefined) {
            const reference = document.createElement('small'); reference.textContent = `${finding.reference_percent}% of the stated population reference`; item.appendChild(reference);
        }
        if (finding.source_url) {
            const link = document.createElement('a'); link.href = finding.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.textContent = 'Evidence source'; item.appendChild(link);
        }
        safetyResult.appendChild(item);
    }
    if (result.review_required) {
        const warning = document.createElement('p'); warning.textContent = 'Ingredients could not be identified. Enter them manually before relying on this report.'; safetyResult.appendChild(warning);
    }
    const notice = document.createElement('p'); notice.textContent = result.notice; safetyResult.appendChild(notice);
}

safetyButton.addEventListener('click', async () => {
    safetyButton.disabled = true; safetyResult.textContent = 'Checking product...';
    const nutrition = {};
    const nutrientFields = ['calories','protein','carbs','fat','saturated_fat','trans_fat','fiber','sugar','added_sugar','sodium','potassium','phosphorus','calcium','iron','vitamin_a','vitamin_c','vitamin_d','vitamin_b12'];
    for (const field of nutrientFields) {
        const input = addForm.elements.namedItem(field);
        if (input && input.value !== '') nutrition[field] = input.value;
    }
    const payload = {
        csrf_token: addForm.elements.namedItem('csrf_token').value,
        raw_label_text: rawLabelInput.value,
        ingredients: addForm.elements.namedItem('ingredients').value,
        contains_text: addForm.elements.namedItem('contains_text').value,
        may_contain_text: addForm.elements.namedItem('may_contain_text').value,
        quantity_g: addForm.elements.namedItem('quantity_g').value,
        label_basis: addForm.elements.namedItem('label_basis').value,
        serving_g: addForm.elements.namedItem('serving_g').value,
        nutrition
    };
    try {
        const response = await fetch('/health/nutrition/food-safety/analyze', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Analysis failed.');
        renderFoodSafety(result);
    } catch (error) {
        safetyResult.textContent = error.message;
    } finally { safetyButton.disabled = false; }
});

const chartData = document.getElementById('week-data');
const chartCanvas = document.getElementById('week-chart');
if (chartData && chartCanvas && window.Chart) {
  const week = JSON.parse(chartData.textContent);
  const historySelect = document.getElementById('history-nutrient');
  const historyChart = new Chart(chartCanvas, {
    type: 'bar',
    data: {
      labels: week.map(day => day.date),
      datasets: [{label: 'Calories (kcal)', data: week.map(day => day.nutrients.calories), backgroundColor: '#71b38a'}]
    },
    options: {responsive: true, scales: {y: {beginAtZero: true}}}
  });

  function updateHistoryChart() {
    const field = historySelect.value;
    historyChart.data.datasets[0].label = historySelect.selectedOptions[0].textContent;
    historyChart.data.datasets[0].data = week.map(day => day.nutrients[field]);
    historyChart.update();
  }

  historySelect.addEventListener('change', updateHistoryChart);
}

if (!window.Tesseract) {
  scanStatus.textContent = 'Scanner library did not load. Check your internet connection and reload.';
}
