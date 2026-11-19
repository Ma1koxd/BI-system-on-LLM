'use strict';
const $=id=>document.getElementById(id);
const paths={
  factory:'<path d="M3 21V9l6 3V8l6 4V4h4l2 17zM7 16h1m4 0h1m4 0h1"/>',
  layers:'<path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v5m10-5v5M3 11h18"/>',
  output:'<path d="m3.5 7.5 8.5-5 8.5 5v9L12 22l-8.5-5.5zM4 7.5l8 5 8-5M12 12.5V22M8 5l8 5"/>',
  quality:'<path d="M12 2.5 20 6v6c0 4-3.5 7-8 9.5C7.5 19 4 16 4 12V6zM12 8v5m0 3h.01"/>',
  down:'<circle cx="12" cy="12" r="9"/><path d="M12 6.5v6l4 2"/>',
  load:'<path d="M3 18a10 10 0 0 1 18 0M12 16l5-7M5 13l2 1m4-6v2"/><circle cx="12" cy="16" r="2"/>',
  spark:'<path d="m10 3 2.2 6.8L19 12l-6.8 2.2L10 21l-2.2-6.8L1 12l6.8-2.2zM19 2l.9 2.2L22 5l-2.1.8L19 8l-.8-2.2L16 5l2.2-.8z"/>',
  reset:'<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',send:'<path d="m3 4 18 8-18 8 3-8zM6 12h15"/>',
  user:'<circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>'};
