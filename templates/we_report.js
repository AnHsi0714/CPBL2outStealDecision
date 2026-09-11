const payload = JSON.parse(document.getElementById("report-data").textContent);

const BASE_CODE_ORDER = [0, 1, 2, 4, 3, 5, 6, 7];
const BASE_LABELS = { 0: "空壘", 1: "一壘", 2: "二壘", 4: "三壘", 3: "一二壘", 5: "一三壘", 6: "二三壘", 7: "一二三壘" };
const INNING_LABELS = { "1-6": "第 1–6 局", "7": "第 7 局", "8": "第 8 局", "9+": "第 9 局以後" };
const SIDE_LABELS = payload.battingSideLabels;
const CAP = payload.scoreDiffCap;
const MIN_N_LOW = 20;

const cellIndex = new Map();
for (const cell of payload.cells) {
  const key = [cell.inningBucket, cell.battingSide, cell.scoreDiffBucket, cell.outs, cell.baseCode].join("|");
  cellIndex.set(key, cell);
}

function diffLabel(bucket) {
  if (bucket <= -CAP) return `落後${CAP}+`;
  if (bucket < 0) return `落後${-bucket}`;
  if (bucket === 0) return "平手";
  if (bucket < CAP) return `領先${bucket}`;
  return `領先${CAP}+`;
}

function levelFor(winRate) {
  return Math.max(0, Math.min(12, Math.round(winRate * 12)));
}

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const inningSelect = document.getElementById("ctl-inning");
const sideSelect = document.getElementById("ctl-side");
const outsSelect = document.getElementById("ctl-outs");

for (const bucket of payload.inningBuckets) {
  const opt = document.createElement("option");
  opt.value = bucket;
  opt.textContent = INNING_LABELS[bucket] || bucket;
  if (bucket === "7") opt.selected = true;
  inningSelect.appendChild(opt);
}
for (const side of ["1", "2"]) {
  const opt = document.createElement("option");
  opt.value = side;
  opt.textContent = SIDE_LABELS[side];
  if (side === "1") opt.selected = true;
  sideSelect.appendChild(opt);
}
for (const outs of [0, 1, 2]) {
  const opt = document.createElement("option");
  opt.value = String(outs);
  opt.textContent = `${outs} 出局`;
  if (outs === 2) opt.selected = true;
  outsSelect.appendChild(opt);
}

function render() {
  const inningBucket = inningSelect.value;
  const battingSide = sideSelect.value;
  const outs = Number(outsSelect.value);

  const colHeaders = document.getElementById("col-headers");
  const gridCells = document.getElementById("grid-cells");
  const tableRows = document.getElementById("table-rows");
  colHeaders.innerHTML = BASE_CODE_ORDER.map((code) => `<div class="col-label">${BASE_LABELS[code]}</div>`).join("");

  const cellsHtml = [];
  const rowsHtml = [];
  for (let diff = CAP; diff >= -CAP; diff--) {
    cellsHtml.push(`<div class="row-label">${esc(diffLabel(diff))}</div>`);
    for (const baseCode of BASE_CODE_ORDER) {
      const key = [inningBucket, battingSide, diff, outs, baseCode].join("|");
      const cell = cellIndex.get(key);
      const label = BASE_LABELS[baseCode];
      if (!cell || cell.winRate === null) {
        cellsHtml.push(
          `<div class="cell empty" data-tooltip="${esc(diffLabel(diff))}・${esc(label)}｜無樣本">` +
          `<span class="cell-value">—</span><span class="cell-n">n=0</span></div>`
        );
        continue;
      }
      const pct = (cell.winRate * 100).toFixed(1);
      const lowN = cell.n < MIN_N_LOW;
      const tooltip = `${diffLabel(diff)}・${label}｜勝率 ${pct}%｜n=${cell.n.toLocaleString()}`;
      cellsHtml.push(
        `<div class="cell${lowN ? " low-n" : ""}" data-level="${levelFor(cell.winRate)}" tabindex="0" data-tooltip="${esc(tooltip)}">` +
        `<span class="cell-value">${pct}%</span><span class="cell-n">n=${cell.n.toLocaleString()}</span></div>`
      );
      rowsHtml.push(
        `<tr><td>${esc(diffLabel(diff))}</td><td>${esc(label)}</td><td>${pct}%</td><td>${cell.n.toLocaleString()}</td></tr>`
      );
    }
  }
  gridCells.innerHTML = cellsHtml.join("");
  tableRows.innerHTML = rowsHtml.join("");
}

[inningSelect, sideSelect, outsSelect].forEach((el) => el.addEventListener("change", render));
render();

if (payload.validation) {
  const v = payload.validation;
  document.getElementById("validation-section").hidden = false;
  document.getElementById("val-violations").textContent = v.monotonicity_violation_count.toLocaleString();
  document.getElementById("val-violations-note").textContent =
    `n≥${v.min_n_for_monotonicity} 的相鄰分差對中出現，多為極端分差桶邊界`;
  const coveragePct = v.coverage_target_cell_count
    ? (100 - (v.coverage_below_min_n_count / v.coverage_target_cell_count) * 100).toFixed(0)
    : "—";
  document.getElementById("val-coverage").textContent = `${coveragePct}% 達標`;
  document.getElementById("val-low-n").textContent =
    `${v.coverage_below_min_n_count.toLocaleString()} / ${v.coverage_target_cell_count.toLocaleString()}`;
  const tied = v.tied_game_win_rate_by_batting_side || {};
  const tiedParts = Object.entries(tied).map(([label, stats]) => `${label} ${(stats.winRate * 100).toFixed(1)}%（n=${stats.n.toLocaleString()}）`);
  document.getElementById("val-tied-note").textContent =
    `平手時勝率（主場優勢粗檢查）：${tiedParts.join("　vs　")}`;
}
