function apiBase(){
  var s = localStorage.getItem("tatap_server");
  if(s) return s.replace(/\/+$/,"");
  if(location.protocol === "file:" || !location.origin || location.origin === "null"){
    return "http://127.0.0.1:8767";
  }
  return "";
}
async function jget(u){var r=await fetch(apiBase()+u);return r.json();}
async function jpost(u,b){var r=await fetch(apiBase()+u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});return r.json();}
window.Tatap={
search:function(q){return jget("/api/search?q="+encodeURIComponent(q));},
catalog:function(p){return jget("/api/catalog?page="+(p||1));},
seasonNow:function(p){return jget("/api/seasonal?which=now&page="+(p||1));},
stillAiring:function(p){return jget("/api/seasonal?which=prev&page="+(p||1));},
seasonBy:function(name,year){return jget("/api/seasonal?season="+encodeURIComponent(name)+"&year="+(year||0)+"&page=1");},
upcoming:function(days){return jget("/api/upcoming-episodes?days="+(days||7));},
filters:function(){return jget("/api/filters");},
browse:function(params,page){
  var qs = "";
  for (var k in params) if (params[k]) qs += "&"+encodeURIComponent(k)+"="+encodeURIComponent(params[k]);
  return jget("/api/browse?page="+(page||1)+qs);
},
episodes:function(slug){return jget("/api/anime/"+encodeURIComponent(slug)+"/episodes");},
resolve:function(slug,ep,mode,q,source){return jget("/api/stream/resolve?slug="+encodeURIComponent(slug)+"&ep="+ep+"&mode="+(mode||"sub")+"&q="+(q||"best")+(source?"&source="+encodeURIComponent(source):""));},
genres:function(){return jget("/api/genres");},
health:function(){return jget("/api/health");},
history:function(){return jget("/api/history");},
saveHist:function(b){return jpost("/api/history",b);},
playMPV:function(b){return jpost("/api/play-mpv",b);},
// Settings (termasuk sub_lang).
getSettings:function(){return jget("/api/settings");},
setSetting:function(b){return jpost("/api/settings",b);}
};