const icon=k=>'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths[k]+'</svg>';
document.querySelectorAll('[data-icon]').forEach(el=>el.innerHTML=icon(el.dataset.icon));
let q={...BI.base}, hourly=false, page=0, current, model='', sequence=0;
const {fmt,pct}=BI, fields={output:'good',quality:'rate',load:'load',down:'down',average:'avg'};
const metricNames={output:'Выпуск продукции',quality:'Доля брака',load:'Загрузка оборудования',down:'Простои оборудования',average:'Средний выпуск за час'};
const unit={output:'шт.',quality:'%',load:'%',down:'мин',average:'шт./ч'};
function spark(points,color) {
  if(points.length<2)return '';
  const min=Math.min(...points),range=Math.max(...points)-min||1;
  const d=points.map((v,i)=>(i?'L':'M')+(1+i*92/(points.length-1)).toFixed(1)+' '+(26-21*(v-min)/range).toFixed(1)).join(' ');
  return '<svg class="sparkline" viewBox="0 0 94 30" aria-hidden="true" preserveAspectRatio="none"><path d="'+d+' L93 30H1Z" fill="'+color+'" opacity=".09"/><path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>';
}
function renderKpis(a){
  const v=a.summary,tr=BI.trend(a,false),has=v.capacity>0;
  const items=[
    ['output','Выпуск продукции',fmt(v.good),'шт.','План '+fmt(v.plan)+' шт.','#cc6937','#fbecdf'],
    ['quality','Доля брака',fmt(v.rate||0,1),'%',fmt(v.bad)+' шт. брака','#a55b55','#f8e9e5'],
    ['down','Простои',fmt(v.down),'мин',a.selected.filter(r=>r.down>0).length+' событий','#9d772f','#f7efdc'],
    ['load','Загрузка станков',fmt(v.load||0,1),'%','По машино-часам','#477863','#e6eee6']];
  $('kpis').innerHTML=items.map(([k,n,val,u,f,c,bg])=>`<button class="kpi" data-k="${k}" aria-label="Показать график: ${n}"><span class="kpi-head"><span class="tileicon" style="background:${bg};color:${c}">${icon(k)}</span>${n}</span><div class="k-value">${has?val:'-'}<small>${u}</small></div><div class="k-foot">${f}</div>${spark(tr.map(x=>x.v[fields[k]]),c)}</button>`).join('');
}
function renderContext(){
  const flags=[q.shift!=='Все'&&q.shift,q.machine!=='Все'&&q.machine,q.status!=='Все'&&('Заказ · '+q.status),q.defect!=='Все'&&('Брак · '+q.defect),q.lag&&'Отставание ≥ 10 %',q.top>0&&('Топ-'+q.top),q.compare==='week'&&'Сравнение с прошлой неделей',q.offset===1&&'Неделей ранее',q.view==='events'&&q.min>0&&('События > '+q.min+' мин')].filter(Boolean);
  $('context').innerHTML=flags.map(f=>'<span>'+f+'</span>').join('')+(flags.length?'<button id="clearContext">Сбросить фильтры</button>':'');
  if($('clearContext'))$('clearContext').onclick=()=>change({...BI.base},'Сброшены фильтры.');
  $('line').value=q.line;
  const count=$('count'), val=q.since||q.until?'date':String(q.count);
  count.querySelectorAll('[data-custom]').forEach(el=>el.remove());
  if(![...count.options].some(o=>o.value===val)){const o=new Option(val==='date'?'Выбранные даты':q.count+' смен',val);o.dataset.custom='1';count.add(o)}
  count.value=val;
}
function renderChart(a){
  const k=q.metric, field=fields[k], data=BI.trend(a,hourly), week=q.compare==='week';
  const baseline=week?'Неделей ранее':k==='output'?'План':'', stops=hourly&&data.some(b=>b.v.down>0);
  $('chartTitle').textContent=metricNames[k]; $('legend').innerHTML='<span><i class="swatch"></i>'+ (k==='output'?'Факт':metricNames[k])+'</span>'+(baseline?'<span><i class="swatch dash"></i>'+baseline+'</span>':'')+(stops?'<span><i class="swatch dot"></i>Простой</span>':'');
  $('shiftChart').setAttribute('aria-pressed',String(!hourly));$('hourChart').setAttribute('aria-pressed',String(hourly));
  if(!data.length){$('chart').innerHTML='<div class="empty">Нет точек для выбранной выборки</div>';$('chartNote').textContent='Измените период или фильтры.';return}
  const width=Math.max(315,$('chart').clientWidth-28),H=215,L=49,R=width-21,T=24,B=167;
  const series=data.map(b=>b.v[field]),comparison=data.map(b=>week?(b.prev?.[field]??null):k==='output'?b.v.plan:null);
  const lo=Math.max(1,...series,...comparison.filter(n=>n!=null)),order=10**Math.floor(Math.log10(lo)),step=Math.ceil(lo/4/(order/5))*(order/5),high=step*4;
  const X=i=>data.length===1?(L+R)/2:L+(R-L)*i/(data.length-1),Y=v=>B-v/high*(B-T);
  const coord=(i,v)=>X(i).toFixed(1)+','+Y(v).toFixed(1), line=series.map((v,i)=>(i?'L':'M')+coord(i,v)).join(' ');
  let s='<defs><linearGradient id="fill" x1="0" x2="0" y1="0" y2="1"><stop stop-color="#ed9a69" stop-opacity=".38"/><stop offset="1" stop-color="#f7cdb0" stop-opacity=".10"/></linearGradient></defs>';
  for(let j=0;j<=4;j++){const v=high*j/4,y=Y(v);s+=`<path d="M${L} ${y}H${R}" stroke="#e1e6de" stroke-dasharray="3 4"/><text x="${L-8}" y="${y+4}" text-anchor="end">${fmt(v,v<10&&v%1?1:0)}</text>`}
  s+=`<text x="${L-8}" y="13" text-anchor="end">${unit[k]}</text><path d="${line}L${X(series.length-1)},${B}L${X(0)},${B}Z" fill="url(#fill)"/>`;
  if(baseline){
    const reference=comparison.map((v,i)=>v==null?'':(i&&comparison[i-1]!=null?'L':'M')+coord(i,v)).join(' ');
    if(!week&&hourly&&data.length>1){const band=comparison.map((v,i)=>(i?'L':'M')+coord(i,v)).join(' ')+comparison.map((_,i)=>{const j=comparison.length-i-1;return 'L'+coord(j,comparison[j]*.9)}).join(' ')+'Z';s+='<path d="'+band+'" fill="#7f96b0" opacity=".14"/>'}
    s+='<path d="'+reference+'" fill="none" stroke="#7f8fa6" stroke-width="2" stroke-dasharray="6 5"/>';
  }
  s+='<path d="'+line+'" fill="none" stroke="#d7672f" stroke-width="2.8" stroke-linejoin="round"/>';
  const stride=Math.max(1,Math.ceil((data.length-1)/Math.max(2,Math.floor((R-L)/95))));
  data.forEach((b,i)=>{
    const x=X(i),y=Y(series[i]),caption=hourly?BI.date(b.r.t)+' '+BI.clock(b.r.t):BI.label(b.r.s);
    const digits=['quality','load','average'].includes(k)?1:0;
    const diff=i>0&&data[i-1].r.t+BI.hour===b.r.t?series[i]-series[i-1]:null;
    const tooltip=caption+' · '+metricNames[k]+' '+fmt(series[i],digits)+' '+unit[k]+(comparison[i]!=null?' · '+baseline+' '+fmt(comparison[i],digits)+' '+unit[k]:'')+(hourly&&diff!=null?' · К прошлому часу '+(diff>0?'+':'')+fmt(diff,digits)+' '+(unit[k]==='%'?'п.п.':unit[k]):'')+(b.v.down?' · Простой '+b.v.down+' маш.-мин':'');
    if(data.length<=20)s+=`<circle cx="${x}" cy="${y}" r="${b.v.dev<=-10&&k==='output'?5:3.5}" stroke="#fff" stroke-width="1.8" fill="${b.v.dev<=-10&&k==='output'?'#ab4926':'#d7672f'}"/>`;
    if(stops&&b.v.down){s+=`<path d="M${x},${B-7}l3.5,3.5 -3.5,3.5 -3.5,-3.5Z" fill="#aa4834"/>`}
    s+=`<rect x="${x-Math.max(1,Math.min(14,(R-L)/data.length/2))}" y="${T}" width="${Math.max(2,Math.min(28,(R-L)/data.length))}" height="${B-T}" fill="transparent"><title>${tooltip}</title></rect>`;
    if(i===0||i===data.length-1||i%stride===0&&data.length-1-i>=stride*.65){
      const anchor=i===0?'start':i===data.length-1?'end':'middle';
      s+=`<text x="${x}" y="${B+18}" text-anchor="${anchor}">${hourly?BI.clock(b.r.t):BI.date(b.r.t)}</text><text x="${x}" y="${B+35}" text-anchor="${anchor}">${hourly?BI.date(b.r.t):b.r.shift}</text>`;
    }
  });
  $('chart').innerHTML=`<svg viewBox="0 0 ${width} ${H}" preserveAspectRatio="none" role="img" aria-label="${metricNames[k]} ${hourly?'по часам':'по сменам'}">${s}</svg>`;
  const v=a.summary;
  $('chartNote').textContent=week?'Сопоставлены те же смены и станки со сдвигом на семь дней.':hourly&&k==='output'?'Зона плана соответствует 90-100 % часового задания. Ромбы отмечают часы с простоем.':k==='output'?'Выполнение плана за период - '+pct(v.plan?100*v.good/v.plan:null)+'.':k==='down'?'Длительность суммируется по станкам, в машино-минутах.':k==='quality'?'Доля брака рассчитана от общего числа изготовленных деталей.':k==='average'?'Выпуск разделён на количество представленных часов.':'Загрузка рассчитана по доступному времени оборудования.';
}
function renderTable(a){
  const events=a.events,items=events?a.incidents:a.groups, week=q.compare==='week',field=fields[q.metric];
  const title=events?'Журнал простоев':q.view==='machine'?'Показатели по станкам':q.view==='line'?'Показатели по линиям':'Показатели по сменам';
  $('tableTitle').textContent=title;$('rowCount').textContent=items.length+' строк';
  const headers=events?['Начало','Конец','Линия','Станок','Мин','Причина']: [(q.view==='machine'?'Станок':q.view==='line'?'Линия':'Смена'),...(q.view==='line'?[]:['Линия']),'Выпуск','План','Откл.','Брак, %','Простой, мин',...(q.metric==='load'?['Загрузка, %']:[]),...(week?['Нед. ранее, '+unit[q.metric]]:[])];
  if(!events&&q.metric==='average')headers.splice(week?-1:headers.length,0,'Среднее, шт./ч');
  const cells=items.slice(page*6,page*6+6).map(g=>{
    if(events)return [BI.date(g.begin)+' '+BI.clock(g.begin),BI.clock(g.end),g.line,g.machine,g.down,g.reason];
    const {r,v}=g,dev=v.dev;return [q.view==='machine'?r.machine:q.view==='line'?'Линия '+r.line:BI.label(r.s),...(q.view==='line'?[]:[r.line]),fmt(v.good),fmt(v.plan),'<span class="'+(dev<=-10?'bad':dev>=0?'ok':'')+'">'+(dev>0?'+':'')+pct(dev)+'</span>',fmt(v.rate,1),fmt(v.down),...(q.metric==='load'?[fmt(v.load,1)]:[]),...(q.metric==='average'?[fmt(v.avg,1)]:[]),...(week?[g.prev?fmt(g.prev[field],['rate','load','avg'].includes(field)?1:0):'-']:[])];
  });
  $('table').innerHTML='<thead><tr>'+headers.map(h=>'<th scope="col">'+h+'</th>').join('')+'</tr></thead><tbody>'+(cells.length?cells.map(c=>'<tr>'+c.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join(''):'<tr><td class="empty" colspan="'+headers.length+'">Нет подходящих записей</td></tr>')+'</tbody>';
  $('pager').innerHTML=items.length>6?`<span>${page*6+1}-${Math.min(page*6+6,items.length)} из ${items.length}</span><div><button id="back" ${page===0?'disabled':''}>Назад</button> <button id="next" ${(page+1)*6>=items.length?'disabled':''}>Далее</button></div>`:'';
  if($('back')){$('back').onclick=()=>{page--;renderTable(a)};$('next').onclick=()=>{page++;renderTable(a)}}
}
function render(){
  page=0;current=BI.analyze(q);renderContext();renderKpis(current);renderChart(current);renderTable(current);
  const nav=q.view==='line'?'shift':q.view;document.querySelectorAll('[data-nav]').forEach(b=>b.classList.toggle('active',b.dataset.nav===nav));
  $('pageTitle').textContent=nav==='events'?'Анализ простоев':nav==='machine'?'Анализ оборудования':'Производственная сводка';
  const rs=BI.select(q);
  $('period').textContent=rs.length?BI.date(rs[0].t)+' '+BI.clock(rs[0].t)+' - '+BI.date(rs.at(-1).t+BI.hour)+' '+BI.clock(rs.at(-1).t+BI.hour)+' 2026 · '+(q.line==='Все'?'Линии А и Б':'Линия '+q.line):'Нет смен за выбранный период';
}
function message(who,body,tip=''){
  const el=document.createElement('article');el.className='msg '+who;
  el.innerHTML='<div class="msg-meta">'+(who==='user'?'Вы <span class="person-icon">'+icon('user')+'</span>':'<span class="boticon">'+icon('spark')+'</span> Такт')+'</div><div class="msg-text"></div>';
  el.lastChild.textContent=body;
  if(tip){const block=document.createElement('div');block.className='takeaway';const title=document.createElement('strong');title.textContent='Рекомендация';block.append(title,document.createTextNode(tip));el.append(block)}
  $('conversation').append(el);$('conversation').scrollTop=$('conversation').scrollHeight;
}
function answer(){const result=BI.report(current);message('bot',result.text,result.tip)}
function change(next,user){sequence++;$('send').disabled=false;q=next;render();message('user',user);answer()}
function init(){++sequence;modelLabel();$('send').disabled=false;q={...BI.base};hourly=false;$('conversation').replaceChildren();$('question').value='';render();message('user','Как цех выполнил план за последние 5 смен?');answer()}
function modelLabel(){ $('mode').textContent=model?'LLM · '+model:'Демонстрационный режим' }
async function ask(text){
  const t=text.trim().replace(/[\u2013\u2014]/g,'-');if(!t||$('send').disabled)return;
  $('question').value='';message('user',t);const id=++sequence;$('send').disabled=true;
  let next,h=hourly;
  try{
    if(model){
      $('mode').textContent='Разбираю вопрос…';
      const res=await fetch('/api/plan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:t,context:{...q,hourly}})});
      const data=await res.json();if(!res.ok)throw Error(data.error||'Ошибка сервиса Ollama.');
      if(!data.supported)throw Error('Уточните период, показатель или оборудование. Модель не смогла сопоставить запрос с витриной.');
      const {supported,hourly:byHour,...plan}=data;h=byHour;next=plan;
    }else{
      next=BI.parse(t,q);if(/по часам|почасов/i.test(t))h=true;else if(/по сменам|между сменами|сброс|сначала/i.test(t))h=false;
    }
    if(sequence!==id)return;q=next;hourly=h;render();answer();
  }catch(e){if(sequence===id)message('bot',e.message)}
  finally{if(sequence===id){$('send').disabled=false;modelLabel()}}
}
$('ask').onsubmit=e=>{e.preventDefault();ask($('question').value)};
$('question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask($('question').value)}};
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>ask(b.dataset.prompt));
$('kpis').onclick=e=>{const k=e.target.closest('[data-k]')?.dataset.k;if(k)change({...q,metric:k,view:k==='down'?'events':q.view==='events'?'shift':q.view},'Показать показатель «'+metricNames[k]+'».')};
document.querySelectorAll('[data-nav]').forEach(b=>b.onclick=()=>{const view=b.dataset.nav;change({...q,view,metric:view==='events'?'down':'output',lag:false,top:0,min:0},'Открыть раздел «'+b.textContent+'».')});
$('brand').onclick=e=>{e.preventDefault();init()};$('reset').onclick=init;
$('line').onchange=e=>change({...q,line:e.target.value,machine:'Все'},e.target.selectedOptions[0].text);
$('count').onchange=e=>change({...q,count:Number(e.target.value),since:'',until:'',offset:0},e.target.selectedOptions[0].text);
$('shiftChart').onclick=()=>{hourly=false;renderChart(current)};$('hourChart').onclick=()=>{hourly=true;renderChart(current)};
$('method').onclick=$('help').onclick=()=>$('about').showModal();$('close').onclick=()=>$('about').close();
init();
if(['localhost','127.0.0.1'].includes(location.hostname))fetch('/api/config').then(r=>r.json()).then(d=>{model=typeof d.model==='string'?d.model:'';modelLabel()}).catch(()=>{});
new ResizeObserver(()=>renderChart(current)).observe($('chart'));
