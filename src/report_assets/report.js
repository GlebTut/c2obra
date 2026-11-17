/* ── Theme toggle ───────────────────────────────────────── */
(function(){
  const t=(function(){try{return localStorage.getItem("theme")}catch(e){return null}}())||"dark";
  document.getElementById("themeBtn").textContent=t==="dark"?"☀️ Light":"🌙 Dark";
})();
function toggleTheme(){
  const curr=document.documentElement.getAttribute("data-theme")||"dark";
  const next=curr==="dark"?"light":"dark";
  document.documentElement.setAttribute("data-theme",next);
  try{localStorage.setItem("theme",next);}catch(e){}
  document.getElementById("themeBtn").textContent=next==="dark"?"☀️ Light":"🌙 Dark";
}

/* ── Collapsible sections ───────────────────────────────── */
function toggleSection(id){
  const el=document.getElementById(id);
  const btn=el.querySelector(".section-toggle");
  const isOpen=el.classList.contains("open");
  el.classList.toggle("open",!isOpen);
  btn.setAttribute("aria-expanded",String(!isOpen));
}
// open all by default already set via class

/* ── Table sort / filter ────────────────────────────────── */
let sortCol=@@status_col@@,sortAsc=true;
const STATUS_ORDER={NONE:0,PARTIAL:1,FULL:2};
function getStatus(row){return row.getAttribute("data-status")||"";}
(function defaultSort(){
  const tbody=document.getElementById("tableBody");
  const rows=Array.from(tbody.querySelectorAll("tr"));
  rows.sort((a,b)=>(STATUS_ORDER[getStatus(a)]??9)-(STATUS_ORDER[getStatus(b)]??9));
  rows.forEach(r=>tbody.appendChild(r));
  document.querySelectorAll("th")[@@status_col@@].classList.add("sorted-asc");
  updateCount();
})();
function sortTable(col){
  const tbody=document.getElementById("tableBody");
  const rows=Array.from(tbody.querySelectorAll("tr"));
  if(sortCol===col)sortAsc=!sortAsc;else{sortCol=col;sortAsc=true;}
  rows.sort((a,b)=>{
    if(col===@@status_col@@){const av=STATUS_ORDER[getStatus(a)]??9,bv=STATUS_ORDER[getStatus(b)]??9;return sortAsc?av-bv:bv-av;}
    const av=a.cells[col].innerText.trim(),bv=b.cells[col].innerText.trim();
    const an=parseFloat(av),bn=parseFloat(bv);
    const cmp=isNaN(an)||isNaN(bn)?av.localeCompare(bv):an-bn;
    return sortAsc?cmp:-cmp;
  });
  rows.forEach(r=>tbody.appendChild(r));
  document.querySelectorAll("th").forEach((th,i)=>{
    th.classList.remove("sorted-asc","sorted-desc");
    if(i===col)th.classList.add(sortAsc?"sorted-asc":"sorted-desc");
  });
  updateCount();
}
function applyFilters(){
  const search=document.getElementById("search").value.toLowerCase();
  const filter=document.getElementById("filter").value;
  const rows=document.querySelectorAll("#tableBody tr");
  let visible=0;
  rows.forEach(r=>{
    const text=r.innerText.toLowerCase();
    const status=r.getAttribute("data-status")||"";
    const ms=!search||text.includes(search);
    const mf=filter==="all"?true:filter==="uncovered"?status!=="FULL":status===filter;
    const show=ms&&mf;
    r.style.display=show?"":"none";
    if(show)visible++;
  });
  updateCount(visible);
}
function updateCount(n){
  const total=document.querySelectorAll("#tableBody tr").length;
  const shown=n!==undefined?n:total;
  document.getElementById("rowCount").textContent=
    shown===total?`Showing all ${total} branches`:`Showing ${shown} of ${total} branches`;
}
const HEADERS=@@headers_js@@;
function exportCSV(){
  const rows=Array.from(document.querySelectorAll("#tableBody tr")).filter(r=>r.style.display!=="none");
  const lines=[HEADERS.join(",")];
  rows.forEach(r=>{const cells=Array.from(r.cells).map(c=>JSON.stringify(c.innerText.trim()));lines.push(cells.join(","));});
  const blob=new Blob([lines.join("\n")],{type:"text/csv"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="coverage.csv";a.click();
}

/* ── Charts ─────────────────────────────────────────────── */
(function(){
  if(typeof Chart==="undefined"){
    document.querySelectorAll(".chart-wrap").forEach(el=>{
      el.innerHTML="<p style=\"color:#546e7a;font-size:0.8rem;text-align:center;margin-top:3.5rem\">&#9888;&#65039; Chart.js unavailable (offline or CDN blocked)</p>";
    });
    return;
  }
  const isDark=document.documentElement.getAttribute("data-theme")!=="light";
  Chart.defaults.color=isDark?"#94a3b8":"#4a90d9";
  Chart.defaults.font.family="'Segoe UI',system-ui,sans-serif";
  Chart.defaults.font.size=11;
  const C={
    full:"#16a34a",partial:"#d97706",none:"#dc2626",
    pass:"#16a34a",crash:"#78909c",timeout:"#dc2626",
    accent:"#94a3b8",accent2:"#1e293b"
  };
  const rows=@@branch_rows_json@@;
  const inputs=@@test_inputs_json@@;

  /* 1. Donut — full/partial/none */
  (function(){
    const full=rows.filter(r=>r.status==="FULL").length;
    const part=rows.filter(r=>r.status==="PARTIAL").length;
    const none=rows.filter(r=>r.status==="NONE").length;
    const tot=rows.length;
    new Chart(document.getElementById("donutChart"),{
      type:"doughnut",
      data:{labels:["Full","Partial","Not covered"],datasets:[{
        data:[full,part,none],
        backgroundColor:[C.full,C.partial,C.none],
        borderWidth:0,hoverOffset:8,
        borderRadius:3
      }]},
      options:{
        responsive:true,maintainAspectRatio:false,cutout:"70%",
        animation:{duration:800,easing:"easeOutQuart"},
        plugins:{
          legend:{display:false},
          tooltip:{callbacks:{label:ctx=>`  ${ctx.label}: ${ctx.parsed} (${tot?(ctx.parsed/tot*100).toFixed(1):0}%)`}}
        }
      }
    });
    const leg=document.getElementById("donutLegend");
    [["Full",C.full,full],["Partial",C.partial,part],["Not covered",C.none,none]].forEach(([l,c,v])=>{
      leg.innerHTML+=`<div class="chart-legend-item"><div class="chart-legend-dot" style="background:${c}"></div><span>${l}: <strong>${v}</strong> (${tot?(v/tot*100).toFixed(1):0}%)</span></div>`;
    });
  })();

  /* 2. Horizontal bar — coverage by type */
  (function(){
    const m={};
    rows.forEach(r=>{const t=r.type||"other";if(!m[t])m[t]={tot:0,hit:0};m[t].tot+=r.edges_total;m[t].hit+=r.edges_hit;});
    const labels=Object.keys(m).sort();
    const pcts=labels.map(t=>m[t].tot?+(m[t].hit/m[t].tot*100).toFixed(1):0);
    new Chart(document.getElementById("typeChart"),{
      type:"bar",
      data:{labels,datasets:[{
        label:"Coverage %",data:pcts,
        backgroundColor:pcts.map(p=>p>=80?C.full:p>=50?C.partial:C.none),
        borderRadius:5,borderSkipped:false
      }]},
      options:{
        indexAxis:"y",responsive:true,maintainAspectRatio:false,
        animation:{duration:800,easing:"easeOutQuart"},
        scales:{
          x:{min:0,max:100,grid:{color:"rgba(38,166,154,0.08)"},ticks:{callback:v=>v+"%"}},
          y:{grid:{display:false}}
        },
        plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>` ${ctx.parsed.x}%`}}}
      }
    });
  })();

  /* 4. Doughnut — test run statuses */
  (function(){
    const cnt={pass:0,partial:0,timeout:0,crash:0};
    if(Array.isArray(inputs))inputs.forEach(t=>{const s=(t.status||"pass").toLowerCase();if(s in cnt)cnt[s]++;else cnt.pass++;});
    const tot=Object.values(cnt).reduce((a,b)=>a+b,0);
    if(!tot){document.getElementById("statusChart").parentElement.innerHTML="<p style=\"color:#546e7a;font-size:0.8rem;text-align:center;margin-top:3.5rem\">No test run data</p>";return;}
    new Chart(document.getElementById("statusChart"),{
      type:"doughnut",
      data:{labels:["Pass","Partial","Timeout","Crash"],datasets:[{
        data:[cnt.pass,cnt.partial,cnt.timeout,cnt.crash],
        backgroundColor:[C.pass,C.partial,C.timeout,C.crash],
        borderWidth:0,hoverOffset:8,borderRadius:3
      }]},
      options:{
        responsive:true,maintainAspectRatio:false,cutout:"70%",
        animation:{duration:800,easing:"easeOutQuart"},
        plugins:{
          legend:{position:"bottom",labels:{boxWidth:9,boxHeight:9,padding:10}},
          tooltip:{callbacks:{label:ctx=>`  ${ctx.label}: ${ctx.parsed} (${tot?(ctx.parsed/tot*100).toFixed(1):0}%)`}}
        }
      }
    });
  })();
})();
