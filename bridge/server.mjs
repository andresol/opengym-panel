import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { snapshot, VERSION } from './model.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const equal=(a,b)=>{const x=Buffer.from(a||''),y=Buffer.from(b||'');return x.length===y.length&&x.length>0&&crypto.timingSafeEqual(x,y);};
export function makeServer({token,uid,dataDir,now=()=>new Date()}) {
  if(!token || token.length<32 || !/^[A-Za-z0-9_-]{8,80}$/.test(uid||'')) throw new Error('Invalid panel configuration');
  const statePath=path.join(path.resolve(dataDir),`state-${uid}.json`);
  const assets={'/':['index.html','text/html; charset=utf-8'],'/app.js':['app.js','text/javascript; charset=utf-8'],'/style.css':['style.css','text/css; charset=utf-8'],'/demo.json':['demo.json','application/json'],'/font.ttf':['../firmware/fonts/DejaVuSans.ttf','font/ttf']};
  const server=http.createServer((req,res)=>{
    res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Frame-Options','DENY');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Robots-Tag','noindex, nofollow');
    res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
    const json=(code,obj)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(obj));};
    if(req.method!=='GET') return json(405,{error:'Read only'});
    let url;try{url=new URL(req.url,'http://panel.local');}catch{return json(400,{error:'Bad request'});}
    if(url.pathname==='/health'&&!url.search) return json(200,{ok:true,version:VERSION});
    if(url.pathname==='/api/plan') {
      if(!equal(req.headers.authorization,`Bearer ${token}`)) return json(401,{error:'Unauthorized'});
      if([...url.searchParams.keys()].some(k=>k!=='day') || url.searchParams.getAll('day').length>1) return json(400,{error:'Invalid query'});
      const d=url.searchParams.get('day'); if(d!==null&&!/^[0-6]$/.test(d)) return json(400,{error:'Invalid day'});
      try {
        const fd=fs.openSync(statePath,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
        let raw;try{const st=fs.fstatSync(fd);if(!st.isFile()||st.size>8*1024*1024) throw new Error('invalid file'); raw=JSON.parse(fs.readFileSync(fd,'utf8'));}finally{fs.closeSync(fd);}
        const data=snapshot(raw,d===null?null:Number(d),now());
        if(Buffer.byteLength(JSON.stringify(data))>48000) throw new Error('response too large');
        return json(200,data);
      } catch {return json(503,{error:'OpenGym unavailable'});}
    }
    if(url.search||!Object.hasOwn(assets,url.pathname)) return json(404,{error:'Not found'});
    const [file,type]=assets[url.pathname];
    try{const data=fs.readFileSync(path.join(root,'web',file));res.writeHead(200,{'Content-Type':type});res.end(data);}catch{return json(503,{error:'Asset unavailable'});}
  });
  server.requestTimeout=5000;server.headersTimeout=5000;server.keepAliveTimeout=2000;server.maxConnections=12;
  return server;
}
if(process.argv[1]===fileURLToPath(import.meta.url)) {
  const config=JSON.parse(fs.readFileSync(process.env.PANEL_CONFIG||'/run/panel/config.json','utf8'));
  makeServer({...config,dataDir:process.env.DATA_DIR||'/data'}).listen(Number(process.env.PORT||8891),process.env.HOST||'0.0.0.0',()=>console.log(`OpenGym Panel ${VERSION} ready (read-only)`));
}
