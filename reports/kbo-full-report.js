const categories = JSON.parse(document.getElementById("categories-data").textContent);

const primaryTabs = document.getElementById("primary-tabs");
const secondaryTabs = document.getElementById("secondary-tabs");
const frame = document.getElementById("report-frame");
const frameLabel = document.getElementById("frame-current-label");
const frameOpenNew = document.getElementById("frame-open-new");

let activeCategoryId = categories[0].id;

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

function selectVariant(cat, index) {
  const variant = cat.variants[index] || cat.variants[0];
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
  selectVariant(cat, cat.defaultIndex);
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
