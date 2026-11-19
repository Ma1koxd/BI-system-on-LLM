/* Часовые производственные записи. Время витрины хранится как местное время цеха. */
const BI = (() => {
  const hour = 3600000, start = Date.UTC(2026, 9, 29, 8), shifts = 42;
  const machines = ['S-101','S-102','S-201','S-202'];
  const causes = ['Сбой подачи материала','Наладка инструмента','Проверка привода'];
  const defects = ['Размер','Поверхность','Геометрия'];
  const base = {count:5, line:'Все', machine:'Все', shift:'Все', view:'shift', metric:'output',
    compare:'plan', lag:false, top:0, min:0, status:'Все', defect:'Все', since:'', until:'', offset:0};
  const rows = [];
  let seed = 23041;
  function random() {seed = seed * 16807 % 2147483647; return seed / 2147483647}
  for (let s=0; s<shifts; s++) {
    for(let h=0; h<12; h++) {
      machines.forEach((machine,m) => {
        const t=start+(s*12+h)*hour, line=m<2?'А':'Б', plan=26+(m%3)*4+(s%4);
        const troubled=(s===38 && m<2) || (s===40 && m>=2);
        let down=random()<(troubled?.23:.033)?Math.floor(12+random()*39):0;
        if(s===38 && m===1 && h===6) down=45;
        const good=Math.max(0,Math.round(plan*(1-down/60)*(.86+random()*.24)*(troubled?.82:1)));
        const bad=Math.round(good*(troubled?.12+random()*.13:.012+random()*.055));
        const a=Math.round(bad*.5), b=Math.floor((bad-a)*.65);
        const reason=causes[(s+h+m)%3], begin=t+Math.floor(random()*(61-down))*60000;
        rows.push({s,h,t,line,machine,plan,good,bad,down,begin,end:begin+down*60000,reason,
          shift:s%2?'Ночь':'День', status:(s+m)%4?'Активен':'Завершён', parts:[a,b,bad-a-b]});
      });
    }
  }
  const fmt=(n,d=0)=>Number(n).toLocaleString('ru-RU',{minimumFractionDigits:d,maximumFractionDigits:d});
  const date=(t)=>new Date(t).toLocaleDateString('ru-RU',{day:'numeric',month:'short',timeZone:'UTC'}).replace('.','');
  const iso=t=>new Date(t).toISOString().slice(0,10);
  const clock=t=>new Date(t).toISOString().slice(11,16);
  const label=s=>date(start+s*12*hour)+' · '+(s%2?'ночь':'день');
  const percent=(x,y)=>y?100*x/y:null;
  const pct=(v)=>v==null?'-':fmt(v,1)+' %';
  function select(q,week=0) {
    const end=shifts-1-(week+q.offset)*14, delta=(week+q.offset)*7*24*hour;
    return rows.filter(r=>{
      const d=iso(r.t+delta);
      const inTime=q.since||q.until?(!q.since||d>=q.since)&&(!q.until||d<=q.until):r.s<=end&&r.s>end-q.count;
      return inTime&&(q.line==='Все'||r.line===q.line)&&(q.machine==='Все'||r.machine===q.machine)
        &&(q.shift==='Все'||r.shift===q.shift)&&(q.status==='Все'||r.status===q.status);
    });
  }
  function sum(rs,defect='Все') {
    const v={good:0,bad:0,allBad:0,plan:0,down:0,capacity:rs.length*60};
    const i=defects.indexOf(defect);
    for(const r of rs){v.good+=r.good; v.plan+=r.plan; v.bad+=i<0?r.bad:r.parts[i]; v.allBad+=r.bad; v.down+=r.down}
    v.dev=v.plan?percent(v.good-v.plan,v.plan):null;
    v.rate=percent(v.bad,v.good+v.allBad);
    v.load=percent(v.capacity-v.down,v.capacity);
    v.avg=rs.length?v.good/new Set(rs.map(r=>r.t)).size:null;
    return v;
  }
  function buckets(rs,key) {
    const map=new Map(); for(const r of rs){const k=key(r); if(!map.has(k))map.set(k,[]); map.get(k).push(r)} return [...map.values()];
  }
  function analyze(q) {
    const all=select(q), prev=select(q,1), key=r=>q.view==='machine'?r.machine:q.view==='line'?r.line:`${r.s}/${r.line}`;
    const prior=new Map(prev.map(r=>[(r.s+14)+'/'+r.h+'/'+r.machine,r]));
    const earlier=rs=>rs.map(r=>prior.get(r.s+'/'+r.h+'/'+r.machine)).filter(Boolean);
    function comparison(rs){return rs.length&&rs[0].s>=14?sum(earlier(rs),q.defect):sum([],q.defect)}
    let groups=buckets(all,key).map(b=>{const p=comparison(b);return {r:b[0],v:sum(b,q.defect),prev:p.capacity?p:null,rows:b}});
    if(q.lag) groups=groups.filter(g=>g.v.dev<=-10);
    function rank(g) {if(q.lag) return g.v.dev; if(q.top || q.view==='machine') return -({output:g.v.good,quality:g.v.rate,load:g.v.load,down:g.v.down,average:g.v.avg}[q.metric]); return -g.r.s}
    groups.sort((a,b)=>rank(a)-rank(b)||a.v.dev-b.v.dev); if(q.top)groups=groups.slice(0,q.top);
    const selected=groups.flatMap(g=>g.rows).sort((a,b)=>a.t-b.t);
    const incidents=selected.filter(r=>r.down>q.min).sort((a,b)=>b.down-a.down||b.t-a.t);
    const summary=sum(selected,q.defect), events=q.view==='events';
    const previous=comparison(selected);
    return {q, groups,selected,incidents,summary,previous,events};
  }
  function trend(report,hourly) {
    const q=report.q, key=r=>hourly?r.t:r.s, delta=hourly?7*24*hour:14;
    const matched=new Set(report.selected.map(r=>(r.s-14)+'/'+r.machine+'/'+r.h));
    const prior=buckets(select(q,1).filter(r=>matched.has(r.s+'/'+r.machine+'/'+r.h)),key);
    const old=new Map(prior.map(b=>[key(b[0])+delta,sum(b,q.defect)]));
    return buckets(report.selected,key).map(b=>({r:b[0],v:sum(b,q.defect),prev:old.get(key(b[0]))}));
  }
  function parse(question,current) {
    const t=question.toLowerCase().replaceAll('ё','е').replace(/[\u2013\u2014]/g,'-'), patch={};
    if(/сброс|сначала|общий обзор/.test(t))return {...base};
    const count=t.match(/(?:последн[а-я]*\s+)?(\d+)\s*смен/);
    if(count){if(+count[1]<1||+count[1]>42)throw Error('В витрине 42 смены. Укажите число от 1 до 42.');Object.assign(patch,{count:+count[1],since:'',until:'',offset:0})}
    if(/последн[а-я]* смен[уаы]/.test(t)&&!count)Object.assign(patch,{count:1,since:'',until:'',offset:0});
    if(/вчера|сегодня|позавчера/.test(t)){const days=/позавчера/.test(t)?2:/вчера/.test(t)?1:0;const d=iso(start+shifts*12*hour-days*24*hour);Object.assign(patch,{since:d,until:d,offset:0})}
    const normalized=t.replace(/(\d{1,2})\.(\d{1,2})\.(\d{4})/g,(_,d,m,y)=>y+'-'+m.padStart(2,'0')+'-'+d.padStart(2,'0'));
    const dates=normalized.match(/\d{4}-\d{2}-\d{2}/g);
    if(dates){if(dates.length>2||dates.some(d=>!validDate(d))||dates[0]>(dates[1]||dates[0]))throw Error('Введите дату или диапазон в виде 2026-11-17 - 2026-11-18.');Object.assign(patch,{since:dates[0],until:dates[1]||dates[0],offset:0})}
    if(/ночн|ночь|ночам/.test(t))patch.shift='Ночь'; if(/дневн|днем/.test(t))patch.shift='День';
    if(/все смены|обе смены/.test(t))patch.shift='Все';
    const line=t.match(/(?:лини[а-я]*|участ[а-я]*)\s+([а-яa-z])(?=\s|$|[,.?!])/);
    if(line){const l=({a:'А',а:'А',б:'Б',b:'Б'})[line[1]];if(!l)throw Error('В витрине есть линии А и Б.');Object.assign(patch,{line:l,machine:'Все'})}
    if(/все лини|обе лини/.test(t))Object.assign(patch,{line:'Все',machine:'Все'});
    const m=t.match(/[sс]-?\s*(\d+)/); if(m){const id='S-'+m[1];if(!machines.includes(id))throw Error('Доступные станки - '+machines.join(', ')+'.');Object.assign(patch,{machine:id,line:'Все'})}
    if(/все станки/.test(t))patch.machine='Все';
    if(/прошл[а-я]* недел|предыдущ[а-я]* недел/.test(t)){
      if(/сравн|сопостав|относительно|к прошл/.test(t))patch.compare='week';
      else Object.assign(patch,{offset:1,compare:'plan',since:'',until:'',count:14});
    }
    if(/последн[а-я]* (?:7 дней|недел)|за неделю/.test(t))Object.assign(patch,{count:14,offset:0,since:'',until:''});
    if(/с планом|план.?факт/.test(t))patch.compare='plan';
    const top=t.match(/топ[\s-]*(\d+)/);
    if(top){if(+top[1]<1||+top[1]>42)throw Error('Укажите размер рейтинга от 1 до 42.');Object.assign(patch,{top:+top[1],lag:false,view:'machine'})}
    if(/по линиям|между линиями/.test(t))patch.view='line';
    if(/по сменам|между сменами|по часам|почасов/.test(t))patch.view='shift';
    if(/по станкам|оборудовани/.test(t)&&!top)patch.view='machine';
    if(/выпуск|производител|план/.test(t))patch.metric='output';
    if(/средн[а-я]* выпуск|выпуск в среднем/.test(t))patch.metric='average';
    if(/брак|дефект/.test(t))patch.metric='quality';
    if(/загруз/.test(t))patch.metric='load';
    if(/просто[йиеяю]|инцидент/.test(t)){patch.metric='down';if(!top)Object.assign(patch,{view:'events',lag:false,top:0})}
    const duration=t.match(/(?:длиннее|дольше|более|больше|свыше|>)\s*(\d+)\s*(?:мин|м\b)/);
    if(duration)patch.min=+duration[1];
    if(/отста[еюв]|отставани|отставш|ниже плана/.test(t))Object.assign(patch,{view:'shift',metric:'output',lag:true,top:0,compare:'plan'});
    if(/активн/.test(t))patch.status='Активен'; if(/завершен/.test(t))patch.status='Завершён';
    if(/все заказы/.test(t))patch.status='Все';
    if(/размер/.test(t))patch.defect='Размер'; if(/поверхност/.test(t))patch.defect='Поверхность'; if(/геометри/.test(t))patch.defect='Геометрия';
    if(patch.defect)patch.metric='quality'; if(/все причины|весь брак/.test(t))patch.defect='Все';
    if(!Object.keys(patch).length)throw Error('Уточните показатель, период или оборудование. Например, «топ-3 станка по доле брака за 5 смен».');
    return {...current,...patch};
  }
  function validDate(d){const n=Date.parse(d+'T00:00:00Z');return Number.isFinite(n)&&iso(n)===d}
  function name(g,q){return q.view==='machine'?g.r.machine:q.view==='line'?'Линия '+g.r.line:label(g.r.s)+', линия '+g.r.line}
  function report(a) {
    const {q,groups,incidents,summary:v,previous:p}=a;
    if(!groups.length)return {text:q.lag?'В выбранной группе нет отставания от плана на 10 % и более.':'Для этих условий в витрине нет записей.',tip:'Расширьте период или выберите обе линии.'};
    let text,tip;
    if(a.events){
      if(!incidents.length)return {text:'За выбранный период простоев длиннее '+q.min+' мин не зарегистрировано.',tip:'Для просмотра всех событий задайте «простои длиннее 0 минут».'};
      const r=incidents[0],vHour=sum(a.selected.filter(x=>x.t===r.t&&x.line===r.line),q.defect);text='Зафиксировано событий - '+incidents.length+'. Самый длинный простой у '+r.machine+' ('+r.down+' мин, '+date(r.begin)+', '+clock(r.begin)+'-'+clock(r.end)+'). В журнале указано «'+r.reason+'». Доля брака за час события в выборке по линии '+r.line+' - '+pct(vHour.rate)+'.';
      tip=r.reason===causes[0]?'Проверьте подачу материала на конвейере и запись об инциденте у '+r.machine+'.':'Проверьте запись о ремонте '+r.machine+' и повторяемость этой причины.';
    }else if(q.compare==='week'){
      const field=({quality:'rate',load:'load',output:'good',down:'down',average:'avg'})[q.metric], unit=({quality:' %',load:' %',output:' шт.',down:' мин',average:' шт./ч'})[q.metric];
      const digits=['rate','load','avg'].includes(field)?1:0,stop=unit.endsWith('.')?'':'.';
      text='За выбранный период показатель «'+({quality:'доля брака',load:'загрузка',output:'выпуск',down:'простои',average:'средний часовой выпуск'})[q.metric]+'» составил '+fmt(v[field],digits)+unit+stop+' '+(p.capacity?'За те же смены неделей ранее - '+fmt(p[field],digits)+unit+stop:'Для полного сравнения недостаточно данных.');tip='Сопоставьте сменные задания и состав оборудования в двух периодах.';
    }else if(q.metric==='average'){
      text='Средний выпуск за час - '+fmt(v.avg,1)+' шт. Общий выпуск за выбранные часы - '+fmt(v.good)+' шт.';tip='Сопоставьте часовой выпуск со сменным планом и отметками простоев.';
    }else if(q.metric==='quality'||q.metric==='load'||q.view==='machine'){
      const f=({quality:'rate',load:'load',down:'down',output:'good'})[q.metric],best=[...groups].sort((a,b)=>b.v[f]-a.v[f])[0];
      text='Максимум по показателю «'+({quality:'доля брака',load:'загрузка',down:'простои',output:'выпуск'})[q.metric]+'» - '+name(best,q)+': '+(f==='rate'||f==='load'?pct(best.v[f]):fmt(best.v[f])+(f==='down'?' мин':' шт.'))+'. Выпуск по выборке - '+fmt(v.good)+' шт.';
      tip=q.metric==='quality'?'Сверьте измерения с картой контроля качества и проверьте настройку инструмента.':'Сопоставьте загрузку оборудования со сменными заданиями.';
    }else{
      const w=[...groups].sort((a,b)=>a.v.dev-b.v.dev)[0];
      text=(!q.lag?'План выполнен на '+pct(percent(v.good,v.plan))+'. ':'')+(w.v.dev<0?'Наибольшее отставание':'Минимальное отклонение')+' - '+name(w,q)+'. Выпуск '+fmt(w.v.good)+' из '+fmt(w.v.plan)+' шт. ('+pct(w.v.dev)+'). Доля брака - '+pct(w.v.rate)+'.';
      if(q.lag&&groups.length>1){const n=groups[1];text+=' Далее - '+name(n,q)+' ('+pct(n.v.dev)+'), доля брака '+pct(n.v.rate)+'.'}
      tip='Сопоставьте сменное задание с журналом простоев линии '+w.r.line+' и проверьте причины брака.';
    }
    return {text,tip};
  }
  return {base,machines,causes,defects,rows,start,hour,fmt,date,iso,clock,label,pct,select,sum,analyze,trend,parse,validDate,name,report};
})();
if(typeof module!=='undefined')module.exports=BI;
