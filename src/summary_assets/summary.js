  (function(){
    const t = (function(){try{return localStorage.getItem("theme")}catch(e){return null}}()) || "dark";
    document.getElementById("themeBtn").textContent = t === "dark" ? "☀️ Light" : "🌙 Dark";
  })();
  function toggleTheme() {
    const curr = document.documentElement.getAttribute("data-theme") || "dark";
    const next = curr === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try{ localStorage.setItem("theme", next); }catch(e){}
    document.getElementById("themeBtn").textContent = next === "dark" ? "☀️ Light" : "🌙 Dark";
  }
  let sortCol = 4, sortAsc = false;
  (function(){
    sortByCol(4, false);
    document.querySelectorAll("th")[4].classList.add("sorted-desc");
    updateCount();
  })();
  function sortByCol(col, asc) {
    const tbody = document.getElementById("tableBody");
    const rows  = Array.from(tbody.querySelectorAll("tr"));
    rows.sort((a, b) => {
      const av = a.cells[col].innerText.trim(), bv = b.cells[col].innerText.trim();
      const an = parseFloat(av), bn = parseFloat(bv);
      const cmp = isNaN(an)||isNaN(bn) ? av.localeCompare(bv) : an-bn;
      return asc ? cmp : -cmp;
    });
    rows.forEach(r => tbody.appendChild(r));
  }
  function sortTable(col) {
    if (sortCol===col) sortAsc=!sortAsc; else {sortCol=col; sortAsc=true;}
    sortByCol(col, sortAsc);
    document.querySelectorAll("th").forEach((th,i) => {
      th.classList.remove("sorted-asc","sorted-desc");
      if (i===col) th.classList.add(sortAsc?"sorted-asc":"sorted-desc");
    });
    updateCount();
  }
  function applySearch() {
    const q = document.getElementById("search").value.toLowerCase();
    const rows = document.querySelectorAll("#tableBody tr");
    let visible = 0;
    rows.forEach(r => {
      const show = !q || r.innerText.toLowerCase().includes(q);
      r.style.display = show ? "" : "none";
      if (show) visible++;
    });
    updateCount(visible);
  }
  function updateCount(n) {
    const total = document.querySelectorAll("#tableBody tr").length;
    const shown = n !== undefined ? n : total;
    document.getElementById("rowCount").textContent =
      shown === total ? `Showing all ${total} files` : `Showing ${shown} of ${total} files`;
  }
