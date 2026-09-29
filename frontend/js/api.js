async function jget(u){var r=await fetch(u);return r.json();}
async function jpost(u,b){var r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b||{})});return r.json();}
window.Tatap={
search:function(q){return jget("/api/search?q="+encodeURIComponent(q));},
episodes:function(slug){return jget("/api/anime/"+encodeURIComponent(slug)+"/episodes");},
resolve:function(slug,ep,mode,q){return jget("/api/stream/resolve?slug="+encodeURIComponent(slug)+"&ep="+ep+"&mode="+(mode||"sub")+"&q="+(q||"best"));},
health:function(){return jget("/api/health");},
history:function(){return jget("/api/history");},
saveHist:function(b){return jpost("/api/history",b);},
playMPV:function(b){return jpost("/api/play-mpv",b);}
};

