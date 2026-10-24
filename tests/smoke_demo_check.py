"""Layout check shared by the UI tests: any text outside its box, or sideways scrolling."""
CHECK = """()=>{const box=['panel','clip','strip','item','btn','notice','toast','takes','stage','track','scope','tag','field','hero','top','navbtn','erow'];
 const out=[]; const m=document.querySelector('#main'); if(m.scrollWidth>m.clientWidth+2) out.push('sideways scroll');
 for(const el of document.querySelectorAll('#main *')){ if(el.closest('.pv')||!el.offsetParent) continue;
  if(![...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())) continue;
  const r=el.getBoundingClientRect(); let a=el.parentElement; while(a&&!box.some(c=>a.classList&&a.classList.contains(c))) a=a.parentElement;
  if(!a||!r.width) continue; const b=a.getBoundingClientRect();
  if(getComputedStyle(el).textOverflow!=='ellipsis'&&(r.right>b.right+1.5||r.left<b.left-1.5)) out.push(el.textContent.trim().slice(0,40));}
 return out}"""
