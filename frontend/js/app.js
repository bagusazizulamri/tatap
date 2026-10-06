var cur = {slug:"", title:"", ep:1, mode:"sub", quality:"best", res:null, eps:[], watched:{},
            subLang:"English",    // preferensi bahasa user dari /api/settings
            activeSub:null,       // URL track subtitle yang sedang aktif (live switch)
            cues:[],              // cue subtitle hasil parse VTT (render overlay milik app)
            subSize:"m"           // ukuran subtitle overlay: s|m|l
           };
function $(id){return document.getElementById(id);}
function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function toast(msg,ms){
  $("toast-msg").textContent=msg;
  $("toast").classList.remove("hidden");
  clearTimeout(window._toastT);
  window._toastT=setTimeout(function(){$("toast").classList.add("hidden");},ms||2200);
}
function loadPrefs(){
  try{
    if(localStorage.getItem("tatap_crt")==="off"){document.body.classList.add("no-crt");}
    if(localStorage.getItem("tatap_ambient")==="off"){document.body.classList.add("no-ambient");}
  }catch(e){}
}

function openTitle(slug,title){
  cur.slug=slug;cur.title=title;cur.eps=[];
  $("tm-title").textContent=title;
  $("tm-sub").textContent=slug;
  $("tm-eyebrow").textContent="DETAIL ANIME";
  $("tm-count").textContent="memuat...";
  $("tm-eps").innerHTML="";
  $("ep-filter").value="";
  $("title-modal").classList.remove("hidden");
  loadEps();
}
function loadEps(){
  window.Tatap.episodes(cur.slug).then(function(r){
    if(!r.success){$("tm-count").textContent="error: "+r.error;return;}
    cur.eps=r.data.episodes||[];
    var watched={};
    window.Tatap.history().then(function(h){
      (h.data||[]).forEach(function(x){if(x.slug===cur.slug)watched[x.episode]=1;});
      cur.watched=watched;
      $("tm-count").textContent=cur.eps.length+" episode · "+cur.mode.toUpperCase();
      renderEpGrid();
    }).catch(function(){});
  });
}
function renderEpGrid(){
  var f=$("ep-filter").value.trim();
  var box=$("tm-eps");box.innerHTML="";
  var shown=0;
  for(var i=0;i<cur.eps.length;i++){
    (function(ep){
      if(f&&String(ep).indexOf(f)<0)return;
      shown++;
      var b=document.createElement("button");
      b.className="ep"+(cur.watched&&cur.watched[ep]?" watched":"");
      b.textContent=ep;
      b.addEventListener("click",function(){openPlayer(ep);});
      box.appendChild(b);
    })(cur.eps[i].ep);
  }
  if(!shown)box.innerHTML="<p class='dim'>Tidak ada episode cocok filter.</p>";
}
function closeTitle(){$("title-modal").classList.add("hidden");}
function syncSeg(){
  document.querySelectorAll("#mode-seg button").forEach(function(x){x.classList.toggle("active",x.getAttribute("data-mode")===cur.mode);});
}

function openPlayer(ep){
  cur.ep=ep;
  closeTitle();
  $("player-modal").classList.remove("hidden");
  $("pm-title").textContent=cur.title;
  $("pm-meta").textContent="ep "+ep+" · "+cur.mode.toUpperCase();
  $("pm-spinner").classList.remove("hidden");
  $("pm-status").textContent="resolving ep "+ep+"...";
  updatePrevNext();
  var t0=Date.now();
  window.Tatap.resolve(cur.slug,ep,cur.mode,cur.quality).then(function(r){
    if(!r.success){$("pm-status").textContent="ERROR: "+r.error;return;}
    cur.res=r.data;
    var picked=r.data.picked||r.data.variants[0];
    $("pm-meta").textContent="ep "+ep+" · "+cur.mode.toUpperCase()+" · "+picked.q+" · "+(r.data.server||"")+(r.data.cached?" · cached":" · "+(Date.now()-t0)+"ms");
    renderVariants();
    // Render dropdown subtitle: pilih track yang cocok dengan preferensi user
    // (cur.subLang) atau default: true. Simpan URL track yang aktif.
    cur.activeSub = pickSubtitleUrl(r.data.subtitles || [], cur.subLang);
    renderSubtitles(r.data.subtitles || [], cur.activeSub);
    playUrl(picked.url,r.data.referer,cur.activeSub,r.data.referer);
    window.Tatap.saveHist({slug:cur.slug,title:cur.title,episode:ep,mode:cur.mode}).then(function(){renderContinue();});
  });
}
function renderVariants(){
  var box=$("pm-variants");box.innerHTML="";
  var vs=(cur.res&&cur.res.variants)||[];
  for(var i=0;i<vs.length;i++){
    (function(v){
      var b=document.createElement("button");
      b.textContent=v.q;
      if(cur.res.picked&&cur.res.picked.q===v.q)b.className="active";
      else if(!cur.res.picked&&i===0)b.className="active";
      b.addEventListener("click",function(){switchQ(v.q);});
      box.appendChild(b);
    })(vs[i]);
  }
}

