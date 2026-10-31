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

// 入口頁與報告頁（iframe）用 postMessage 溝通，這樣本機以 file:// 開啟（跨來源）時也能運作：
// report-anchor 回報目前停在哪個區塊（切換報告時捲回同一區塊）、report-ready 帶目錄項目、
// report-height 讓手機版把 iframe 撐成內容高度（只剩一層捲動）、report-goto-category 切換分頁。
let tocApi = null;
const mobileQuery = window.matchMedia("(max-width: 760px)");
let mobile = false;

function applyMobile() {
  mobile = mobileQuery.matches;
  document.documentElement.classList.toggle("mobile", mobile);
  if (!mobile) frame.style.height = "";
}
mobileQuery.addEventListener("change", applyMobile);
applyMobile();

function mountParentToc(items) {
  if (!window.ReportCommon || !items || !items.length) return;
  tocApi = window.ReportCommon.mountToc(items, {
    inline: document.querySelector(".title-row"),
    onGo: (id) => frame.contentWindow.postMessage({ type: "report-goto", id }, "*"),
  });
}

window.addEventListener("message", (event) => {
  if (event.source !== frame.contentWindow || !event.data) return;
  const d = event.data;
  if (d.type === "report-anchor") {
    lastAnchor = d.anchor;
    if (tocApi) tocApi.setActive(d.anchor.section && d.anchor.section.id);
  } else if (d.type === "report-height") {
    if (mobile) frame.style.height = `${d.height}px`;
  } else if (d.type === "report-scroll-to") {
    if (mobile) window.scrollTo({ top: frame.getBoundingClientRect().top + window.scrollY + d.y, behavior: "smooth" });
  } else if (d.type === "report-goto-category") {
    if (categoryById(d.id)) {
      lastAnchor = null;
      activateCategory(d.id);
    }
  } else if (d.type === "report-ready") {
    frame.style.opacity = "1";
    if (mobile && d.height) frame.style.height = `${d.height}px`;
    mountParentToc(d.items);
    if (lastAnchor) frame.contentWindow.postMessage({ type: "report-restore", anchor: lastAnchor }, "*");
  }
});

// 手機版整頁捲動：定期請報告頁換算「目前停在哪個區塊」。
let queryTimer = null;
window.addEventListener("scroll", () => {
  if (!mobile || queryTimer) return;
  queryTimer = setTimeout(() => {
    queryTimer = null;
    const y = Math.max(0, -frame.getBoundingClientRect().top);
    frame.contentWindow.postMessage({ type: "report-query", y }, "*");
  }, 120);
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
  // 手機版 iframe 高度跟著內容走；換報告時先放掉舊高度，否則新報告比舊的短時，底下會留一大片空白
  if (mobile) frame.style.height = "";
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
