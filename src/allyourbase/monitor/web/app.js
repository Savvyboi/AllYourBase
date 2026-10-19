"use strict";
const categorySelect = document.querySelector("#category-filter");
if (categorySelect) {
  const buttons = [...document.querySelectorAll("[data-filter]")];
  const params = new URLSearchParams(location.search);
  const requested = params.get("category") || "";
  categorySelect.value = [...categorySelect.options].some(o => o.value === requested) ? requested : "";
  let status = buttons.some(b => b.dataset.filter === params.get("status")) ? params.get("status") : "all";
  function filter() {
    const category = categorySelect.value;
    for (const card of document.querySelectorAll(".location-card")) {
      card.hidden = (category !== "" && card.dataset.category !== category) || (status !== "all" && card.dataset.status !== status);
    }
    for (const group of document.querySelectorAll("[data-category-group]")) {
      group.hidden = ![...group.querySelectorAll(".location-card")].some(card => !card.hidden);
    }
    for (const card of document.querySelectorAll(".detection-card")) card.hidden = category !== "" && card.dataset.category !== category;
    document.querySelector("#checks-empty").hidden = [...document.querySelectorAll(".location-card")].some(card => !card.hidden);
    document.querySelector("#detections-empty").hidden = [...document.querySelectorAll(".detection-card")].some(card => !card.hidden);
    for (const button of buttons) button.setAttribute("aria-pressed", String(button.dataset.filter === status));
    const url = new URL(location.href);
    category ? url.searchParams.set("category", category) : url.searchParams.delete("category");
    status !== "all" ? url.searchParams.set("status", status) : url.searchParams.delete("status");
    history.replaceState(null, "", url);
  }
  categorySelect.addEventListener("change", filter);
  for (const button of buttons) button.addEventListener("click", () => {status = button.dataset.filter; filter();});
  filter();
}
