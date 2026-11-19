// Запуск: node server.cjs. Локальные запросы к Ollama выполняются только с сервера.
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const BI = require('./dist/engine.js');
const model = process.env.OLLAMA_MODEL || '';
const port = Number(process.env.PORT || 8765);
const enumOf = (...values) => ({type:'string', enum:values});
const integer = (minimum, maximum) => ({type:'integer', minimum, maximum});
const schema = {type:'object', additionalProperties:false, properties:{
  supported:{type:'boolean'}, count:integer(1,42), line:enumOf('Все','А','Б'),
  machine:enumOf('Все',...BI.machines), shift:enumOf('Все','День','Ночь'),
  view:enumOf('shift','line','machine','events'), metric:enumOf('output','quality','load','down','average'),
  compare:enumOf('plan','week'), lag:{type:'boolean'}, top:integer(0,42), min:integer(0,720),
  status:enumOf('Все','Активен','Завершён'), defect:enumOf('Все',...BI.defects),
  since:{type:'string'}, until:{type:'string'}, offset:integer(0,1),
  hourly:{type:'boolean'}
}};
schema.required = Object.keys(schema.properties);
function valid(q) {
  return q && typeof q==='object' && !Object.keys(q).some(k=>!schema.required.includes(k)) && schema.required.every(k=>{
    const r=schema.properties[k],v=q[k];
    if(r.enum)return r.enum.includes(v);
    if(r.type==='integer')return Number.isInteger(v)&&v>=r.minimum&&v<=r.maximum;
    if(k==='since'||k==='until')return v===''||(typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&BI.validDate(v));
    return typeof v===r.type;
  }) && (!q.since||!q.until||q.since<=q.until);
}
const instruction = 'Ты планировщик русскоязычной BI-системы. Верни полный план по JSON Schema. Сохраняй контекст уточняющих вопросов. Опорное время 19.11.2026 08:00. Витрина с 29.10.2026 08:00 по 19.11.2026 08:00. count - число последних завершённых смен по 12 ч; offset=1 сдвигает окно на неделю, compare=week сравнивает одинаковые смены с неделей ранее. since и until - даты включительно в формате YYYY-MM-DD или пустые строки. lag означает отставание не менее 10%, топ=0 отключает рейтинг; для топ станков view=machine. min - строгая нижняя граница длительности отдельного простоя в минутах, view=events. Для выпуска, брака, загрузки и простоев используй соответственно output, quality, load, down. Доля брака конкретной причины использует общий знаменатель. hourly - почасовой график. При неизвестных сущностях, неподдерживаемой задаче или недостатке сведений supported=false. Не вычисляй чисел отчёта.';
async function plan(question,context){
  const res=await fetch('http://127.0.0.1:11434/api/chat',{method:'POST',signal:AbortSignal.timeout(90000),
    headers:{'Content-Type':'application/json'},body:JSON.stringify({model,stream:false,format:schema,options:{temperature:0},
      messages:[{role:'system',content:instruction+' Схема '+JSON.stringify(schema)},
        {role:'user',content:JSON.stringify({context,question})}]})});
  if(!res.ok)throw Error();
  const q=JSON.parse((await res.json()).message.content);
  if(!valid(q))throw Error();
  return q;
}
const assets={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js','/engine.js':'engine.js'};
function json(res,status,data){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data))}
http.createServer(async(req,res)=>{
  const url=req.url.split('?')[0];
  try{
    if(url==='/api/config'&&req.method==='GET')return json(res,200,{model});
    if(url==='/api/plan'&&req.method==='POST'){
      if(!model)return json(res,503,{error:'Модель не настроена.'});
      if(req.headers.origin&&req.headers.origin!=='http://'+req.headers.host)return json(res,403,{error:'Недопустимый источник.'});
      req.setEncoding('utf8');
      let body='';for await(const part of req){body+=part;if(body.length>10000)return json(res,413,{error:'Слишком длинный запрос.'})}
      let input;try{input=JSON.parse(body)}catch{return json(res,400,{error:'Проверьте запрос.'})}
      if(typeof input?.question!=='string'||!input.question.trim()||input.question.length>1500)return json(res,400,{error:'Введите вопрос до 1500 символов.'});
      return json(res,200,await plan(input.question,input.context));
    }
    if(req.method!=='GET'||!Object.hasOwn(assets,url))return json(res,404,{error:'Страница не найдена.'});
    const f=assets[url],body=await fs.readFile(path.join(__dirname,'dist',f));
    res.writeHead(200,{'Content-Type':({'html':'text/html','js':'text/javascript','css':'text/css'})[f.split('.').pop()]+'; charset=utf-8'});res.end(body);
  }catch{return json(res,502,{error:'Ollama не вернула корректный план. Проверьте имя модели и локальный сервис.'})}
}).listen(port,'127.0.0.1',()=>console.log('http://127.0.0.1:'+port));
