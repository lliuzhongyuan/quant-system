// Delays the Vue mount by one tick because app.js builds its template string after declaring the app.
(function(){
  const originalCreateApp=Vue.createApp;
  Vue.createApp=function(){
    const instance=originalCreateApp.apply(Vue,arguments);
    const originalMount=instance.mount.bind(instance);
    instance.mount=function(target){
      if(target==='#app') return setTimeout(()=>originalMount(target),0);
      return originalMount(target);
    };
    return instance;
  };
})();
