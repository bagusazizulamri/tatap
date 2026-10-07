var Tui = (function () {
  var S = {view:"cari",items:[],sel:-1,page:1,total:1,filter:{},promptFoc:false,seasonFilter:null};
  var MAXLOG = 200;

  function $(id){return document.getElementById(id);}
  function esc(s){return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
  function isModalOpen(){return !$("title-modal").classList.contains("hidden") || !$("player-modal").classList.contains("hidden");}

  function log(msg,kind){
    var box=$("log");box.classList.remove("hidden");
    var d=document.createElement("div");d.className="log-line"+(kind?" log-"+kind:"");
    d.textContent=msg;box.appendChild(d);
    while(box.children.length>MAXLOG) box.removeChild(box.firstChild);
    box.scrollTop=box.scrollHeight;
  }
  function clearLog(){$("log").classList.add("hidden");$("log").innerHTML="";}

  function loadRecents(){try{return JSON.parse(localStorage.getItem("tatap_recent")||"[]");}catch(e){return [];}}
  function loadCmdHist(){try{return JSON.parse(localStorage.getItem("tatap_hist")||"[]");}catch(e){return [];}}
  function saveCmdHist(h){try{localStorage.setItem("tatap_hist",JSON.stringify(h.slice(0,50)));}catch(e){}}

  function cmdUsage(){
    return "perintah:\n  cari <judul> | :musim | :lanjutan | :katalog\n  :terbaru | :season <winter|spring|summer|fall> <tahun>\n  :switch [hianime|otaku] (ganti sumber video HiAnime / Otakudesu)\n  :filter [key=val...] | :filter reset\n  :genre <slug|title> | :genre | :genre --list | :genre reset\n  :apikey <key> | :ollama <key> | :groq <key> | :gemini <key> | :model <nama> | :apiurl <url>\n  :logs | :crt on|off|toggle | :ambient on|off|toggle\n  :riwayat | :status | :bantuan | :q";
  }

  function applyFilter(){
    if(S.view!=="katalog"){log("filter hanya di katalog","err");return;}
    S.page=1;loadView();
  }

  function setView(v){
    S.view=v;S.page=1;S.sel=-1;S.items=[];clearLog();
    $("empty-state").style.display="none";
    $("results").innerHTML="";$("results-title").textContent="memuat...";$("results-meta").textContent="";
    $("pager").classList.add("hidden");
    $("lane-season-sec").classList.toggle("hidden",v!=="musim");
    $("lane-still-sec").classList.toggle("hidden",v!=="lanjutan");
    $("continue-sec").classList.add("hidden");
    switch(v){
      case "cari":$("results-title").textContent="cari judul";$("empty-state").style.display="";break;
      case "musim":$("results-title").textContent="Tayang musim ini";break;
      case "lanjutan":$("results-title").textContent="Masih tayang (lanjut)";break;
      case "katalog":$("results-title").textContent="Katalog";break;
      case "terbaru":$("results-title").textContent="Sedang rilis · episode terbaru";break;
      case "season-custom":{
        var sf=S.seasonFilter||{season:"",year:""};
        $("results-title").textContent="Season: "+(sf.season||"?")+" "+sf.year;
        break;
      }
    }
    $("sb-view").textContent="view: "+v;
    loadView();
  }

  function apiCall(name){
    switch(name){
      case "musim":return window.Tatap.seasonNow(S.page);
      case "lanjutan":return window.Tatap.stillAiring(S.page);
      case "katalog":return window.Tatap.browse(S.filter,S.page);
      case "terbaru":return window.Tatap.upcoming(7);
      case "season-custom":{
        if(!S.seasonFilter)return null;
        return window.Tatap.seasonBy(S.seasonFilter.season, S.seasonFilter.year);
      }
      case "cari":return null;
    }
    return null;
  }

  async function loadView(){
    if(S.view==="cari"){renderRecents();return;}
    try{
      var r=await apiCall(S.view);
      if(!r){log("gagal load: response kosong","err");return;}
      if(!r.success){
        // FastAPI 422 unpacked — tampilkan detail pertama agar user tahu alasannya.
        var msg=r.error;
        if(Array.isArray(r.detail)&&r.detail[0]&&r.detail[0].msg){
          msg=r.detail[0].msg;
        }else if(r.detail&&r.detail.msg){
          msg=r.detail.msg;
        }
        log("gagal load: "+(msg||"??"),"err");
        return;
      }
      var d=r.data||{};
      S.items=d.items||[];S.page=d.page||1;S.total=d.total_pages||1;S.sel=-1;
      var label=$("results-title").textContent;
      if(d.season) label+=" · "+String(d.season).toUpperCase();
      $("results-title").textContent=label;
      $("results-meta").textContent=S.items.length+" item"+(d.cached?" · cached":"");
      renderResults();renderPager();
    }catch(e){log("err: "+(e&&e.message||e),"err");}
  }

  function renderRecents(){
    S.items=[];S.sel=-1;var r=loadRecents();
    var box=$("results");box.innerHTML="";
    if(!r.length){$("empty-state").style.display="";$("results-title").textContent="siap";$("results-meta").textContent="";$("pager").classList.add("hidden");return;}
    $("empty-state").style.display="none";
    $("results-title").textContent="saran pencarian";$("results-meta").textContent=r.length+" recent";
    for(var i=0;i<r.length;i++){
      (function(q){
        var d=document.createElement("div");d.className="trow";
        d.innerHTML='<span class="tr-num">'+(i+1)+'</span><span class="tr-title">'+esc(q)+'</span>';
        d.addEventListener("click",function(){startSearch(q);});
        box.appendChild(d);
      })(r[i]);
    }
  }

  function renderResults(){
    var box=$("results");box.innerHTML="";
    var isTxt = S.view==="cari" || S.view==="terbaru";
    if(!S.items.length){box.innerHTML="<p class='dim'>Kosong.</p>";return;}
    if(isTxt){
      var nowTs=Math.floor(Date.now()/1000);
      for(var i=0;i<S.items.length;i++){
        (function(a,idx){
          if(S.view==="terbaru"){
            var d=document.createElement("div");
            var aheadSec=(a.airing_at||0)-nowTs;
            var cls="trow trow-up"+(idx===S.sel?" sel":"");
            if(aheadSec>0&&aheadSec<86400) cls+=" today";
            else if(aheadSec>=86400&&aheadSec<172800) cls+=" tomorrow";
            d.className=cls;
            var when=(a.weekday||"")+" "+(a.date||"")+" · "+(a.time||"");
            // Fallback: gunakan textContent kalau ada masalah template; build spans manual.
            var spanDay=document.createElement("span");spanDay.className="tr-day";spanDay.textContent=when;
            var spanEp=document.createElement("span");spanEp.className="tr-ep";spanEp.textContent="ep "+(a.episode==null||a.episode==undefined?"?":a.episode);
            var spanTitle=document.createElement("span");spanTitle.className="tr-title";spanTitle.textContent=a.title||"";
            d.appendChild(spanDay);d.appendChild(spanEp);d.appendChild(spanTitle);
            d.addEventListener("click",function(){
              if(typeof App==="undefined"){log("App belum siap, coba lagi","err");return;}
              App.openTitle(a.id,a.title);
            });
            box.appendChild(d);
          } else {
            var d2=document.createElement("div");d2.className="trow"+(idx===S.sel?" sel":"");
            d2.innerHTML='<span class="tr-num">'+(idx+1)+'</span><span class="tr-title">'+esc(a.title)+'</span><span class="tr-slug">'+esc(a.id)+'</span>';
            d2.addEventListener("click",function(){
              if(typeof App==="undefined"){log("App belum siap, coba lagi","err");return;}
              App.openTitle(a.id,a.title);
            });
            box.appendChild(d2);
          }
        })(S.items[i],i);
      }
    } else {
      var grid=document.createElement("div");grid.className="poster-grid";
      for(var j=0;j<S.items.length;j++){
        (function(a,idx){
          var isUnavail=!a.id;
          var d=document.createElement("div");
          d.className="poster-card"+(idx===S.sel?" sel":"")+(isUnavail?" unmapped":"");
          d.tabIndex=0;
          var idxSpan=document.createElement("span");idxSpan.className="pc-idx";idxSpan.textContent=String(idx+1).padStart(2,"0");d.appendChild(idxSpan);
          if(isUnavail){var bad=document.createElement("span");bad.className="pc-bad";bad.textContent="?";bad.title="Tidak ada di hianime";d.appendChild(bad);}
          if(a.poster){var im=document.createElement("img");im.loading="lazy";im.alt=a.title;im.src=a.poster;im.onerror=function(){this.style.display="none";};d.appendChild(im);}
          var body=document.createElement("div");body.className="poster-body";
          var b=document.createElement("b");b.textContent=a.title;body.appendChild(b);
          var meta=document.createElement("div");meta.className="poster-meta";
          var m=[];if(a.type)m.push(a.type);if(a.eps)m.push(a.eps+" ep");if(a.sub)m.push("SUB "+a.sub);if(a.dub)m.push("DUB "+a.dub);if(a.duration)m.push(a.duration);if(a.score)m.push(a.score.toFixed(1));meta.textContent=m.join(" · ");body.appendChild(meta);
          d.appendChild(body);
          if(!isUnavail){
            d.addEventListener("click",function(){App.openTitle(a.id,a.title);});
          }
          grid.appendChild(d);
        })(S.items[j],j);
      }
      box.appendChild(grid);
    }
  }

  function renderPager(){
    var show=S.view!=="cari";
    $("pager").classList.toggle("hidden",!show);
    if(!show)return;
    $("pg-info").textContent=S.total>1?("hal "+S.page+"/"+S.total+" · ["+"] halaman"):(S.items.length+" item");
  }

  function moveSel(d){
    if(!S.items.length)return;
    S.sel=(S.sel+d+S.items.length)%S.items.length;
    renderSel();
  }
  function renderSel(){
    var box=$("results");
    var all=box.querySelectorAll(".trow");
    for(var i=0;i<all.length;i++){
      var isUnm=all[i].classList.contains("unmapped");
      all[i].classList.toggle("sel",i===S.sel&&!isUnm);
    }
    if(all[S.sel])all[S.sel].scrollIntoView({block:"nearest"});
  }
  function openSelected(){
    if(!S.items.length)return;
    var a=S.items[S.sel];
    if(!a||!a.id){log("judul ini belum tersedia di hianime","err");return;}
    App.openTitle(a.id,a.title);
  }

  function startSearch(q){
    q=q.trim();if(!q)return;
    var recent=loadRecents().filter(function(x){return x!==q;});recent.unshift(q);
    try{localStorage.setItem("tatap_recent",JSON.stringify(recent.slice(0,6)));}catch(e){}
    setViewSilent("cari");
    $("empty-state").style.display="none";
    $("results-title").textContent="Mencari "+q+"...";$("results-meta").textContent="";
    doSearch(q);
  }

  async function doSearch(q){
    var t0=Date.now();
    try{
      var r=await window.Tatap.search(q);
      if(!r||!r.success){log("search error: "+(r&&r.error||"??"),"err");return;}
      S.items=r.data.results||[];S.sel=-1;S.total=1;
      $("results-title").textContent=S.items.length?"Hasil untuk \""+q+"\"":"Tidak ketemu \""+q+"\"";
      $("results-meta").textContent=S.items.length+" judul · "+(Date.now()-t0)+"ms"+(r.data.cached?" · cached":"");
      renderResults();renderPager();
    }catch(e){log("err: "+e.message,"err");}
  }

  function setViewSilent(v){
    S.view=v;S.page=1;
    $("pager").classList.add("hidden");
    $("continue-sec").classList.add("hidden");
    $("lane-season-sec").classList.add("hidden");
    $("lane-still-sec").classList.add("hidden");
  }

  // ==== :genre ====
  var _genreList=null;
  function slugifyGenre(s){
    return String(s||"").trim().toLowerCase()
      .replace(/&/g,"and").replace(/[^a-z0-9]+/g,"-")
      .replace(/^-+|-+$/g,"");
  }
  async function loadGenres(){
    if(_genreList)return _genreList;
    var r=await window.Tatap.genres();
    _genreList=(r&&r.success&&r.data&&r.data.list)||[];
    return _genreList;
  }
  async function openGenreModal(){
    $("genre-modal").classList.remove("hidden");
    $("genre-search").value="";
    var list=await loadGenres();
    renderGenreList(list);
    setTimeout(function(){$("genre-search").focus();},30);
  }
  function closeGenreModal(){$("genre-modal").classList.add("hidden");}
  function renderGenreList(list){
    var box=$("genre-list");box.innerHTML="";
    if(!list.length){
      var e=document.createElement("div");e.className="empty";e.textContent="(tidak ada hasil)";box.appendChild(e);return;
    }
    for(var i=0;i<list.length;i++){
      (function(g){
        var b=document.createElement("button");
        b.innerHTML='<span class="g-slug">'+esc(g.slug)+'</span><span class="g-title">'+esc(g.title)+'</span>';
        b.addEventListener("click",function(){
          applyGenreFilter(g.slug);closeGenreModal();
        });
        box.appendChild(b);
      })(list[i]);
    }
  }
  function applyGenreFilter(slug){
    S.filter={genre:slug};S.page=1;
    log("genre: "+slug,"ok");
    setViewSilent("katalog");
    $("results-title").textContent="Genre: "+slug;
    $("empty-state").style.display="none";
    $("pager").classList.remove("hidden");
    loadView();
  }
  async function cmdGenre(parts){
    if(parts.length<=1){openGenreModal();return;}
    var a=parts.slice(1);
    if(a[0]==="reset"){
      if(S.filter&&S.filter.genre){delete S.filter.genre;S.page=1;
        log("genre filter dihapus","ok");applyFilter();}
      else log("tidak ada genre filter aktif","err");return;
    }
    if(a[0]==="--list"||a[0]==="list"){
      var kw=a[1]&&a[1]!=="--search"?a[1]:(a[2]||"");
      var list=await loadGenres();
      if(!list.length){log("gagal load genre (lihat ?bak offline).","err");return;}
      var shown=0;
      for(var i=0;i<list.length;i++){
        var g=list[i];
        if(kw&&(g.title+" "+g.slug).toLowerCase().indexOf(kw.toLowerCase())<0)continue;
        log((""+g.slug).padEnd(28)+"  "+g.title);
        shown++;
      }
      if(!shown)log("tidak ada genre cocok '"+kw+"'","err");
      else log("total: "+shown+" genre","ok");
      return;
    }
    var slug=slugifyGenre(a.join(" "));
    if(!slug){log("usage: genre <slug|title> | genre | genre --list | genre reset","err");return;}
    applyGenreFilter(slug);
  }

  // ==== :season ====
  var SEASONS = ["winter","spring","summer","fall"];
  function applySeasonFilter(name, year){
    S.seasonFilter = {season: name, year: year};
    S.page = 1;
    log("season: "+name+" "+year, "ok");
    setViewSilent("season-custom");
    $("results-title").textContent = "Season: "+name[0].toUpperCase()+name.slice(1)+" "+year;
    $("empty-state").style.display = "none";
    $("pager").classList.remove("hidden");
    loadView();
  }
  function cmdSeason(rawArgs){
    var t = (rawArgs||"").trim();
    if(!t){
      log("usage: season <winter|spring|summer|fall> <tahun>","err");
      log("contoh: :season fall 2024","err");return;
    }
    var parts = t.split(/\s+/);
    if(parts.length < 2){
      log("usage: season <winter|spring|summer|fall> <tahun>","err");
      log("contoh: :season fall 2024","err");return;
    }
    var name = parts[0].toLowerCase();
    var year = parseInt(parts[1], 10);
    if(SEASONS.indexOf(name) < 0){
      log("season tak dikenal: "+name+" (winter/spring/summer/fall)","err");return;
    }
    if(!year || year < 1900 || year > 2100){
      log("tahun tak valid: "+parts[1],"err");return;
    }
    applySeasonFilter(name, year);
  }

  // ==== :apikey / :model / :apiurl / :ollama / :groq / :gemini ====
  var TRANSLATE_KEYS = {
    apikey: {field:"translate_apikey", label:"apikey"},
    ollama: {field:"translate_apikey", label:"apikey (Ollama Cloud)"},
    groq:   {field:"translate_apikey", label:"apikey (Groq)"},
    gemini: {field:"translate_apikey", label:"apikey (Google AI Studio)"},
    openai: {field:"translate_apikey", label:"apikey (OpenAI)"},
    model:  {field:"translate_model",  label:"model"},
    apiurl: {field:"translate_apiurl", label:"apiurl"}
  };
  function maskKey(v){
    if(!v) return "(kosong)";
    if(v.length <= 10) return "****";
    var prefixLen = (v.indexOf("AQ.") === 0) ? 6 : 8;
    return v.slice(0, prefixLen) + "..." + v.slice(-4);
  }
  async function cmdTranslateSetting(cmd, rawArgs){
    var info = TRANSLATE_KEYS[cmd];
    if(!info) return;
    var args = (rawArgs||"").trim();
    if(cmd === "apikey" || cmd === "ollama" || cmd === "groq" || cmd === "gemini" || cmd === "openai"){
      args = args.replace(/^["']|["']$/g, "").trim();
    }
    if(!args){
      // Status: tampilkan ketiga nilai translate (mask apikey).
      var r = await window.Tatap.getSettings();
      var d = (r && r.success && r.data) || {};
      log("apikey : "+maskKey(d.translate_apikey||""),"ok");
      log("model  : "+(d.translate_model||"(default)"),"ok");
      log("apiurl : "+(d.translate_apiurl||"(default)"),"ok");
      if(!d.translate_apikey){
        log("Belum ada API key AI. Preset otomatis yang didukung:", "err");
        log("  • Ollama Cloud : :apikey ollama_... (model: gpt-oss:20b-cloud)", "dim");
        log("  • Groq (Gratis) : :apikey gsk_...    (model: llama-3.3-70b-versatile)", "dim");
        log("  • Google AI     : :apikey AQ...      (model: gemini-3.1-flash-lite)", "dim");
        log("  • OpenAI        : :apikey sk-...      (model: gpt-4o-mini)", "dim");
      }
      return;
    }
    if(args === "clear" || args === "reset"){
      var p1 = {}; p1[info.field] = "";
      try{ await window.Tatap.setSetting(p1); }catch(e){}
      log(info.label+" dihapus","ok");
      return;
    }
    // Set value.
    var payload = {};
    payload[info.field] = args;
    var extra = "";
      if(cmd === "ollama" || args.indexOf("ollama_") === 0 || args.indexOf("ol_") === 0){
        // Ollama Cloud key -> auto-set apiurl + model gpt-oss:20b-cloud
        payload.translate_apiurl = "https://ollama.com/v1";
        payload.translate_model = "gpt-oss:20b-cloud";
        extra = " (auto: apiurl=Ollama Cloud, model=gpt-oss:20b-cloud)";
      }else if(cmd === "gemini" || args.indexOf("AQ.") === 0 || args.indexOf("AIza") === 0 || args.indexOf("AQ") === 0){
        // Google Gemini key (Google AI Studio: AQ. baru / AIza legacy) -> auto-set apiurl + model Gemini Flash Lite.
        payload.translate_apiurl = "https://generativelanguage.googleapis.com/v1beta/openai";
        payload.translate_model = "gemini-3.1-flash-lite";
        extra = " (auto: apiurl=Google AI Studio, model=gemini-3.1-flash-lite)";
      }else if(cmd === "groq" || args.indexOf("gsk_") === 0){
        // Groq key -> auto-set apiurl + model Llama-3.3-70B / gpt-oss-20b
        payload.translate_apiurl = "https://api.groq.com/openai/v1";
        payload.translate_model = "llama-3.3-70b-versatile";
        extra = " (auto: apiurl=Groq, model=llama-3.3-70b-versatile)";
      }else if(args.indexOf("sk-or-") === 0){
        payload.translate_apiurl = "https://openrouter.ai/api/v1";
        payload.translate_model = "google/gemini-2.0-flash-exp:free";
        extra = " (auto: apiurl=OpenRouter, model=gemini-2.0-flash-exp:free)";
      }else if(cmd === "openai" || args.indexOf("sk-") === 0 || args.indexOf("sk_") === 0){
        payload.translate_apiurl = "https://api.openai.com/v1";
        payload.translate_model = "gpt-4o-mini";
        extra = " (auto: apiurl=OpenAI, model=gpt-4o-mini)";
      }else{
        extra = " (provider kustom: gunakan juga :apiurl <url> dan :model <nama> bila perlu, atau ketik :ollama <key>)";
      }
    }
    try{
      var res = await window.Tatap.setSetting(payload);
      if(res && res.success){
        var masked = (cmd === "apikey") ? (" (" + maskKey(args) + ")") : (" (" + args + ")");
        log(info.label + " disimpan" + masked + extra, "ok");
      }else{
        log("gagal menyimpan " + info.label + ": " + ((res && res.error) || "unknown error"), "err");
      }
    }catch(e){
      log("gagal menyimpan " + info.label + ": " + e.message, "err");
    }
  }

  async function cmdLogs(){
    try{
      var r = await fetch("/api/translate/logs").then(function(res){return res.json();});
      var logs = (r&&r.data&&r.data.logs)||[];
      if(!logs.length){
        log("Belum ada riwayat aktivitas translasi subtitle.", "dim");
        return;
      }
      log("--- Riwayat Log Translasi Subtitle ---", "ok");
      for(var i=0; i<logs.length; i++){
        var line = logs[i];
        var cls = "dim";
        if(line.indexOf("sukses")>=0 || line.indexOf("selesai")>=0 || line.indexOf("Cache HIT")>=0){
          cls = "ok";
        }else if(line.indexOf("GAGAL")>=0 || line.indexOf("gagal")>=0 || line.indexOf("ERROR")>=0 || line.indexOf("Rate limit")>=0){
          cls = "err";
        }
        log(line, cls);
      }
    }catch(e){
      log("Gagal membaca log translasi: " + e.message, "err");
    }
  }

  async function handleCommand(raw){
    var s=raw.trim();if(!s)return;
    var parts=s.split(/\s+/);
    var cmd=parts[0].toLowerCase();
    var args=parts.slice(1).join(" ");
    switch(cmd){
      case "cari":if(!args){log("usage: cari <judul>","err");}else{startSearch(args);}break;
      case "musim":setView("musim");break;
      case "lanjutan":setView("lanjutan");break;
      case "katalog":setView("katalog");break;
      case "season":cmdSeason(args);break;
      case "terbaru":case "airing":setView("terbaru");break;
      case "switch":
        var target = (args || "").toLowerCase().trim();
        var curSrc = (window.cur && window.cur.source) || "hianime";
        var nxt = "";
        if(target === "otaku" || target === "otakudesu"){
          nxt = "otakudesu";
        }else if(target === "hi" || target === "hianime"){
          nxt = "hianime";
        }else if(!target){
          nxt = (curSrc === "otakudesu") ? "hianime" : "otakudesu";
        }else{
          log("usage: :switch [hianime|otaku]","err");
          break;
        }
        if(window.App && window.App.switchSource){
          var resSrc = window.App.switchSource(nxt);
          log("sumber streaming beralih ke: " + (resSrc === "otakudesu" ? "Otakudesu (Sub Indo)" : "HiAnime"), "ok");
        }else{
          if(window.Tatap && window.Tatap.setSetting){
            window.Tatap.setSetting({ preferred_source: nxt }).catch(function(){});
          }
          log("sumber streaming default: " + nxt, "ok");
        }
        break;
      case "genre":cmdGenre(parts);break;
      case "filter":
        if(!args||args==="reset"){
          S.filter={};S.page=1;log("filter direset","ok");applyFilter();break;
        }
        var f={};
        for(var i=0;i<parts.length-1;i++){
          var kv=parts[i+1].split("=");
          if(kv.length===2)f[kv[0]]=kv[1];
        }
        S.filter=f;S.page=1;log("filter: "+JSON.stringify(f),"ok");applyFilter();break;
      case "crt":
        if(!args){log("usage: crt on|off|toggle","err");break;}
        var v1=args==="on"?"on":args==="off"?"off":null;
        if(v1===null&&args!=="toggle"){log("usage: crt on|off|toggle","err");break;}
        var cur=localStorage.getItem("tatap_crt")||"on";
        var nxt=v1||(cur==="on"?"off":"on");
        try{localStorage.setItem("tatap_crt",nxt);}catch(e){}
        document.body.classList.toggle("no-crt",nxt==="off");
        log("crt "+(nxt==="on"?"ON":"OFF"),"ok");break;
      case "ambient":
        if(!args){log("usage: ambient on|off|toggle","err");break;}
        var v2=args==="on"?"on":args==="off"?"off":null;
        if(v2===null&&args!=="toggle"){log("usage: ambient on|off|toggle","err");break;}
        var cur2=localStorage.getItem("tatap_ambient")||"on";
        var nxt2=v2||(cur2==="on"?"off":"on");
        try{localStorage.setItem("tatap_ambient",nxt2);}catch(e){}
        document.body.classList.toggle("no-ambient",nxt2==="off");
        log("ambient "+(nxt2==="on"?"ON":"OFF"),"ok");break;
      case "riwayat":
        try{await fetch("/api/history",{method:"DELETE"});log("riwayat dihapus","ok");}catch(e){log("err: "+e.message,"err");}break;
      case "logs":case "translog":
        await cmdLogs();break;
      case "apikey":case "model":case "apiurl":
      case "ollama":case "groq":case "gemini":case "openai":
        await cmdTranslateSetting(cmd,args);break;
      case "status":
        var extra="";
        if(S.filter&&Object.keys(S.filter).length) extra+=" filter="+JSON.stringify(S.filter);
        if(S.seasonFilter) extra+=" season="+S.seasonFilter.season+" "+S.seasonFilter.year;
        log("view="+S.view+" page="+S.page+"/"+S.total+" items="+S.items.length+(S.sel>=0?" sel="+S.sel:"")+extra,"ok");break;
      case "bantuan":case "help":case "?":
        $("help-overlay").classList.remove("hidden");
        $("help-body").textContent=cmdUsage();
        break;
      case "q":case "clear":
        $("cmd").value="";clearLog();break;
      default:
        if(cmd.indexOf(":")===0){log("perintah tak dikenal: "+cmd+"  (ketik :bantuan)","err");}
        else{startSearch(s);}
    }
  }

  function onKey(e){
    var t=(e.target.tagName||"");
    var typing = t==="INPUT"||t==="SELECT"||t==="TEXTAREA";
    if(e.key==="Escape"){
      if(isModalOpen()){App.onKeyPlayer(e);return;}
      if(typing){$("cmd").blur();S.promptFoc=false;return;}
      $("cmd").value="";clearLog();e.preventDefault();return;
    }
    if(isModalOpen()){App.onKeyPlayer(e);return;}
    if(e.key==="/"){e.preventDefault();focusPrompt();return;}
    if(typing){if(e.key==="Escape"){$("cmd").blur();S.promptFoc=false;}return;}
    if(e.key==="Escape"){$("cmd").value="";clearLog();e.preventDefault();return;}
    if(e.key==="Tab"){e.preventDefault();cycleView();return;}
    if(e.key==="ArrowUp"){
      e.preventDefault();
      if(!S.items.length){cmdHistory(-1);}else{moveSel(-1);}
      return;
    }
    if(e.key==="ArrowDown"){
      e.preventDefault();
      if(!S.items.length){cmdHistory(1);}else{moveSel(1);}
      return;
    }
    if(e.key==="Enter"){
      e.preventDefault();
      if(S.promptFoc){submitPrompt();}else{focusPrompt();}
      return;
    }
    if(e.key==="["||e.key===","){e.preventDefault();pagePrev();return;}
    if(e.key==="]"||e.key==="."){e.preventDefault();pageNext();return;}
    if(!typing&&e.key.length===1&&!e.ctrlKey&&!e.metaKey){focusPrompt();}
  }

  function focusPrompt(){
    S.promptFoc=true;
    var inp=$("cmd");inp.focus();
  }
  function submitPrompt(){
    var inp=$("cmd");var raw=inp.value.trim();inp.value="";
    if(!raw)return;
    log("tatap$ "+raw);
    if(raw.indexOf(":")===0){handleCommand(raw.slice(1));}
    else{handleCommand("cari "+raw);}
  }

  var _hIdx=0,_hPos=0;
  function cmdHistory(dir){
    var h=loadCmdHist();if(!h.length)return;
    _hPos+=dir;
    if(_hPos<0)_hPos=0;
    if(_hPos>=h.length)_hPos=h.length-1;
    $("cmd").value=h[_hPos]||"";
    var inp=$("cmd");inp.selectionStart=inp.selectionEnd=inp.value.length;
  }
  function cycleView(){
    var ord=["cari","musim","terbaru","lanjutan","katalog"];
    var idx=ord.indexOf(S.view);setView(ord[(idx+1)%ord.length]);
  }
  function pagePrev(){if(S.page>1){S.page--;loadView();}}
  function pageNext(){if(S.page<S.total){S.page++;loadView();}}

  function onPromptFocus(){S.promptFoc=true;$("cmd").classList.add("focus");}
  function onPromptBlur(){S.promptFoc=false;$("cmd").classList.remove("focus");setTimeout(function(){if($("cmd").value.trim()&&S.items.length){/* keep sel visible */}},50);}

  function boot(){
    var inp=$("cmd");
    inp.addEventListener("keydown",function(e){
      if(e.key==="Enter"){e.preventDefault();_hPos=loadCmdHist().length;submitPrompt();}
      else if(e.key==="Escape"){inp.blur();}
      else if(e.key==="ArrowUp"&&!S.items.length){e.preventDefault();cmdHistory(-1);}
      else if(e.key==="ArrowDown"&&!S.items.length){e.preventDefault();cmdHistory(1);}
      else if(e.key==="Tab"){e.preventDefault();cycleView();}
      else if(e.key==="/"){e.preventDefault();}
    });
    inp.addEventListener("focus",onPromptFocus);
    inp.addEventListener("blur",onPromptBlur);
    inp.addEventListener("input",function(){if(inp.value.indexOf(":")===0){/* could show command hints */}});
    document.addEventListener("keydown",onKey);
    $("help-close").addEventListener("click",function(){$("help-overlay").classList.add("hidden");});
    $("help-overlay").addEventListener("click",function(e){if(e.target===$("help-overlay"))$("help-overlay").classList.add("hidden");});
    // Genre modal listeners
    $("genre-close").addEventListener("click",closeGenreModal);
    $("genre-modal").addEventListener("click",function(e){if(e.target===$("genre-modal"))closeGenreModal();});
    $("genre-search").addEventListener("input",function(){
      var kw=this.value.trim().toLowerCase();
        loadGenres().then(function(list){
          var filtered=kw?list.filter(function(g){
            return (g.title+" "+g.slug).toLowerCase().indexOf(kw)>=0;
          }):list;
          renderGenreList(filtered);
        });
      });
    $("clear-hist").addEventListener("click",async function(){
      try{await fetch("/api/history",{method:"DELETE"});}catch(e){}
      App.renderContinue();log("riwayat dihapus","ok");
    });
    $("sb-view").textContent="view: "+S.view;
    renderRecents();
  }

  return {boot:boot,log:log,clearLog:clearLog,setView:setView,loadView:loadView,moveSel:moveSel,renderSel:renderSel,openSelected:openSelected,startSearch:startSearch,doSearch:doSearch,renderResults:renderResults,renderPager:renderPager,renderRecents:renderRecents,cmdUsage:cmdUsage,openGenreModal:openGenreModal,view:function(){return S.view;},state:function(){return S;}};
})();