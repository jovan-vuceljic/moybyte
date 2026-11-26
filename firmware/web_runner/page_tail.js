
// ---- web runner transport tail (#151, threading #176) ------------------------
// The console runs in a WORKER (worker.js) and PUSHES frames; THIS thread only
// blits. It used to step the console inside the rAF callback, which put ~7ms of
// console work + ~2ms of blit on a 16.7ms budget -- so a worst-case frame
// (full repaint, GC sweep) missed vsync and dropped.
//
// Since moycore stage 4 a frame is a finished RGB565 FRAMEBUFFER (the wasm
// rasterizes with the boards' own kernel) plus a small metadata object. The
// page's JS draw-command replayer is gone, and with it the per-surface delta,
// the keyframe/resync protocol and the /assets pixel payload: a frame is
// self-contained, so dropping one costs exactly one stale frame.
//
// The worker paces itself at 60fps, so this loop has no frame gate: rAF presents
// the most recent frame and DROPS stale ones (a slow main thread must never make
// frames queue up).
var WORKER=null,pendingFrame=null,pendingFB=null,assetsJSON=null,assetsWait=[],
gotAssets=false,assetsBusy=false,assetsAt=0;
// Assets are METADATA now (size, title, audio rate, input hint) -- a few dozen
// bytes, fetched on a cart change rather than per missing cover. The coalescing
// throttle stays because a cart change and a reload can land together.
var ASSETS_MIN_MS=1000;
function fetchAssets(){
return new Promise(function(res,rej){
var now=Date.now();
if(!WORKER){if(assetsJSON)res(JSON.parse(assetsJSON));else assetsWait.push([res,rej]);return;}
if(assetsJSON&&(assetsBusy||now-assetsAt<ASSETS_MIN_MS)){res(JSON.parse(assetsJSON));return;}
assetsWait.push([res,rej]);
assetsBusy=true;assetsAt=now;
WORKER.postMessage({t:"assets"});});}
// The console's `state` -- the dev channel's snapshot, the keys an on-glass
// suite reads -- for a harness driving this page: a promise of the object.
var stateWait=[];
window.__moyState=function(){return new Promise(function(ok){stateWait.push(ok);
WORKER.postMessage({t:"state"});});};
function onWorker(m){
if(m.t==="status"){sEl.textContent=m.s;pinSaid(m.s);}
else if(m.t==="assets"){assetsJSON=m.json;assetsBusy=false;
if(assetsWait.length){var ws=assetsWait;assetsWait=[];
for(var i=0;i<ws.length;i++)ws[i][0](JSON.parse(m.json));}
// An UNREQUESTED push is the dev hot-reload's fresh cart: re-run getA() so the
// new title/size/input hint land (the cart title may be unchanged, so df()'s
// own detection never fires).
else if(gotAssets&&typeof getA==="function"){getA().catch(function(){});}
gotAssets=true;}
// Keep only the NEWEST frame. A superseded framebuffer goes straight back to the
// worker's pool -- it is a transferable, so holding it here would starve the
// ping-pong and force a fresh 1.2MB allocation on the next painted frame.
else if(m.t==="clip"){clipOut(m.s);}
else if(m.t==="ask"){asks(m.a);}
else if(m.t==="frame"){
if(pendingFB&&WORKER)WORKER.postMessage({t:"fbret",b:pendingFB},[pendingFB]);
pendingFrame=m.s;pendingFB=m.fb||null;}
// The worker's own account of where the carts went, kept where a probe (or a
// devtools console) can read it -- console logs get trimmed by whatever is
// capturing them, and this is the evidence that the store is being written.
else if(m.t==="persist"){window.__moyPersist={mode:m.mode,s:m.s,d:m.d||"",n:m.n||0};
pzMode(m.mode,m.s);if(m.mode==="board")linkState("signed-in",m.s);}
else if(m.t==="keep"){pzKeep();}
else if(m.t==="carts"){pzFill(m.names);}
else if(m.t==="exported"){pzDownload(m.name,m.buf);}
else if(m.t==="imported"){window.__moyImported=m.s;if(m.ok)pzAsk();
if(m.report)p8Report(m.report,m.ok,m.dir);else pzSay(m.s,!m.ok);}
else if(m.t==="update"){updBound(m);}
else if(m.t==="edited"){window.__moyEdited=m.s;pzSay(m.s,!m.ok);}
else if(m.t==="pair"){pinAsk(m);linkState("sign-in",m.wait||m.why||"");}
else if(m.t==="claimed"){claimed(m);}
else if(m.t==="key"){keyGot(m);}
else if(m.t==="unkey"){keyDrop(m.id);}
else if(m.t==="wait"){linkWait(m.s);}
else if(m.t==="pod"){podSaid(m.s);}
else if(m.t==="pick"){pkAsk(m);}
else if(m.t==="unpick"){pkDone(m.id);}
else if(m.t==="installed"){window.__moyInstalled=m.folder;}
else if(m.t==="state"){var sw=stateWait;stateWait=[];
var so=JSON.parse(m.json);if(so&&typeof so==="object"){so.sink=m.sink||null;so.loop=m.loop||null;so.live=m.live||null;so.hints=m.hints||null;}
for(var si=0;si<sw.length;si++)sw[si](so);}
else if(m.t==="pcm"){if(HUD.on){var p0=PT();playPCM(m);hudPcm(PT()-p0);}else playPCM(m);}
else if(m.t==="wperf"){console.log("[moy worker] "+m.s);HUD.w="worker "+m.s.split(" | ").slice(0,2).join("  ");if(HUD.on)drawHud();}
// THE SEAM the pump that sees failures calls. Nothing counts failures yet --
// the sync push still requeues forever on a board that has gone -- and when
// something does, it says so HERE rather than growing a second panel of its
// own. `kind` is the whole contract: "lost" adds the unsynced-work warning,
// anything else is a restart somebody asked for.
else if(m.t==="lost"){linkLost(m.kind||"lost",m.head||"the console is not answering",
m.body||"",m.risk!==false,m.go||"");}
else if(m.t==="error"){console.error("[moy]",m.s);linkState("failed","the console crashed");
sEl.textContent="console crash (see devtools)";sEl.style.color="#ff004d";
// Under the title: the message's tail (an abort's reason; a traceback's
// raising line and exception), then the first frames that threw it.
var ce=document.getElementById("crash");var cs=String(m.s);window.__moyCrash=cs;
var cm=m.msg==null?"":String(m.msg);var cl=(cm||cs).split("\n").slice(-12);
if(cm&&cs.indexOf(cm)===0)cl=cl.concat(cs.slice(cm.length).split("\n")
.filter(function(x){return x.trim();}).slice(0,4));
ce.textContent=cl.join("\n");ce.style.display="block";}}
// ---- pairing (worker.js, THE SIGN-IN) -------------------------------------
// A board serves its console to anyone and its carts only to a browser it has
// paired: by the QR on its screen (a single-use token after the url's #), or
// by the console's password. Pairing leaves this browser a DEVICE KEY, kept
// here per board id in localStorage, and every later visit signs in with it
// unasked. The crypto is the worker's wasm (no WebCrypto over plain HTTP); the
// page keeps the keys and asks the questions.
//
// A QR ARRIVAL'S TOKEN leaves the url before anything else runs, so a reload,
// a bookmark or a shared tab never carries it. An old `?pin=` link is dropped
// the same way: the board refuses pins.
var PINEL=document.getElementById("pin"),PINF=document.getElementById("pinf"),
PINB=document.getElementById("pinb"),PINM=document.getElementById("pinm"),
PINP=document.getElementById("pinp"),PINR=document.getElementById("pinr"),
PINH=document.getElementById("pinh");
var KEYS="moybyte.keys";
// THE CLAIM (worker.js, THE SIGN-IN): a board takes its password from the
// browser holding the claim its Improv answer carried (its first, or a new
// one the cable asked for), here
// from the url's # (the URL Improv answered, which any Improv client opens)
// or from My consoles over the link (a `claim` request); `CHOOSE` while the
// prompt asks for a new password rather than the console's.
var CLAIM=null,CHOOSE=false,CLAIMQ=null,TAKEN=false;
// A refusal takes the busy card down: a console signed in runs on (the link
// says why), one that is not asks again (the worker's {t:"pair"}, with why).
function claimed(m){if(m.ok){CLAIM=null;pinBusy("pairing this browser with it...");}
else if(PINEL&&PINEL.className==="busy"){PINEL.className="";PINEL.style.display="none";}
if(CLAIMQ){try{CLAIMQ.w.postMessage({moylink:1,re:CLAIMQ.id,kind:"claim",ok:!!m.ok,
said:m.why||""},CLAIMQ.o);}catch(e){}CLAIMQ=null;}}
function keysStored(){try{return JSON.parse(localStorage.getItem(KEYS)||"{}")||{};}
catch(e){return {};}}
function keySave(id,kid,key){var k=keysStored();k[id]={kid:kid,key:key};
try{localStorage.setItem(KEYS,JSON.stringify(k));}catch(e){/* private window: this visit only */}}
function keyDrop(id){var k=keysStored();if(!k[id])return;delete k[id];
try{localStorage.setItem(KEYS,JSON.stringify(k));}catch(e){}}
// What a browser calls itself in the console's list of paired browsers.
function browserName(){var u=navigator.userAgent||"";
var b=/Edg\//.test(u)?"Edge":/Firefox\//.test(u)?"Firefox":/Chrome\//.test(u)?"Chrome"
:/Safari\//.test(u)?"Safari":"A browser";
var o=/iPhone|iPad/.test(u)?"iOS":/Android/.test(u)?"Android":/Mac OS/.test(u)?"macOS"
:/Windows/.test(u)?"Windows":/Linux|CrOS/.test(u)?"Linux":"";
return o?b+" on "+o:b;}
// Called by the loader BEFORE the worker is constructed: the sign-in's input.
window.__moySignIn=function(){var tok=null,bid=null;
try{var h=new URLSearchParams((location.hash||"").replace(/^#/,""));
tok=h.get("t");bid=h.get("b");
if(/^[0-9a-f]{32}$/.test(h.get("claim")||"")){CLAIM={claim:h.get("claim"),id:h.get("id")||""};}
var q=new URLSearchParams(location.search);var had=q.has("pin");q.delete("pin");
if(tok||had||h.has("claim")||h.has("id")){var s=q.toString();
history.replaceState(null,"",location.pathname+(s?"?"+s:""));}}
catch(e){/* no history: the token is spent on its first use either way */}
return {keys:keysStored(),token:tok,board:bid,name:browserName()};};
// The worker's word that pairing is needed: `pw` a password can do it, `why`
// what went wrong last ("" the first time), `wait` the backoff's sentence.
// `taken`: another browser took the board, and the card's one button takes
// it back (worker.js, TAKEN).
function pinAsk(m){if(!PINEL)return;
PINEL.className="";TAKEN=!!m.taken;PINF.style.display=TAKEN?"none":"";
PINH.textContent=TAKEN?"disconnected":"pair this browser";
PINB.textContent=TAKEN?"take it back":"pair";
if(TAKEN){PINP.textContent=m.why;PINM.textContent="";PINR.style.display="";
PINEL.style.display="flex";PINB.disabled=false;return;}
PINM.textContent=m.wait||m.why||"";
CHOOSE=!m.pw&&!!CLAIM;
if(CHOOSE){PINP.textContent="Choose this console's password, 8 to 64 characters: "
+"every browser pairs with it.";PINR.style.display="";PINEL.style.display="flex";
PINB.disabled=false;try{PINF.value="";PINF.focus();}catch(e){}return;}
PINP.textContent=m.cable?(m.pw?"Type the console's password, or pair this board by cable: "
+"plug it in and choose Manage by cable in My consoles.":"Pair this board by cable: plug it "
+"in and choose Manage by cable in My consoles."):asApp()?(m.pw?"Type the console's password. "
+"(A code scanned with the camera opens Safari, not this app.)":"Set a password on the console "
+"(passwd), then close and open this app again to type it. (A code scanned with the camera opens Safari, not this app.)")
:m.pw?"Scan the code on the console's WEB "
+"CONSOLE screen, or type the console's password.":"Scan the code on the console's WEB "
+"CONSOLE screen. To type a password instead, set one on the console (passwd).";
PINR.style.display=m.pw?"":"none";
PINEL.style.display="flex";PINB.disabled=false;
if(m.pw){try{PINF.value="";PINF.focus();}catch(e){}}}
function pinSubmit(){if(TAKEN){TAKEN=false;PINEL.style.display="none";
WORKER.postMessage({t:"takeback"});return;}
var v=PINF.value||"";
if(!v){PINM.textContent="type the console's password";return;}
if(CHOOSE){if(v.length<8||v.length>64){PINM.textContent="a password is 8 to 64 characters";return;}
pinSetting();
WORKER.postMessage({t:"claim",claim:CLAIM.claim,id:CLAIM.id,pw:v,name:browserName()});
PINF.value="";return;}
pinBusy("pairing this browser with it...");
WORKER.postMessage({t:"password",pw:v,name:browserName()});PINF.value="";}
// The card while the worker sets a password or pairs: it says what it does
// and asks nothing; the worker's next {t:"pair"} (a refusal) asks again.
function pinBusy(said){if(!PINEL)return;PINEL.className="busy";
PINH.textContent="setting up this browser";
PINP.textContent="The console checks the password with this browser. On a small "
+"board that takes a few seconds; the console starts when it is done.";
PINR.style.display="none";PINB.disabled=true;PINM.textContent=said;PINEL.style.display="flex";}
function pinSetting(){pinBusy("setting the console's password...");}
// The boot's own words on a busy card, which goes once the console is live.
function pinSaid(s){if(!PINEL||PINEL.className!=="busy")return;
if(s==="live"){PINEL.className="";PINEL.style.display="none";}else PINM.textContent=s;}
// Paired: the key is this browser's from now on. A boot that waited at the
// pairing goes on (the worker's), a console that ran starts again with it.
function keyGot(m){keySave(m.id,m.kid,m.key);
if(PINEL&&PINEL.className==="busy")pinBusy("paired: starting the console...");
if(m.reload)location.reload();}
if(PINB)PINB.addEventListener("click",pinSubmit);
if(PINF)PINF.addEventListener("keydown",function(e){
if(e.key==="Enter"){e.preventDefault();pinSubmit();}});
// ---- the link (docs/web_console_online_2026-11.md §5) ---------------------
// A console the loader booted in a window My consoles opened holds the link
// from here: the loader's listener went with its document. It takes messages
// only from its opener at the sites the loader named (window.moyLink), never
// evaluates one, and answers every request: a pack is refused (the console
// runs), a `claim` ({claim, board, password}) sets the board's first password
// (THE CLAIM above) and is answered once the board took it or did not, and
// any other kind is unknown. It tells the site its
// `state`: booted, sign-in (with the prompt's sentence), signed-in (the
// board's carts pulled), failed.
var LINK=window.moyLink||null,LINKW=window.opener,linkN=1000;
function linkState(st,said){if(!LINK||!LINKW)return;
var m={moylink:1,id:++linkN,kind:"state",state:st,said:said||""};
for(var i=0;i<LINK.length;i++){try{LINKW.postMessage(m,LINK[i]);}catch(e){}}}
if(LINK&&LINKW){addEventListener("message",function(e){var m=e.data;
if(e.source!==LINKW||LINK.indexOf(e.origin)<0||!m||m.moylink!==1||typeof m.id!=="number")return;
if(m.kind==="claim"&&WORKER&&!CLAIMQ&&typeof m.claim==="string"&&typeof m.password==="string"){
CLAIMQ={w:e.source,o:e.origin,id:m.id};pinSetting();
WORKER.postMessage({t:"claim",claim:m.claim,id:typeof m.board==="string"?m.board:"",
pw:m.password,name:browserName()});return;}
e.source.postMessage(m.kind==="pack"?{moylink:1,re:m.id,kind:"pack",ok:false,
said:"the console is running"}:{moylink:1,re:m.id,kind:"unknown"},e.origin);});
linkState("booted","");}
// ---- where the carts are kept (#193), export and import ----------------------
// The worker decides the MODE (board vs browser-local) and this only reports it,
// in every mode, board-served included: a board-served page uses the BOARD's
// store and never a second one, which is about where carts LIVE, not about
// which direction they may travel (owner, 2026-08-29: ".moy export/import and
// the p8 converter" are ordinary parts of the picture). A board-served page
// already writes to the board's store on every edit, through the same sync
// push an import rides, and exporting is a read. The rows are the console's
// (page_link.py): Download, Add a file.
var PZMODE=null;
// What the console says of the page's carts: a notice (page_link.py).
function pzSay(s,warn){send({type:"page",say:[s,"",warn?"bad":"ok"]});}
// Where the page keeps the carts: Settings' Carts row, in a word; a page
// that keeps nothing past this tab says so as it starts.
var KEPT={site:"In this browser",board:"On the console",none:"In this tab only"};
function pzMode(mode,s){PZMODE=mode;window.__moyKept=s;
send({type:"page",kept:KEPT[mode]||""});
if(mode==="none")send({type:"page",say:[s,"Your work is lost when it closes.","bad"]});pzAsk();}
function pzAsk(){if(WORKER)WORKER.postMessage({t:"carts"});}
// The worker decided this page keeps its carts HERE, in OPFS -- which the
// browser may evict under disk pressure unless the origin is asked to be made
// durable. THIS thread has to do the asking: storage.persist() is
// [Exposed=Window] and simply does not exist on the worker's navigator, so the
// worker (which owns the mode, and only asks in site mode) sends {t:"keep"}
// and this answers. Never throws and never blocks anything: a refusal, a
// missing API and a locked-down profile are all just states the chip reports.
function pzKeep(){var st=navigator.storage;
if(!st||typeof st.persist!=="function")return;
Promise.resolve().then(function(){return st.persist();})
.then(function(okd){if(WORKER)WORKER.postMessage({t:"kept",state:okd?"granted":"denied"});})
.catch(function(){});}
// The cart folders, for a harness (the worker's {t:"carts"}).
function pzFill(names){window.__moyCarts=names;}
// A .moy zip is bytes the page never inspects -- the worker built it from the
// live VFS, which is the same folder a board reads.
function pzDownload(name,buf){var url=URL.createObjectURL(new Blob([buf],{type:"application/zip"}));
var a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();
document.body.removeChild(a);setTimeout(function(){URL.revokeObjectURL(url);},4000);
window.__moySaved=name;pzSay("Saved "+name,false);}
function pzImport(file){if(!WORKER||!file)return;pzSay("Importing "+file.name,false);
file.arrayBuffer().then(function(buf){
WORKER.postMessage({t:"import",name:file.name,buf:buf},[buf]);})
.catch(function(e){pzSay("Could not read that file",true);console.error(e);});}
// Drop a .moy zip or a PICO-8 cart (.p8 / .p8.png, #194) anywhere on the page.
// In every mode, once the worker has reported one. On a board-served page the
// new cart lands in the VFS like any other change and the sweep ships it to the
// board -- the identical path Make -> +New already takes, pin and all. The
// import deliberately does NOT rebase the sync watcher for exactly this reason:
// an import is a CHANGE and must stay pending until the far end has it.
window.addEventListener("dragover",function(e){if(PZMODE)e.preventDefault();});
window.addEventListener("drop",function(e){if(!PZMODE)return;
e.preventDefault();var f=e.dataTransfer&&e.dataTransfer.files&&e.dataTransfer.files[0];
if(f)pzImport(f);});
// ---- the PICO-8 import report (#194) ----------------------------------------
// "Report, don't crash": the cart RUNS now, so what this says is where it will
// stop agreeing with PICO-8 -- the verbs the generated shim has no answer for,
// and the ones it answers differently. That second kind is why the panel exists
// at all: a cart that quietly draws the wrong thing is worse than one that
// refused. The lines come from tools/p8_writer.report_lines so the CLI and the
// browser say the same things; this only paints them, and offers the one action
// the page cannot infer -- opening the new cart in the editor.
// The report is the console's card: on a cart that converted, its Open plays
// it (page_link.py's `offer`).
function p8Report(lines,ok,dir){var rows=[];
for(var i=1;i<lines.length;i++)rows.push([lines[i],ok?"plain":"danger"]);
if(ok&&dir)send({type:"page",offer:[lines[0],dir].concat(rows)});
else send({type:"page",tell:[lines[0]].concat(rows)});
// Readable by a harness without scraping the DOM, the same way __moyImported is.
window.__moyReport=lines.join(" | ");
window.__moyCard={kind:ok&&dir?"offer":"tell",title:lines[0]};}
// ---- Get Carts' file question (#124) ------------------------------------------
// The console needs a file this page cannot fetch (its host sends no CORS
// header) and asks for the player's own copy. The answer goes back as bytes;
// the CONSOLE holds it to the index's size and sha256, here nothing is
// checked, so there is one check and it is the one every console runs.
// The console's Get Carts page says what it needs; the choosing is the
// page's file chooser, an ask like the rows' (THE ASKS): opened at once while
// the gesture that asked is live, else at the player's next tap.
var pkId=null;
function pkAsk(m){pkId=m.id;
// Readable by the browser harness, the way __moyReport is.
window.__moyPick={id:m.id,name:m.name,size:m.size};
var a={do:"pick"};if(askLive())askDo(a);else askArm(a);}
function pkDone(id){if(id!==undefined&&id!==pkId)return;
pkId=null;window.__moyPick=null;if(ASKED&&ASKED.do==="pick"){ASKED=null;window.__moyAsked=null;}}
// The file goes to the worker TRANSFERRED: a WAD is megabytes.
function pkSend(file){if(!WORKER||pkId===null||!file)return;var id=pkId;pkDone(id);
file.arrayBuffer().then(function(buf){
WORKER.postMessage({t:"picked",id:id,name:file.name,buf:buf},[buf]);})
.catch(function(){WORKER.postMessage({t:"picked",id:id,cancel:1});});}
function pkCancel(){if(!WORKER||pkId===null)return;var id=pkId;
pkDone(id);WORKER.postMessage({t:"picked",id:id,cancel:1});}
// The loader module hands the worker over once constructed.
window.__moyAttach=function(w){WORKER=w;w.onmessage=function(e){onWorker(e.data);};audioSink(w);
w.postMessage({t:"vis",hidden:document.hidden?1:0});};
// Whether this tab is hidden, for the live socket's match (worker.js): a
// match the tab's throttled frames held up says so when it moves again.
document.addEventListener("visibilitychange",function(){
if(WORKER)WORKER.postMessage({t:"vis",hidden:document.hidden?1:0});});
// ?pad=1 forces the touch controls on ANY device (desktop demos, touch laptops).
// Phones show them automatically -- the core's media query hides them only on
// hover-capable fine-pointer (i.e. mouse) devices; per-cart input hints still
// hide the pad for touch-only carts unless forced here.
if(new URLSearchParams(location.search).get("pad")){
document.getElementById("ctl").style.display="flex";}
// ---- GAMEPAD (#254) -----------------------------------------------------------
// A gamepad held at the browser presses the console's buttons as a board's
// does, from its own source, "gamepad" (web_input.GAMEPAD_SOURCE), read once a
// frame before the frame's events go. The Gamepad API's standard mapping: the
// d-pad, and the left stick past GP_DZ, are the directions; the face buttons
// by their place and the standard mapping's names, bottom A, right B, left X,
// top Y; Back/Select is `select`, Start `start` (the console's key: the system
// menu, the pause card over a game), the centre button `home`; the shoulders
// type the tab keys Q and E, the T-Deck's L and R. A pad appearing makes it an
// input (the `gamepad` event: its focus and its keys show), and the last one
// leaving takes it away. A browser shows pads only to a secure context
// (https, localhost), and only after a button of one is pressed on the page.
var GP_BTN={0:"a",1:"b",2:"x",3:"y",8:"select",9:"start",12:"up",13:"down",
14:"left",15:"right",16:"home"},GP_KEY={4:113,5:101},GP_DZ=0.5;
var gpOn=false,gpHeld={},gpKeys={};
function gpPoll(){var ps=navigator.getGamepads?navigator.getGamepads():null,
now={},keys={},any=false,i,k,n;
if(ps)for(i=0;i<ps.length;i++){var p=ps[i];if(!p||!p.connected)continue;any=true;
var b=p.buttons||[],ax=p.axes||[],x=ax[0]||0,y=ax[1]||0;
for(k in GP_BTN)if(b[k]&&b[k].pressed)now[GP_BTN[k]]=1;
for(k in GP_KEY)if(b[k]&&b[k].pressed)keys[k]=1;
if(x<-GP_DZ)now.left=1;if(x>GP_DZ)now.right=1;if(y<-GP_DZ)now.up=1;if(y>GP_DZ)now.down=1;}
if(!any&&!gpOn)return;
if(any&&!gpOn){gpOn=true;send({type:"gamepad",on:true});}
for(n in gpHeld)if(!now[n]){delete gpHeld[n];send({type:"hold",name:n,down:false,src:"gamepad"});}
for(n in now)if(!gpHeld[n]){gpHeld[n]=1;send({type:"hold",name:n,down:true,src:"gamepad"});}
for(k in keys)if(!gpKeys[k])send({type:"key",code:GP_KEY[k],src:"gamepad"});
gpKeys=keys;
if(!any){gpOn=false;send({type:"gamepad",on:false});}}
var panWas=false;
function pump(){gpPoll();var v=pv();if(v[0]||v[1]){panWas=true;send({type:"pan",dx:v[0],dy:v[1]});}
else if(panWas){panWas=false;send({type:"pan",dx:0,dy:0});}
if(!q.length||!WORKER)return;var b=q;q=[];
WORKER.postMessage({t:"input",json:JSON.stringify({events:b})});}
function tick(ts){requestAnimationFrame(tick);
pump();
// The page's sink reports what it played (a worklet reports its own).
if(WORKER&&schedNext>=0){SS.played=audioPlayed();WORKER.postMessage({t:"played",s:SS});}
var f=pendingFrame,fb=pendingFB;pendingFrame=null;pendingFB=null;
if(f){PERF.f++;if(fb)PERF.b+=fb.byteLength;HUD.kb=fb?fb.byteLength/1024:HUD.kb;
df(JSON.parse(f),fb);
// Hand the buffer back for reuse once it has been blitted.
if(fb&&WORKER)WORKER.postMessage({t:"fbret",b:fb},[fb]);}}
// ---- PLAY ON DEVICE (#197) ---------------------------------------------------
// A page served BY a board hands the open cart back to the board's own glass:
// the open cart's Play on the console (page_link.py), a cart NAME the board
// looks up the way its serial `run` does. The POST is the worker's (podRun),
// sealed like every signed-in call, and what it said is the console's notice.
function podSaid(s){if(s)pzSay(s,false);}
// ---- the LINK surface: one panel, and the REASON is the point ---------------
// A board stops answering for two very different reasons, and saying the same
// thing about both is wrong in both directions:
//
//   "expected"  somebody just asked for an update, or handed the glass back by
//               turning wasm mode off. The board is restarting on purpose and
//               will come back, possibly on a new version. Nothing is at risk.
//   "lost"      it vanished -- unplugged, rebooted, off the WiFi. In BOARD
//               MODE this page keeps no store of its own BY DESIGN, so
//               anything the sweep had not yet shipped lives only in this tab
//               and a reload loses it.
//
// The warning belongs to "lost" alone, and is appended HERE rather than
// trusted to each caller: a caller that forgot it would under-warn on the one
// case that matters, and a surface that always carried it would cry wolf on
// every ordinary update -- which is the same mistake twice.
//
// AND EVEN WITHIN "lost" it is conditional (2026-08-30), on `risk`: whether
// this page is actually holding work the board never took. A reader who had
// changed nothing, watching a console they had just switched off themselves,
// was told "anything you changed in the last few seconds is only in this tab"
// -- which is alarming, useless, and false. The worker knows the answer
// (`outstanding`), so the surface asks rather than assumes. `risk` defaults to
// TRUE for any caller that does not say, because under-warning is the worse
// direction and window.__moyLinkLost has other callers.
//
// THE FIRST REASON WINS. An update that was asked for will be followed by
// exactly the silence a loss looks like, and re-reporting it as a loss thirty
// seconds later is the wolf again.
//
// This owns the SURFACE. The DETECTION -- counting failed posts until "gone"
// is a fact rather than a hiccup -- belongs with the pump that sees them, next
// to gpio_link's MAX_FAILS and the persist path's give-up, and it reaches this
// through window.__moyLinkLost or the worker's {t:"lost"} above.
var linkGone=false;
function linkLost(kind,head,body,risk,go){
if(linkGone)return;
linkGone=true;
var text=(kind==="lost")
?((body?body+" ":"")+((risk===false)
?"Nothing of yours is waiting to be saved. Reopen the console's WEB CONSOLE "
+"screen to carry on."
:"This page keeps no copy of its own while a console is "
+"serving it, so anything you changed in the last few seconds is only in this "
+"tab -- do not reload until the console is back."))
:body;
// The console's card says it; the harness reads it here, the way __moyReport is.
// `go`: where the console went (a Zero that moved to another network), which
// the card's Open opens.
window.__moyLink=kind;window.__moyLinkCard={head:head,body:text,bad:kind==="lost",go:go||""};
send({type:"page",tell:[head,[text,kind==="lost"?"danger":"plain"]],go:go||""});}
window.__moyLinkLost=linkLost;
// A sign-in wait on the sync push: the board is answering and holding this
// page off, so the console says why, and again when a push lands ("").
function linkWait(s){if(linkGone)return;
if(s){window.__moyLink="wait";window.__moyLinkCard={head:s,bad:false};
send({type:"page",say:[s,"Your changes wait in this tab until then -- do not reload.","ok"]});}
else if(window.__moyLink==="wait"){window.__moyLink="";window.__moyLinkCard=null;}}

// The loader module calls this on the play-button gesture (which also unlocks
// WebAudio), once the worker has booted and shipped its assets. It is the whole
// page's entry point: without it nothing starts and the canvas stays black.
// It lived at the TAIL of the update strip's block, after code it had nothing
// to do with, and went out with it (2026-08-29) -- a black screen everywhere,
// past a green suite.
window.__moyStart=function(){
getA().then(function(){sEl.textContent="live";sEl.style.color="#00e436";
if(WORKER)WORKER.postMessage({t:"run"});
requestAnimationFrame(tick);setInterval(plog,PERF_MS);cv.focus();})
.catch(function(e){console.error(e);sEl.textContent="no assets";sEl.style.color="#ff004d";});};
window.__moyRefetchAssets=function(){getA().catch(function(){});};
// The worker bound the update bridge: the board serving this page offers
// firmware updates, and the console's Settings row is live. Recorded rather
// than drawn -- the page owns no update UI now.
// `bound`/`services` come from the CONSOLE (web_boot.services_json), not from
// this message having been sent -- the sending only ever proved the board's
// probe answered, which is a different fact and was reported as this one.
function updBound(m){window.__moyUpdate={running:m.running,screen:!!m.screen,
bound:(m.bound===undefined?null:m.bound),services:m.services||null};}
// ---- loader: spawn the console worker, wire it to the page -------------------
// The VM used to boot HERE, on the main thread. It now lives in worker.js; this
// module only constructs it, forwards the query string (tier + cart) and owns the
// page-side splash and dev-reload polling.
const sEl2 = document.getElementById("s");
try {
  // Stamped by build.sh with worker.js's content hash (see below). Left as the
  // literal placeholder by a hand-assembled index.html, which still works --
  // any token makes the url differ from the bare "worker.js" a browser may have
  // cached -- it just stops changing between builds.
  const MOY_BUILD = "@MOY_BUILD@";
  // The channel this page was published as: empty but on a channel's site,
  // whose build (site/build.py --channel) rewrites this one line. The worker
  // keeps that page's stores apart from the stable site's (moy_store.channelNav).
  const MOY_CHANNEL = "";
  // The colour scheme a first-run console takes its theme variant from: the
  // url's ?scheme=dark|light (the project site passes its visitor's), else the
  // browser's own prefers-color-scheme.
  function moyScheme() {
    const q = new URLSearchParams(location.search).get("scheme");
    if (q === "dark" || q === "light") return q;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark" : "light";
  }
  // The worker url carries a CACHE BUSTER, and it is not superstition: browsers
  // cache worker scripts stubbornly, and a hard reload that refreshes the
  // document will happily keep an old worker.js. That is not hypothetical --
  // the board served a correct new console for an hour while a browser ran the
  // previous worker, and the tier decision lives in exactly that file. The
  // document is no-store from the board, so a reload always fetches this line
  // fresh, and a changed token makes the worker a different url the cache has
  // never seen.
  // The sign-in's input FIRST: a QR's token leaves the url before the worker
  // exists, and the keys this browser holds go with the init.
  const auth = window.__moySignIn();
  // The pack's assets as Blob URLs where the loader (loader.html) booted this
  // page; the worker then imports its modules and the wasm through them, and
  // resolves its requests against this page's address.
  const assets = window.moyAssets || null;
  const w = new Worker(assets ? assets["worker.js"] : "worker.js?v=" + MOY_BUILD,
                       { type: "module" });
  window.__moyAttach(w);
  // A coarse pointer is a finger: the console's hints start on touch.
  w.postMessage({ t: "init", search: glassSearch(), channel: MOY_CHANNEL, auth: auth,
                  assets: assets, base: location.href,
                  rate: actx ? actx.sampleRate : 0,
                  coarse: !!(window.matchMedia && matchMedia("(pointer: coarse)").matches),
                  scheme: moyScheme() });
  // Leaving the page ends the VM with it. A page the back-forward cache keeps
  // keeps its worker too -- and on iOS that worker's wasm memory, so the next
  // console in the same tab (the desk's "small screen?" link) instantiates
  // beside it and can be refused memory. A page brought back from that cache
  // has no VM any more, so it boots again.
  addEventListener("pagehide", function () { if (WORKER) WORKER.terminate(); });
  addEventListener("pageshow", function (e) { if (e.persisted) location.reload(); });
  // ---- play-button splash ----------------------------------------------------
  // The p8-web-player pattern: the game starts on a CLICK, which is also the user
  // gesture that unlocks WebAudio, so sound works from frame one.
  // ?dev=1 (the CLI hot-reload loop) skips it -- devs restart constantly. So
  // does ?start=1, which an embedding page passes when its visitor's click
  // already started this console (the project site's hero): the click that
  // unlocks audio is then the page's, and the frame inherits it.
  const qStart = new URLSearchParams(location.search);
  if (qStart.get("dev") || qStart.get("start")) {
    window.__moyStart();
  } else {
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;display:flex;align-items:center;" +
      "justify-content:center;background:rgba(11,15,26,.88);cursor:pointer;z-index:20";
    ov.innerHTML = "<div style='width:110px;height:110px;border-radius:50%;" +
      "background:#7e2553;border:4px solid #fff1e8;display:flex;align-items:center;" +
      "justify-content:center'><div style='width:0;height:0;margin-left:10px;" +
      "border-top:26px solid transparent;border-bottom:26px solid transparent;" +
      "border-left:42px solid #fff1e8'></div></div>";
    ov.addEventListener("click", () => { ov.remove(); window.__moyStart(); },
      { once: true });
    document.body.appendChild(ov);
  }
  // ---- dev hot-reload (?dev=1, the moy CLI's watch loop) ---------------------
  // Poll the CLI server's /stamp (latest cart-file mtime); on change the WORKER
  // refetches carts.json, restarts the cart and pushes fresh assets. Static
  // production hosting never has ?dev=1, so this costs nothing there; a host
  // with no /stamp (a board, which says what changed on its live socket)
  // answers the first ask with no stamp, and nothing asks again.
  if (new URLSearchParams(location.search).get("dev")) {
    let stamp = null;
    const poll = setInterval(async () => {
      try {
        const r = await fetch("stamp");
        if (!r.ok) { clearInterval(poll); return; }
        const s = await r.text();
        if (stamp === null) { stamp = s; return; }
        if (s === stamp) return;
        stamp = s;
        w.postMessage({ t: "reload" });
        console.log("[moy] cart reload requested");
      } catch (e) { console.error("[moy] reload failed", e); }
    }, 400);
  }
} catch (e) {
  console.error(e);
  sEl2.textContent = "boot failed (see devtools)";
  sEl2.style.color = "#ff004d";
}
</script>
</body></html>