// ==== Multi-subtitle dropdown ====

function pickSubtitleUrl(subtitles, preferLang){
  // Pilih URL track subtitle yang cocok. Prioritas:
  //   1) Track dengan label == preferLang (case-insensitive).
  //   2) Track dengan lang code == preferLang (misal "English" → "en").
  //   3) Track dengan default: true.
  //   4) Track pertama kalau tidak ada yang match.
  // Return null kalau subtitles kosong (UI akan sembunyikan dropdown).
  if(!subtitles||!subtitles.length)return null;
  if(preferLang){
    var low=String(preferLang).toLowerCase();
    for(var i=0;i<subtitles.length;i++){
      var s=subtitles[i];
      if((s.label||"").toLowerCase()===low)return s.url;
    }
    // Partial match di label (misal "Indonesian" cocok "Indonesian (Bahasa)").
    for(var j=0;j<subtitles.length;j++){
      if(((subtitles[j].label)||"").toLowerCase().indexOf(low)===0)return subtitles[j].url;
    }
    // Match kode bahasa (English → en/id/ja).
    var langMap={"english":"en","indonesian":"id","japanese":"ja","spanish":"es","portuguese":"pt",
                 "french":"fr","german":"de","italian":"it","korean":"ko","chinese":"zh","arabic":"ar",
                 "russian":"ru","thai":"th","vietnamese":"vi","turkish":"tr","hindi":"hi"};
    var code=langMap[low];
    if(code){
      for(var k=0;k<subtitles.length;k++){
        if((subtitles[k].lang||"").toLowerCase()===code)return subtitles[k].url;
      }
    }
  }
  // Fallback: default:true → first track.
  for(var m=0;m<subtitles.length;m++){
    if(subtitles[m].default)return subtitles[m].url;
  }
  return subtitles[0].url;
}

function renderSubtitles(subtitles, activeUrl){
  var wrap=$("pm-subs-wrap");
  var sel=$("pm-subs");
  if(!wrap||!sel)return;
  // Dropdown hanya tampil kalau ada minimal 1 track subtitle.
  // Kalau 0 → sembunyikan wrap (UI tetap clean).
  if(!subtitles||!subtitles.length){
    wrap.classList.add("hidden");
    sel.innerHTML="";
    return;
  }
  wrap.classList.remove("hidden");
  sel.innerHTML="";
  // Opsi pertama: "Off" (matikan subtitle).
  var offOpt=document.createElement("option");
  offOpt.value="";
  offOpt.textContent="Off";
  sel.appendChild(offOpt);
  for(var i=0;i<subtitles.length;i++){
    (function(s){
      var o=document.createElement("option");
      o.value=s.url||"";
      o.textContent=s.label||("Subtitle "+(i+1));
      if(s.default)o.textContent+=" (Default)";
      if(activeUrl&&s.url===activeUrl)o.selected=true;
      sel.appendChild(o);
    })(subtitles[i]);
  }
  // Set value juga kalau match dari default tidak ketemu (URL di pickSubtitleUrl).
  if(activeUrl){
    sel.value=activeUrl;
  }else{
    sel.value="";  // Off
  }
  // Event listener: ganti track aktif seketika + simpan preferensi.
  sel.onchange=function(){
    var url=sel.value;
    cur.activeSub=url||null;
    // Update <track> live tanpa pause/reload video.
    switchSubtitleTrack(url);
    // Cari label untuk disimpan ke settings (server-side preference).
    var label="";
    if(url){
      for(var j=0;j<subtitles.length;j++){
        if(subtitles[j].url===url){label=subtitles[j].label||"";break;}
      }
    }
    if(label){
      cur.subLang=label;
      window.Tatap.setSetting({sub_lang:label}).then(function(){}).catch(function(){});
      toast("Subtitle: "+label);
    }else{
      cur.subLang="";
      window.Tatap.setSetting({sub_lang:""}).then(function(){}).catch(function(){});
      toast("Subtitle: Off");
    }
  };
}

