let currentItem = null;
let showing = "pdf";

async function getJSON(url, opts={}){
  const res = await fetch(url, opts);
  if(!res.ok) throw new Error(await res.text());
  return await res.json();
}

function setStatus(msg){ document.getElementById("status").textContent = msg; }
function setMeta(msg){ document.getElementById("meta").textContent = msg; }

function humanDate(iso){
  const d = new Date(iso + "T12:00:00");
  return new Intl.DateTimeFormat(undefined,{year:"numeric",month:"short",day:"numeric"}).format(d);
}
function updateDateHuman(){
  const iso = document.getElementById("date").value;
  document.getElementById("date-human").textContent = iso ? humanDate(iso) : "";
}

function setViewer(){
  const iframe = document.getElementById("doc-viewer");
  if(!currentItem){ iframe.src=""; return; }
  if(showing==="pdf" && currentItem.pdf_url){ iframe.src=currentItem.pdf_url; }
  else if(showing==="docx" && currentItem.docx_html_url){ iframe.src=currentItem.docx_html_url; }
  else if(currentItem.pdf_url){ showing="pdf"; iframe.src=currentItem.pdf_url; }
  else if(currentItem.docx_html_url){ showing="docx"; iframe.src=currentItem.docx_html_url; }
  else { iframe.src=""; }
}

async function loadNext(){
  try {
    setStatus("Loading next item...");
    console.log("DEBUG: Calling /api/next");
    const data = await getJSON("/api/next");
    console.log("DEBUG: Received data:", data);
    currentItem = data;
    document.getElementById("editor").value = data.initial_text || "";
    document.getElementById("title").value = "";
    document.getElementById("date").value = data.date_parsed || "";
    updateDateHuman();
    document.getElementById("category").value = data.category || "";
    document.getElementById("author").value = data.author || "";
    setMeta(`${data.basename} • ${data.date_parsed} • PDF:${data.has_pdf} DOCX:${data.has_docx}`);
    showing = "pdf";
    setViewer();
    setStatus("Ready.");
  } catch (error) {
    console.error("ERROR in loadNext:", error);
    setStatus("Error loading document: " + error.message);
  }
}

async function doCleanup(){
  const text = document.getElementById("editor").value;
  const res = await getJSON("/api/cleanup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
  document.getElementById("editor").value = res.text;
}

async function doReOCR(){
  if(!currentItem || !currentItem.has_pdf){ alert("No PDF available to OCR."); return; }
  setStatus("Re-OCR in progress...");
  const res = await getJSON("/api/ocr",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({basename: currentItem.basename})});
  document.getElementById("editor").value = res.text || "";
  setStatus("Re-OCR complete.");
}

async function postStatus(kind){
  if(!currentItem) return;
  const title = document.getElementById("title").value.trim();
  const date = document.getElementById("date").value;
  const content = document.getElementById("editor").value;
  if(kind!=="skip" && (!title || !date)){ alert("Title and Date are required."); return; }
  setStatus(kind==="publish"?"Publishing...":kind==="draft"?"Saving draft...":"Skipping...");
  const res = await getJSON(`/api/${kind}`,{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ basename: currentItem.basename, year_folder: currentItem.year_folder, title, date, content })
  });
  setStatus(res.message || "Done.");
  await loadNext();
}

document.getElementById("cleanup").addEventListener("click", doCleanup);
document.getElementById("reocr").addEventListener("click", doReOCR);
document.getElementById("publish").addEventListener("click", ()=>postStatus("publish"));
document.getElementById("draft").addEventListener("click", ()=>postStatus("draft"));
document.getElementById("skip").addEventListener("click", ()=>postStatus("skip"));
document.getElementById("show-pdf").addEventListener("click", ()=>{showing="pdf"; setViewer();});
document.getElementById("show-docx").addEventListener("click", ()=>{showing="docx"; setViewer();});
document.getElementById("date").addEventListener("input", updateDateHuman);

// Shortcuts
document.addEventListener("keydown",(e)=>{
  if((e.metaKey||e.ctrlKey)&&e.key==="Enter"){ postStatus("publish"); e.preventDefault(); }
  if((e.metaKey||e.ctrlKey)&&(e.key==="s"||e.key==="S")){ postStatus("draft"); e.preventDefault(); }
  if(e.altKey && e.key==="ArrowRight"){ loadNext(); e.preventDefault(); }
});

(async()=>{ await loadNext(); })();
