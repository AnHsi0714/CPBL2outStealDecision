const categories = JSON.parse(document.getElementById("categories-data").textContent);

const primaryTabs = document.getElementById("primary-tabs");
const secondaryTabs = document.getElementById("secondary-tabs");
const frame = document.getElementById("report-frame");
const frameLabel = document.getElementById("frame-current-label");
const frameOpenNew = document.getElementById("frame-open-new");

let activeCategoryId = categories[0].id;
let activeYear = null;
let pendingScroll = null;

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

// 切換報告時記住 iframe 目前捲動位置，載入完成後捲回同一處，避免每次都回到頂端。
frame.addEventListener("load", () => {
  if (pendingScroll === null) return;
  const y = pendingScroll;
  pendingScroll = null;
  const restore = () => { try { frame.contentWindow.scrollTo(0, y); } catch (e) {} };
  restore();
  requestAnimationFrame(restore);
});

function selectVariant(cat, index) {
  const variant = cat.variants[index] || cat.variants[0];
  activeYear = variant.year;
  try { pendingScroll = frame.contentWindow.scrollY; } catch (e) { pendingScroll = null; }
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