function vttTime(s){
  var m=/^(?:(\d+):)?([0-5]?\d):([0-5]\d)(?:[.,](\d{1,3}))?$/.exec((s||"").trim());
  if(!m)return -1;
  var ms=m[4]?parseInt((m[4]+"000").slice(0,3),10):0;
  return (m[1]?parseInt(m[1],10)*3600:0)+parseInt(m[2],10)*60+parseInt(m[3],10)+ms/1000;
}
function parseVtt(text){
  var out=[];
  var lines=String(text||"").replace(/\r\n?/g,"\n").split("\n");
  var i=0;
  if(lines[0]&&lines[0].indexOf("WEBVTT")===0)i=1;
  var start=-1,end=-1,buf=[];
  var flush=function(){
    if(start>=0&&end>start&&buf.length){
      var html=buf.map(function(x){return esc(x);}).join("<br>");
      html=html.replace(/&lt;[^&]*?&gt;/g,"");
      out.push({start:start,end:end,html:html});
    }
    start=-1;end=-1;buf=[];
  };
  for(;i<lines.length;i++){
    var ln=lines[i].trim();
    if(!ln){flush();continue;}
    if(ln.indexOf("-->")>=0){
      flush();
      var p=ln.split("-->");
      start=vttTime(p[0]);end=vttTime((p[1]||"").trim().split(" ")[0]);
      continue;
    }
    if(/^(NOTE|STYLE|REGION)/.test(ln))continue;
    if(start>=0)buf.push(ln);
  }
  flush();
  return out;
}
function clearOverlay(){
  var box=$("pm-subs-overlay");
  if(!box)return;
  var s=box.querySelector("span");
  if(s)s.innerHTML="";
}
function paintCue(){
  var box=$("pm-subs-overlay");
  var v=$("vid");
  if(!box||!v)return;
  var s=box.querySelector("span");
  if(!s)return;
  if($("player-modal").classList.contains("hidden")){s.innerHTML="";return;}
  var t=v.currentTime||0;
  var html="";
  for(var i=0;i<cur.cues.length;i++){
    if(t>=cur.cues[i].start&&t<=cur.cues[i].end){html=cur.cues[i].html;break;}
  }
  if(s._last!==html){s.innerHTML=html;s._last=html;}
}
function switchSubtitleTrack(url){
  // Render subtitle milik app (overlay div), bukan <track> native.
  // Style tidak lagi mengikuti setting caption Windows.
  var v=$("vid");
  if(!v)return;
  // Bersihkan <track> lama kalau ada (legacy), lalu kosongkan overlay.
  var oldTracks=v.querySelectorAll("track");
  for(var i=0;i<oldTracks.length;i++)oldTracks[i].parentNode.removeChild(oldTracks[i]);
  cur.cues=[];
  clearOverlay();
  if(!url)return;
  var ref=cur.res&&cur.res.referer||"";
  var prox="/api/player/sub?url="+encodeURIComponent(url)+"&referer="+encodeURIComponent(ref);
  fetch(prox).then(function(r){
    if(!r.ok)throw new Error("sub "+r.status);
    return r.text();
  }).then(function(t){
    cur.cues=parseVtt(t);
    paintCue();
  }).catch(function(){
    cur.cues=[];
    clearOverlay();
  });
}
function armAutohide(){
  var stage=document.querySelector(".ambient-stage");
  var shell=document.querySelector(".player-shell");
  if(!stage||stage._armed)return;
  stage._armed=true;
  var v=$("vid");
  var t=null;
  var show=function(){
    stage.classList.remove("idle");
    if(shell)shell.classList.remove("idle");
    clearTimeout(t);
    t=setTimeout(function(){
      if(v.paused)return;
      v.removeAttribute("controls");
      stage.classList.add("idle");
      if(shell)shell.classList.add("idle");
    },2800);
  };
  var wake=function(){
    if(!v.hasAttribute("controls"))v.setAttribute("controls","");
    show();
  };
  ["mousemove","touchstart","click"].forEach(function(ev){stage.addEventListener(ev,wake,{passive:true});});
  v.addEventListener("play",show);
  v.addEventListener("pause",function(){clearTimeout(t);v.setAttribute("controls","");stage.classList.remove("idle");if(shell)shell.classList.remove("idle");});
  v.addEventListener("seeking",show);
  show();
}
function playUrl(url,referrer,sub,subRef){
  var v=$("vid");
  var prox="/api/player/video?url="+encodeURIComponent(url)+"&referer="+encodeURIComponent(referrer||"");
  try{
    var m=/^(.*\/)index-(f\d+-v\d+-a\d+)\.m3u8/.exec(url);
    if(m){
      for(var wi=1;wi<=2;wi++){
        (function(n){
          var seg=m[1]+"seg-"+n+"-"+m[2]+".jpg";
          fetch("/api/player/video?url="+encodeURIComponent(seg)+"&referer="+encodeURIComponent(referrer||""),{mode:"no-cors"}).catch(function(){});
        })(wi);
      }
    }
  }catch(e){}
  // Bersihkan <track> lama lalu pasang track subtitle aktif (live switch).
  // Fungsi switchSubtitleTrack() menhandle Off (hapus semua) dan replace.
  switchSubtitleTrack(sub || null);
  $("pm-spinner").classList.remove("hidden");
  $("pm-status").textContent="buffering...";
  var onCan=function(){$("pm-spinner").classList.add("hidden");};
  v.addEventListener("canplay",onCan,{once:true});
  setTimeout(function(){$("pm-spinner").classList.add("hidden");},15000);
  if(window.Hls&&window.Hls.isSupported()&&url.indexOf(".m3u8")>=0){
    if(window._hls){try{window._hls.destroy();}catch(e){}}
    var h=new Hls({maxBufferLength:30,maxMaxBufferLength:60,maxBufferSize:40*1000*1000,startLevel:-1,capLevelToPlayerSize:true,fragLoadingMaxRetry:6,manifestLoadingMaxRetry:4,levelLoadingMaxRetry:4,fragLoadingMaxRetryTimeout:12000,backBufferLength:30,liveSyncDurationCount:2,maxFragLookUpTolerance:0.5,testBandwidth:false,progressive:true,lowLatencyMode:false});
    window._hls=h;
    h.on(Hls.Events.FRAG_BUFFERED,function(){
      try{
        var nxt=null;
        if(h.levels&&h.levelDetails&&h.levelDetails.fragments){
          var fr=h.levelDetails.fragments;
          for(var fi=0;fi<fr.length;fi++){if(!fr[fi].loaded){nxt=fr[fi];break;}}
        }
        if(nxt&&nxt.url){
          fetch("/api/player/video?url="+encodeURIComponent(nxt.url)+"&referer="+encodeURIComponent(referrer||""),{mode:"no-cors",priority:"low"}).catch(function(){});
        }
      }catch(e){}
    });
    h.loadSource(prox);
    h.attachMedia(v);
    h.on(Hls.Events.ERROR,function(ev,d){
      if(!d)return;
      if(d.fatal){
        $("pm-status").textContent="player error: "+(d.type||"fatal")+" — "+(d.details||"");
        try{h.destroy();}catch(_){}
        return;
      }
      // Non-fatal: fragLoadError / manifestLoadError / networkError — kalau host
      // mati (dramahot.top RST), proxy return 502; HLS.js fire ini. Beri pesan
      // jelas di spinner & stop setelah beberapa retry agar user tidak hang.
      var n=(h.config&&h.config.fragLoadingMaxRetry)||4;
      if(d.details==="fragLoadError"||d.details==="manifestLoadError"||d.details==="networkError"){
        $("pm-status").textContent="gagal load: "+(d.details||"network");
      }
    });
  }else{
    v.src=url.indexOf(".m3u8")>=0?prox:url;
  }
  v.play().catch(function(){$("pm-spinner").classList.add("hidden");});
  armAutohide();
}
function switchQ(q){
  if(!cur.res)return;
  for(var i=0;i<cur.res.variants.length;i++)
    if(cur.res.variants[i].q===q){
      cur.res.picked=cur.res.variants[i];
      renderVariants();
      playUrl(cur.res.variants[i].url,cur.res.referer,cur.res.sub,cur.res.referer);
      toast("Quality: "+q);
      return;
    }
}
function updatePrevNext(){
  var idx=-1;
  for(var i=0;i<cur.eps.length;i++)if(cur.eps[i].ep===cur.ep)idx=i;
  $("pm-prev").disabled=idx<=0;
  $("pm-next").disabled=idx<0||idx>=cur.eps.length-1;
}
function stepEp(d){
  if($("player-modal").classList.contains("hidden"))return;
  var idx=-1;
  for(var i=0;i<cur.eps.length;i++)if(cur.eps[i].ep===cur.ep)idx=i;
  var nxt=cur.eps[idx+d];
  if(nxt)openPlayer(nxt.ep);
  else toast(d>0?"Sudah episode terakhir":"Sudah episode pertama");
}
function closePlayer(){
  var v=$("vid");
  try{v.pause();}catch(e){}
  if(window._hls){try{window._hls.destroy();window._hls=null;}catch(e){}}
  cur.cues=[];
  clearOverlay();
  v.removeAttribute("src");
  try{v.load();}catch(e){}
  $("player-modal").classList.add("hidden");
  $("pm-spinner").classList.add("hidden");
}
function playMPV(){
  window.Tatap.playMPV({slug:cur.slug,title:cur.title,ep:cur.ep||1,mode:cur.mode,quality:cur.quality}).then(function(r){
    toast(r.success?("MPV: "+r.data.picked.q):("ERROR: "+r.error));
  });
}
function renderContinue(){
  window.Tatap.history().then(function(r){
    var h=(r.data||[]).slice(0,10);
    var sec=$("continue-sec");
    if(!h.length){sec.classList.add("hidden");return;}
    var inCari=!window.Tui||Tui.view()==="cari";
    sec.classList.toggle("hidden",!inCari);
    var box=$("continue-row");box.innerHTML="";
    for(var i=0;i<h.length;i++){
      (function(x){
        var d=document.createElement("div");d.className="hist-card";
        var b=document.createElement("b");b.textContent=x.title;d.appendChild(b);
        var s=document.createElement("span");s.textContent="ep "+x.episode+" · "+x.mode+" · lanjutkan ▶";d.appendChild(s);
        d.addEventListener("click",function(){
          cur.slug=x.slug;cur.title=x.title;cur.mode=x.mode||"sub";syncSeg();
          openTitle(x.slug,x.title);openPlayer(x.episode);
        });
        box.appendChild(d);
      })(h[i]);
    }
  }).catch(function(){});
}
function setFallback(r,g,b){
  var fb=$("ambient-fallback");
  if(!fb)return;
  fb.style.background="radial-gradient(60% 90% at 50% 50%, rgb("+r+","+g+","+b+"), transparent 70%)";
}
function startAmbient(){
  var cv=$("ambient"),ctx=null;
  try{ctx=cv.getContext("2d",{willReadFrequently:true});}catch(e){ctx=cv.getContext("2d");}
  var v=$("vid");
  v.setAttribute("crossorigin","anonymous");
  var tmp=document.createElement("canvas");
  tmp.width=48;tmp.height=27;
  var tctx=null;
  try{tctx=tmp.getContext("2d",{willReadFrequently:true});}catch(e){tctx=tmp.getContext("2d");}
  setInterval(function(){
    if(document.body.classList.contains("no-ambient"))return;
    if($("player-modal").classList.contains("hidden"))return;
    if(v.paused||v.ended||v.readyState<2||v.videoWidth===0)return;
    try{
      tctx.drawImage(v,0,0,48,27);
      var px;
      try{px=tctx.getImageData(0,0,48,27).data;}
      catch(taint){
        var h=0,s=String(cur.slug)+cur.ep;
        for(var k=0;k<s.length;k++)h=(h*31+s.charCodeAt(k))%360;
        setFallback(Math.round(90+80*Math.abs(Math.sin(h))),120,220);
        return;
      }
      var r=0,g=0,b=0,n=0;
      for(var i=0;i<px.length;i+=12){r+=px[i];g+=px[i+1];b+=px[i+2];n++;}
      r=Math.round(r/n);g=Math.round(g/n);b=Math.round(b/n);
      var g2=ctx.createLinearGradient(0,0,96,54);
      g2.addColorStop(0,"rgb("+r+","+g+","+b+")");
      g2.addColorStop(1,"rgb("+Math.round(b*.7)+","+Math.round(r*.6)+","+Math.round(g*.8)+")");
      ctx.fillStyle=g2;
      ctx.fillRect(0,0,96,54);
      setFallback(r,g,b);
    }catch(e){}
  },500);
}
function onKeyPlayer(e){
  var t=(e.target.tagName||"");
  var typing=t==="INPUT"||t==="SELECT"||t==="TEXTAREA";
  if(typing&&e.key==="Escape"){e.target.blur();return;}
  var v=$("vid");
  if(e.key==="Escape"){
    if(!$("player-modal").classList.contains("hidden"))closePlayer();
    else if(!$("title-modal").classList.contains("hidden"))closeTitle();
    return;
  }
  if($("player-modal").classList.contains("hidden"))return;
  if(e.key===" "){e.preventDefault();if(v.paused)v.play();else v.pause();}
  else if(e.key==="n")stepEp(1);
  else if(e.key==="p")stepEp(-1);
  else if(e.key==="m")v.muted=!v.muted;
  else if(e.key==="ArrowRight"){e.preventDefault();v.currentTime+=5;}
  else if(e.key==="ArrowLeft"){e.preventDefault();v.currentTime-=5;}
}

