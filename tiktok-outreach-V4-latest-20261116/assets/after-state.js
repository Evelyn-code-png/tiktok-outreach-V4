(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const creators = {
    maya: {name:'Maya',subject:'A simple routine, a collaboration with Sunnyleaf',source:'Maya’s supplied profile describes a focus on simple, three-step skincare routines.',reason:'The opening references simple routines; the proposal builds on that format.',why:'Your focus on simple, three-step skincare routines stood out to us.',idea:'We’d love to explore a short routine video featuring our daily moisturizer, with room for your honest experience and your usual storytelling style.',next:'Would you be open to discussing a paid collaboration with a product sample? If so, could you share your rates and availability?'},
    alex: {name:'Alex',subject:'An ingredient-led collaboration with Sunnyleaf',source:'Alex’s supplied profile describes accessible explanations of skincare ingredients.',reason:'The opening references ingredient education; the proposal invites an explanation using brand-supplied information.',why:'Your focus on making skincare ingredients easier to understand caught our attention.',idea:'We’d love to explore an ingredient explainer featuring our daily moisturizer. We can share its ingredient list for you to assess and explain in your own words, alongside your honest experience.',next:'Would you be interested in discussing a paid video with a product sample? If it feels like a fit, could you share your rates and availability?'},
    jamie: {name:'Jamie',subject:'A travel-routine collaboration with Sunnyleaf',source:'Jamie’s supplied profile describes travel packing and everyday routines while away from home.',reason:'The opening references travel routines; the proposal explores a relevant scenario without claiming the product is travel-sized or travel-tested.',why:'Your focus on travel packing and everyday routines away from home stood out to us.',idea:'We’d love to explore how our daily moisturizer could fit into a routine while traveling, if it suits your experience. You would shape the video and share your honest perspective.',next:'Would you be open to discussing a paid collaboration with a product sample? We’d love to hear your ideas, rates, and availability.'}
  };
  const buttons = [...document.querySelectorAll('[data-after-creator]')];
  function select(key) {
    const c=creators[key];
    for(const button of buttons) {
      const active=button.dataset.afterCreator===key;
      button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));
    }
    byId('after-heading').textContent=`An invitation for ${c.name}.`;
    byId('after-subject').textContent=`Subject: ${c.subject}`;
    byId('after-greeting').textContent=`Hi ${c.name},`;
    for(const field of ['why','idea','next','source','reason'])byId(`after-${field}`).textContent=c[field];
  }
  for(const button of buttons)button.addEventListener('click',()=>select(button.dataset.afterCreator));
  byId('after-reset').addEventListener('click',()=>{select('maya');byId('after-evidence').open=false;});
  byId('after-business').addEventListener('click',()=>{
    document.querySelector('[data-instruction-tab="instruction-value"]').click();
    byId('user-instruction').scrollIntoView({block:'start'});
  });
  function route(){
    if(location.hash==='#ai-solution'){
      document.querySelector('[data-instruction-tab="instruction-ai"]').click();
      byId('user-instruction').scrollIntoView({block:'start'});
    }
  }
  window.addEventListener('hashchange',route);
  select('maya');route();
})();
