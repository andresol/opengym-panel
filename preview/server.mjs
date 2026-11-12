import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {snapshot} from '../bridge/model.mjs';
import {CATALOGUE} from '../vendor/opengym/frontend/src/lib/exercises.js';
import {names} from './names.mjs';
export const VERSION='1.1.0-preview.1';
const root=path.dirname(fileURLToPath(import.meta.url));
const equal=(a,b)=>{const x=Buffer.from(a||''),y=Buffer.from(b||'');return x.length===y.length&&x.length>0&&crypto.timingSafeEqual(x,y);};
const legacyMedia=JSON.parse(fs.readFileSync(path.join(root,'../native/catalogue-media.json')));
const publicMedia=new Set(legacyMedia.map(file=>`/media/${file}`));
const virtualMedia=new Map(legacyMedia.map(file=>{
 const match=file.match(/^(img|gif)\/([0-9]+)-[^/]+\.(jpg|gif|png)$/);
 return match?[`/media/${match[1]}/v140-${match[2]}.${match[1]==='img'?'jpg':'gif'}`,`/media/${file}`]:[null,null];
}).filter(([key])=>key));
function readFile(file,max){
 const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);
 try{const st=fs.fstatSync(fd);if(!st.isFile()||st.size>max)throw Error('Invalid file');return fs.readFileSync(fd);}finally{fs.closeSync(fd);}
}
export function makePreviewServer({token,profiles=[],dataDir,mediaDir=path.join(root,'media'),now=()=>new Date()}={}){
 if(profiles.length && (!token||token.length<32||!dataDir))throw Error('Missing private configuration');
 const bindings=new Map();
 for(const p of profiles){
  if(!/^[a-z][a-z0-9-]{0,30}$/.test(p.slug)||!/^[A-Za-z0-9_-]{8,80}$/.test(p.uid)||!p.name||bindings.has(p.slug))throw Error('Invalid profile binding');
  bindings.set(p.slug,p);
 }
 const assets={'/':['index.html','text/html; charset=utf-8'],'/app.js':['app.js','text/javascript; charset=utf-8'],'/style.css':['style.css','text/css; charset=utf-8'],'/demo.mjs':['demo.mjs','text/javascript; charset=utf-8'],'/font.ttf':['../firmware/fonts/DejaVuSans.ttf','font/ttf']};
 const server=http.createServer((req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Frame-Options','DENY');res.setHeader('Referrer-Policy','no-referrer');res.setHeader('X-Robots-Tag','noindex, nofollow');
  res.setHeader('Content-Security-Policy',"default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  const json=(code,obj)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(obj));};
  if(req.method!=='GET')return json(405,{error:'Read only'});
  let u;try{u=new URL(req.url,'http://panel.local');}catch{return json(400,{error:'Bad request'});}
  if(u.pathname==='/health'&&!u.search)return json(200,{ok:true,version:VERSION,preview:true});
  if(u.pathname.startsWith('/api/')){
   if(!token||!equal(req.headers.authorization,`Bearer ${token}`))return json(401,{error:'Unauthorized'});
   if(u.pathname==='/api/profiles'&&!u.search)return json(200,{profiles:profiles.map(({slug,name})=>({slug,name}))});
   const m=u.pathname.match(/^\/api\/profiles\/([a-z][a-z0-9-]{0,30})\/plan$/);
   if(!m||!bindings.has(m[1]))return json(404,{error:'Unknown profile'});
   if([...u.searchParams.keys()].some(k=>k!=='day')||u.searchParams.getAll('day').length>1)return json(400,{error:'Invalid query'});
   const d=u.searchParams.get('day');if(d!==null&&!/^[0-6]$/.test(d))return json(400,{error:'Invalid day'});
   const p=bindings.get(m[1]);
   try{
    const raw=JSON.parse(readFile(path.join(path.resolve(dataDir),`state-${p.uid}.json`),8*1024*1024));
    const data=snapshot(raw,d===null?null:Number(d),now(),{profile:p.name,enhanced:true,mediaAliases:p.mediaAliases,names});
    data.profileSlug=p.slug;data.previewVersion=VERSION;
    if(Buffer.byteLength(JSON.stringify(data))>64000)throw Error('Oversized plan');
    return json(200,data);
   }catch{return json(503,{error:'OpenGym unavailable'});}
  }
  if(u.search)return json(404,{error:'Not found'});
  if(publicMedia.has(u.pathname)||virtualMedia.has(u.pathname)){
   const drawing = '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="360" viewBox="0 0 512 360"><rect width="512" height="360" fill="#17191b"/><g fill="#b8ee56"><rect x="190" y="165" width="132" height="14"/><rect x="164" y="110" width="24" height="122" rx="6"/><rect x="188" y="110" width="24" height="122" rx="6"/><rect x="300" y="110" width="24" height="122" rx="6"/><rect x="324" y="110" width="24" height="122" rx="6"/></g><text x="256" y="280" text-anchor="middle" fill="white" font-family="sans-serif" font-size="18">No exercise illustration</text></svg>';
   res.writeHead(200, {'Content-Type': 'image/svg+xml', 'Cache-Control': 'public, max-age=86400'});
   return res.end(drawing);
  }
  if(!Object.hasOwn(assets,u.pathname))return json(404,{error:'Not found'});
  const [file,type]=assets[u.pathname];try{const data=fs.readFileSync(path.join(root,file));res.writeHead(200,{'Content-Type':type});res.end(data);}catch{return json(503,{error:'Asset unavailable'});}
 });
 server.requestTimeout=5000;server.headersTimeout=5000;server.keepAliveTimeout=2000;server.maxConnections=24;
 return server;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 const config=process.env.PANEL_CONFIG?JSON.parse(fs.readFileSync(process.env.PANEL_CONFIG)):{};
 makePreviewServer({...config,dataDir:process.env.DATA_DIR,mediaDir:process.env.MEDIA_DIR}).listen(Number(process.env.PORT||8892),process.env.HOST||'127.0.0.1',()=>console.log(`OpenGym ${VERSION} (read-only preview)`));
}