function syncSubSize(){
  var box=$("pm-subs-overlay");
  if(box){
    box.classList.remove("sz-s","sz-m","sz-l");
    box.classList.add("sz-"+(cur.subSize||"m"));
  }
  document.querySelectorAll(".sub-size button").forEach(function(b){
    b.classList.toggle("active",b.getAttribute("data-subsize")===(cur.subSize||"m"));
  });
}
function setSubSize(sz){
  if(sz!=="s"&&sz!=="m"&&sz!=="l")return;
  cur.subSize=sz;
  try{localStorage.setItem("tatap_subsize",sz);}catch(e){}
  syncSubSize();
}

App = {
  openTitle:openTitle, openPlayer:openPlayer, playMPV:playMPV,
  renderContinue:renderContinue, onKeyPlayer:onKeyPlayer
};

function init(){
  loadPrefs();
  try{
    var sz=localStorage.getItem("tatap_subsize");
    if(sz==="s"||sz==="m"||sz==="l")cur.subSize=sz;
  }catch(e){}
  syncSubSize();
  document.querySelectorAll(".sub-size button").forEach(function(b){
    b.addEventListener("click",function(){setSubSize(b.getAttribute("data-subsize"));});
  });
  $("vid").addEventListener("timeupdate",paintCue);
  $("vid").addEventListener("seeked",paintCue);
  // Muat preferensi subtitle dari server (sub_lang). Kalau server gagal,
  // fallback ke default 'English' yang sudah di-set di var cur.
  if(window.Tatap&&window.Tatap.getSettings){
    window.Tatap.getSettings().then(function(r){
      if(r&&r.success&&r.data){
        if(r.data.sub_lang) cur.subLang=r.data.sub_lang;
        if(r.data.quality) cur.quality=r.data.quality;
        if(r.data.mode) {cur.mode=r.data.mode; syncSeg();}
      }
    }).catch(function(){});
  }
  document.querySelectorAll("#mode-seg button").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("#mode-seg button").forEach(function(x){x.classList.remove("active");});
      b.classList.add("active");cur.mode=b.getAttribute("data-mode");loadEps();
    });
  });
  document.querySelectorAll("#quality-seg button").forEach(function(b){
    b.addEventListener("click",function(){
      document.querySelectorAll("#quality-seg button").forEach(function(x){x.classList.remove("active");});
      b.classList.add("active");cur.quality=b.getAttribute("data-q");
    });
  });
  $("ep-filter").addEventListener("input",renderEpGrid);
  $("tm-close").addEventListener("click",closeTitle);
  $("title-modal").addEventListener("click",function(e){if(e.target===this)closeTitle();});
  $("pm-close").addEventListener("click",closePlayer);
  $("player-modal").addEventListener("click",function(e){if(e.target===this)closePlayer();});
  $("pm-prev").addEventListener("click",function(){stepEp(-1);});
  $("pm-next").addEventListener("click",function(){stepEp(1);});
  $("pm-mpv").addEventListener("click",playMPV);
  startAmbient();
  renderContinue();
  window.Tui.boot();
}
init();