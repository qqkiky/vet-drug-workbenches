
const BUILD = "20260904001029";
const SHELL = ['index.html','manifest.json','icon-192.png','icon-512.png','version.json'];
const CACHE = 'wb-shell-' + BUILD;
self.addEventListener('install', function(e){
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(function(c){return c.addAll(SHELL);}).catch(function(){}));
});
self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(keys){
    return Promise.all(keys.filter(function(k){return k!==CACHE;}).map(function(k){return caches.delete(k);}));
  }).then(function(){return self.clients.claim();}));
});
self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var url = new URL(req.url);
  if(url.pathname.endsWith('version.json')){
    e.respondWith(fetch(req, {cache:'no-store'}).catch(function(){return caches.match(req);}));
    return;
  }
  if(req.mode === 'navigate'){
    e.respondWith(fetch(req).then(function(res){
      var cp = res.clone(); caches.open(CACHE).then(function(c){c.put(req, cp);});
      return res;
    }).catch(function(){return caches.match(req).then(function(r){return r || caches.match('index.html');});}));
    return;
  }
  e.respondWith(caches.match(req).then(function(r){
    return r || fetch(req).then(function(res){
      var cp = res.clone(); caches.open(CACHE).then(function(c){c.put(req, cp);});
      return res;
    }).catch(function(){return r;});
  }));
});
