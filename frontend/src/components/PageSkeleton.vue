<script setup>
defineProps({ variant: { type: String, default: 'dashboard' } })
</script>

<template>
  <section class="page-skeleton" :class="`skeleton-${variant}`" role="status" aria-label="Loading page content">
    <span class="sr-only">Loading</span>
    <div class="sk-head"><i class="sk-line w-25"></i><i class="sk-line w-50"></i></div>
    <template v-if="variant === 'dashboard'">
      <div class="sk-attention"><div v-for="n in 3" :key="n" class="sk-card sk-attention-row"><i class="sk-pill"></i><div><i class="sk-line w-25"></i><i class="sk-line w-50"></i></div><i class="sk-button"></i></div></div>
      <div class="sk-metrics"><div v-for="n in 4" :key="n" class="sk-card sk-metric"><i class="sk-icon"></i><i class="sk-line w-50"></i><i class="sk-line w-25 tall"></i><i class="sk-bar"></i></div></div>
      <div class="sk-columns"><div class="sk-card sk-map"></div><div class="sk-card sk-activity"><i v-for="n in 4" :key="n" class="sk-line w-75"></i></div></div>
    </template>
    <template v-else-if="variant === 'shipments'">
      <div class="sk-card sk-filter"><i v-for="n in 5" :key="n" class="sk-button"></i></div>
      <div class="sk-card sk-table"><i v-for="n in 7" :key="n" class="sk-line w-100"></i></div>
    </template>
    <template v-else-if="variant === 'planning'">
      <div class="sk-card sk-summary"><i class="sk-line w-25"></i><i class="sk-line w-75 tall"></i></div>
      <div class="sk-card sk-form"><i v-for="n in 6" :key="n" class="sk-input"></i></div>
      <div class="sk-columns"><div class="sk-card sk-map"></div><div class="sk-card sk-activity"></div></div>
    </template>
    <template v-else-if="variant === 'assistant'">
      <div class="sk-card sk-chat"><i v-for="n in 4" :key="n" class="sk-line w-75"></i><i class="sk-input"></i></div>
    </template>
    <template v-else>
      <div class="sk-metrics"><div v-for="n in (variant === 'delivery' || variant === 'analytics' ? 4 : 3)" :key="n" class="sk-card sk-metric"><i class="sk-line w-50"></i><i class="sk-line w-25 tall"></i><i class="sk-bar"></i></div></div>
      <div class="sk-columns"><div v-for="n in (variant === 'orders' ? 3 : 2)" :key="n" class="sk-card sk-form"><i v-for="row in 5" :key="row" class="sk-input"></i></div></div>
      <div v-if="variant === 'orders' || variant === 'inventory' || variant === 'delivery'" class="sk-card sk-table"><i v-for="n in 4" :key="n" class="sk-line w-100"></i></div>
    </template>
  </section>
</template>

<style scoped>
.page-skeleton{display:grid;gap:1rem;min-width:0}.sk-head{display:grid;gap:.65rem;margin-bottom:.15rem}.sk-line,.sk-pill,.sk-icon,.sk-button,.sk-input,.sk-bar{display:block;background:linear-gradient(100deg,var(--panel-2) 20%,color-mix(in srgb,var(--line) 72%,var(--panel)) 38%,var(--panel-2) 56%);background-size:220% 100%;animation:sk-shimmer 1.45s ease-in-out infinite}.sk-line{height:.72rem;border-radius:999px}.sk-line.tall{height:1.65rem;border-radius:7px}.w-25{width:25%}.w-50{width:50%}.w-75{width:75%}.w-100{width:100%}.sk-card{min-width:0;padding:1rem;background:var(--panel);border:1px solid var(--line);border-radius:14px}.sk-attention,.sk-metrics,.sk-columns{display:grid;gap:.85rem}.sk-attention-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:.85rem;min-height:68px}.sk-attention-row>div{display:grid;gap:.55rem}.sk-pill{width:4.8rem;height:1.4rem;border-radius:999px}.sk-button{width:5.2rem;height:2rem;border-radius:8px}.sk-metrics{grid-template-columns:repeat(4,minmax(0,1fr))}.sk-metric{display:grid;gap:.75rem;min-height:150px}.sk-icon{width:2rem;height:2rem;border-radius:9px}.sk-bar{height:.38rem;border-radius:99px}.sk-columns{grid-template-columns:minmax(0,1.8fr) minmax(240px,.85fr)}.sk-map{height:320px}.sk-activity{display:flex;flex-direction:column;gap:1.3rem}.sk-filter{display:flex;gap:.55rem}.sk-table{display:grid;gap:1.35rem;padding:1.35rem}.sk-summary{display:grid;gap:.8rem;padding:1.4rem}.sk-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.sk-input{height:2.7rem;border-radius:8px}.sk-chat{display:grid;gap:1.2rem;min-height:55vh;align-content:end}.sk-chat .sk-line:nth-child(odd){justify-self:start}.sk-chat .sk-line:nth-child(even){justify-self:end}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@keyframes sk-shimmer{to{background-position-x:-220%}}@media(max-width:900px){.sk-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.sk-columns{grid-template-columns:1fr}.sk-map{height:280px}}@media(max-width:600px){.page-skeleton{gap:.7rem}.sk-card{padding:.75rem;border-radius:12px}.sk-attention-row{grid-template-columns:auto minmax(0,1fr);gap:.6rem}.sk-attention-row>.sk-button{display:none}.sk-pill{width:3.6rem}.sk-metric{min-height:120px}.sk-map{height:230px}.sk-form{grid-template-columns:1fr}.sk-filter{overflow:hidden}.sk-button{flex:0 0 4.2rem}.sk-table{gap:1rem}}@media(prefers-reduced-motion:reduce){.sk-line,.sk-pill,.sk-icon,.sk-button,.sk-input,.sk-bar{animation:none}}
</style>
