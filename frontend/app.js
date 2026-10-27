"use strict";
const $ = id => document.getElementById(id);
const esc = value => String(value ?? "—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const number = (value,digits=1) => Number.isFinite(value) ? value.toLocaleString("de-DE",{maximumFractionDigits:digits}) : "—";
const date = value => value ? new Date(value).toLocaleString("de-DE") : "—";
const states = {arming:"Vorbereitung",running:"Läuft",draining:"Abschluss abwarten",complete:"Abgeschlossen",incomplete:"Unvollständig",failed:"Fehlgeschlagen",invalid:"Ungültige Zähler"};
let state = {nodes:[],runs:[],changes:[],profiles:[],events:[]}, selected = null, locked = false, nodeSignature = "", profileSignature = "", runSignature = "";
let charts = {};

async function api(path,body){
  const response = await fetch(path,{method:body === undefined ? "GET":"POST",headers:{"Content-Type":"application/json"},body:body === undefined ? undefined:JSON.stringify(body)});
  const data = await response.json();
  if(!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}
function error(message){$("error").textContent=message;$("error").classList.toggle("hidden",!message);}
async function action(fn){error("");try{await fn();}catch(e){error(e.message);}}
function options(el,items,current){el.innerHTML=items.map(([v,label])=>`<option value="${esc(v)}">${esc(label)}</option>`).join("");if(items.some(([v])=>String(v)===String(current)))el.value=current;}
function powerOptions(){const node=state.nodes.find(n=>n.node_id===Number($("power-node").value));options($("power"),(node?.powers_qdbm||[]).map(p=>[p,`${number(p/4,2)} dBm`]),node?.power_qdbm);}

function network(){
  const nodes=state.nodes, pos=new Map();
  nodes.forEach((n,i)=>{const angle=2*Math.PI*i/Math.max(nodes.length,1)-Math.PI;pos.set(n.node_id,nodes.length===1?[320,130]:[320+210*Math.cos(angle),135+85*Math.sin(angle)]);});
  let svg="";
  for(const [a,b] of state.edges||[]){if(!pos.has(a)||!pos.has(b))continue;const [x,y]=pos.get(a),[xx,yy]=pos.get(b);svg+=`<line x1="${x}" y1="${y}" x2="${xx}" y2="${yy}" stroke="#9fcac7" stroke-width="2" stroke-dasharray="5 6"/><rect x="${(x+xx)/2-70}" y="${(y+yy)/2-12}" width="140" height="24" rx="5" fill="#fff"/><text x="${(x+xx)/2}" y="${(y+yy)/2+4}" text-anchor="middle" font-size="10">ESP-NOW · direkt</text>`;}
  for(const n of nodes){const [x,y]=pos.get(n.node_id),color=n.online?"#007c83":"#a6b1b6";svg+=`<circle cx="${x}" cy="${y}" r="43" fill="#fff" stroke="${color}" stroke-width="1.5"/><circle cx="${x}" cy="${y}" r="34" fill="${n.online?"#e8f4f1":"#f1f3f3"}"/><text x="${x}" y="${y+6}" text-anchor="middle" font-size="20">${esc(n.node_id)}</text><text x="${x}" y="${y+66}" text-anchor="middle" class="node-role">${esc(n.role)} · ${n.online?"online":"offline"}</text>`;}
  if(!nodes.length)svg='<text x="320" y="130" text-anchor="middle" font-size="13">Warte auf Statusmeldungen …</text>';
  $("network").innerHTML=svg;$("node-count").textContent=`${nodes.filter(n=>n.online).length} / ${nodes.length} online`;
}

function render(){
  const sim=state.mode==="simulation";$("simulation").classList.toggle("hidden",!sim);$("mode").textContent=sim?"Simulation":state.mode==="hardware"?"Hardware verbunden":"Kein Gateway";$("mode").className=`badge ${sim?"warn":state.mode==="hardware"?"live":""}`;
  $("connection-error").textContent=state.connection_error||"Nur der Master benötigt eine Datenverbindung zum PC.";
  const sig=state.nodes.map(n=>n.node_id).join(",");
  if(sig!==nodeSignature){nodeSignature=sig;const items=state.nodes.map(n=>[n.node_id,`${n.node_id} · ${n.role}`]);for(const id of ["power-node","source","destination"])options($(id),items,$(id).value);if($("source").value===$("destination").value&&items.length>1)$("destination").value=items[1][0];powerOptions();}
  const ps=state.profiles.map(p=>p.id).join(",");if(ps!==profileSignature){profileSignature=ps;options($("profile"),state.profiles.map(p=>[p.id,p.label]),state.nodes[0]?.profile);}
  $("nodes").innerHTML=state.nodes.length?state.nodes.map(n=>{const change=state.changes.find(c=>c.requested.powers[n.node_id]!==undefined);const requested=change?.requested.powers[n.node_id];return `<tr><td><b>#${esc(n.node_id)}</b> · ${esc(n.role)}</td><td><span class="mono">${esc(n.mac)}</span><small>${esc(n.chip)} / ${esc(n.idf)}</small></td><td><i class="dot ${n.online?"":"offline"}"></i>${n.online?"Online":"Offline"}<small>${esc(date(n.last_seen))}</small></td><td>${requested===undefined?"—":number(requested/4,2)} → <b>${number(n.power_qdbm/4,2)} dBm</b><small>Konfigurierte Obergrenze</small></td><td>${esc(n.profile)}<small>K${esc(n.channel)} · ${number(2407+5*n.channel,0)} MHz · ${esc(n.bandwidth_mhz)} MHz</small></td><td>${number(n.tx_total,0)} / ${number(n.rx_total,0)}</td></tr>`;}).join(""):'<tr><td colspan="6">Gateway verbinden, um Geräte zu sehen.</td></tr>';
  const change=state.changes[0];$("configuration-state").textContent=change?`#${change.id} · ${{pending:"Ausstehend · Funkbestätigung wird geprüft",success:"Erfolgreich bestätigt",failed:"Fehlgeschlagen · Rückkehr angefordert"}[change.state]}${change.error?` · ${change.error}`:""}`:"Noch keine Änderung.";
  const busy=locked||Boolean(state.active)||change?.state==="pending";
  for(const el of document.querySelectorAll("#power-form button,#profile-form button"))el.disabled=busy||state.nodes.length<2||state.nodes.some(n=>!n.online);
  $("start").disabled=busy||state.nodes.length<2||state.nodes.some(n=>!n.online);$("stop").disabled=!state.active||state.runs.find(r=>r.id===state.active)?.state!=="running";
  const rs=state.runs.map(r=>r.id).join(",");if(rs!==runSignature){runSignature=rs;if(state.active)selected=state.active;else if(!selected)selected=state.runs.at(-1)?.id;options($("history"),[...state.runs].reverse().map(r=>[r.id,`#${r.id} · ${r.plan.source} → ${r.plan.destination}${r.mode==="simulation"?" · SIM":""}`]),selected);}
  $("events").innerHTML=state.events.length?state.events.map(e=>`<li class="${e.level==="error"?"error-event":""}"><time>${esc(new Date(e.at).toLocaleTimeString("de-DE"))}</time>${esc(e.message)}</li>`).join(""):"<li>Noch keine Ereignisse.</li>";
  network();results();
}

function results(){
  const run=state.runs.find(r=>r.id===Number(selected)),m=run?.metrics||{};
  $("direction").textContent=run?`Knoten ${run.plan.source} → Knoten ${run.plan.destination}${run.mode==="simulation"?" · Simulation":""}`:"Noch kein Versuch";
  const status=states[run?.state]||"Bereit";$("run-state").textContent=status;
  $("window").textContent=run?`${date(run.started_at)} · aktive Sendedauer ${number(m.elapsed_s,3)} s · ${status}${m.provisional?" · laufende Auswertung vorläufig":""}${run.error?` · ${run.error}`:""}`:"Messfenster: —";
  $("export").classList.toggle("hidden",!run);if(run)$("export").href=`/api/tests/${run.id}/export`;
  const metrics=[["Goodput",m.goodput_bps/1000,"kbit/s","Eindeutige Nutzdaten"],["Paketverlust",m.loss_pct,"%",m.provisional?"Vorläufig · Zielbericht":"Aus TX und eindeutigen RX"],["RTT",m.rtt_ms,"ms","Antwort am Sender"],["RTT-Jitter",m.jitter_ms,"ms","Mittlere |Δ RTT|"],["RSSI",m.rssi_dbm,"dBm",run?`Empfang an Knoten ${run.plan.destination}`:"Empfangsmetadaten"],["BER",null,"","Nicht messbar"]];
  if(m.goodput_bps==null)metrics[0][1]=null;
  $("metrics").innerHTML=metrics.map(([label,v,unit,note])=>`<div class="metric"><span>${label}</span><strong class="${v==null?"unavailable":""}">${label==="BER"?"nicht messbar":v==null?"—":`${number(v,2)} <small>${unit}</small>`}</strong><em>${note}</em></div>`).join("");
  const src=run?.reports[String(run.plan.source)],dst=run?.reports[String(run.plan.destination)];
  const rows=[["Sender: vom Treiber angenommene Testpakete",src?.tx],["MAC-Sendestatus erfolgreich / fehlgeschlagen",src?`${src.mac_ok} / ${src.mac_fail}`:null],["Sofortige Sende-API-Fehler",src?.send_errors],["Am Ziel eindeutig empfangen",dst?.rx_unique],["Duplikate / verspätete Pakete am Ziel",dst?`${dst.duplicates} / ${dst.late}`:null],["Anwendungsantworten / gültige RTT-Stichproben",src?`${src.app_acks} / ${src.rtt_count}`:null],["Paketzustellrate",m.delivery_pct==null?null:`${number(m.delivery_pct,2)} %`],["RX-Ereignisqueue verworfen · Sender / Ziel",src&&dst?`${src.queue_drops} / ${dst.queue_drops}`:null]];
  $("counters").innerHTML=rows.map(([k,v])=>`<div class="counter-row"><span>${k}</span><span>${esc(v)}</span></div>`).join("");
  if(!charts.radar)return;
  const keys=["ber","loss_pct","goodput_bps","rtt_ms","jitter_ms","rssi_dbm"];
  charts.radar.data.datasets[0].data=keys.map(k=>m.radar?.[k]??null);charts.radar.update("none");
  for(const [id,key,scale] of [["goodput-chart","goodput_bps",1000],["loss-chart","loss_pct",1],["rtt-chart","rtt_ms",1]]){const chart=charts[id];chart.data.datasets[0].data=(run?.samples||[]).filter(s=>s.elapsed_s!=null).map(s=>({x:s.elapsed_s,y:s[key]==null?null:s[key]/scale}));chart.update("none");}
}

function initCharts(){
  if(typeof Chart==="undefined"){error("Diagrammbibliothek konnte nicht geladen werden.");return;}
  Chart.defaults.font.family="Segoe UI, system-ui, sans-serif";Chart.defaults.color="#637680";Chart.defaults.font.size=10;
  charts.radar=new Chart($("radar"),{type:"radar",data:{labels:["BER · nicht messbar","Paketverlust","Goodput","RTT","Jitter","RSSI"],datasets:[{label:"Qualität",data:[null,null,null,null,null,null],borderColor:"#007c83",backgroundColor:"#007c8322",pointBackgroundColor:"#007c83",pointRadius:4,fill:false,spanGaps:false,borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{display:false}},scales:{r:{min:0,max:100,ticks:{stepSize:25,backdropColor:"transparent"},grid:{color:"#e2eaea"},angleLines:{color:"#e2eaea"}}}}});
  for(const [id,label,color] of [["goodput-chart","Goodput · kbit/s","#007c83"],["loss-chart","Paketverlust · %","#d66c32"],["rtt-chart","RTT · ms","#647da8"]])charts[id]=new Chart($(id),{type:"line",data:{datasets:[{label,data:[],borderColor:color,borderWidth:2,pointRadius:0,spanGaps:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,parsing:false,plugins:{legend:{display:false},title:{display:true,text:label,align:"start",padding:2}},scales:{x:{type:"linear",title:{display:true,text:"Sendedauer · s"},grid:{display:false}},y:{beginAtZero:true,max:id==="loss-chart"?100:undefined,grid:{color:"#eef2f2"}}}}});
}

function socket(){const ws=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/ws`);ws.onopen=()=>{$("socket").textContent="● Live verbunden";$("socket").className="badge live";};ws.onmessage=e=>{const event=JSON.parse(e.data);if(event.type==="state"){state=event.data;render();}};ws.onclose=()=>{$("socket").textContent="Browser-Verbindung unterbrochen";$("socket").className="badge warn";setTimeout(socket,1500);};ws.onerror=()=>ws.close();}
async function refresh(){const found=await api("/api/ports");options($("ports"),found.map(p=>[p.port,`${p.port} · ${p.description}`]),$("ports").value);}
$("refresh").onclick=()=>action(refresh);$("connect").onclick=()=>action(()=>api("/api/connect",{port:$("ports").value}));$("disconnect").onclick=()=>action(()=>api("/api/disconnect",{}));$("power-node").onchange=powerOptions;
$("power-form").onsubmit=e=>{e.preventDefault();action(async()=>{locked=true;render();try{await api("/api/configure",{powers:{[$("power-node").value]:Number($("power").value)}});}finally{locked=false;render();}});};
$("profile-form").onsubmit=e=>{e.preventDefault();action(async()=>{locked=true;render();try{await api("/api/configure",{profile:$("profile").value});}finally{locked=false;render();}});};
$("test-form").onsubmit=e=>{e.preventDefault();action(async()=>{locked=true;render();try{const run=await api("/api/tests",{source:Number($("source").value),destination:Number($("destination").value),payload_bytes:Number($("payload").value),rate_pps:Number($("rate").value),duration_s:Number($("duration").value)});selected=run.id;}finally{locked=false;render();}});};
$("stop").onclick=()=>action(()=>api(`/api/tests/${state.active}/stop`,{}));$("history").onchange=()=>{selected=Number($("history").value);results();};
initCharts();render();action(refresh);socket();
