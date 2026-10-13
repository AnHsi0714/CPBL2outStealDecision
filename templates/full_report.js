const categories = JSON.parse(document.getElementById("categories-data").textContent);

const primaryTabs = document.getElementById("primary-tabs");
const secondaryTabs = document.getElementById("secondary-tabs");
const frame = document.getElementById("report-frame");
const frameLabel = document.getElementById("frame-current-label");
const frameOpenNew = document.getElementById("frame-open-new");

let activeCategoryId = categories[0].id;
let activeYear = null;
let lastAnchor = null;

function categoryById(id) {
  return categories.find((c) => c.id === id);
}

function renderPrimaryTabs() {
  primaryTabs.querySelectorAll(".tab").forEach((btn) => {
    btn.setAttribute("aria-selected", btn.dataset.cat === activeCategoryId ? "true" : "false");
  });
}

function renderSecondaryTabs() {
  const cat = categoryById(activeCategoryId);
  const hasYearTabs = cat.variants.length > 1;
  if (!hasYearTabs) {
    secondaryTabs.hidden = true;
    secondaryTabs.innerHTML = "";
    return;
  }
  secondaryTabs.hidden = false;
  secondaryTabs.innerHTML = cat.variants
    .map(
      (v, i) =>
        `<button type="button" class="sub-tab" data-idx="${i}" aria-selected="${i === cat.defaultIndex ? "true" : "false"}">${v.year}</button>`
    )
    .join("");
}

// 切換報告時的捲動位置同步：報告頁（iframe 內）用 postMessage 回報目前停在哪個區塊，
// 載入新報告後入口頁再請它捲到同一區塊。用 postMessage 而非直接讀 iframe 內容，
// 這樣本機以 file:// 開啟（跨來源）時也能運作。
window.addEventListener("message", (event) => {
  if (event.source !== frame.contentWindow || !event.data) return;
  if (event.data.type === "report-anchor") {
    lastAnchor = event.data.anchor;
  } else if (event.data.type === "report-ready") {
    if (lastAnchor) frame.contentWindow.postMessage({ type: "report-restore", anchor: lastAnchor }, "*");
    frame.style.opacity = "1";
  }
});

frame.addEventListener("load", () => { frame.style.opacity = "1"; });

function selectVariant(cat, index) {
  const variant = cat.variants[index] || cat.variants[0];
  activeYear = variant.year;
  frame.style.opacity = "0.15";
  const label = variant.year ? `${cat.label}・${variant.year}` : cat.label;
  frameLabel.textContent = `${label}｜${cat.description}`;
  frameLabel.title = cat.description;
  frameOpenNew.href = variant.file;
  frame.src = variant.file;
  secondaryTabs.querySelectorAll(".sub-tab").forEach((btn) => {
    btn.setAttribute("aria-selected", Number(btn.dataset.idx) === index ? "true" : "false");
  });
}

function activateCategory(id) {
  if (id !== activeCategoryId) lastAnchor = null;
  activeCategoryId = id;
  const cat = categoryById(id);
  renderPrimaryTabs();
  renderSecondaryTabs();
  // 同分類換聯盟或換分類時，盡量沿用目前年份。
  const sameYear = cat.variants.findIndex((v) => v.year && v.year === activeYear);
  const index = sameYear >= 0 ? sameYear : cat.defaultIndex;
  if (index !== cat.defaultIndex) {
    secondaryTabs.querySelectorAll(".sub-tab").forEach((btn) => {
      btn.setAttribute("aria-selected", Number(btn.dataset.idx) === index ? "true" : "false");
    });
  }
  selectVariant(cat, index);
}

primaryTabs.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => activateCategory(btn.dataset.cat));
});

secondaryTabs.addEventListener("click", (event) => {
  const btn = event.target.closest(".sub-tab");
  if (!btn) return;
  selectVariant(categoryById(activeCategoryId), Number(btn.dataset.idx));
});

activateCategory(activeCategoryId);
