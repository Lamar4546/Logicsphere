<script setup>
import { ref, watch } from 'vue'
import { api } from '../services/api.js'

const props = defineProps({ theme: { type: String, required: true }, user: { type: Object, default: null } })
const emit = defineEmits(['update-theme', 'account-deleted', 'profile-updated'])
const confirmation = ref('')
const deleting = ref(false)
const error = ref('')
const profileName = ref(props.user?.full_name || '')
const savingProfile = ref(false)
const profileNotice = ref('')
watch(() => props.user?.full_name, (name) => { profileName.value = name || '' })

const themes = [
  { id: 'sky', name: 'Sky blue', description: 'The standard bright control-tower interface.' },
  { id: 'midnight', name: 'Midnight', description: 'A focused dark operations theme for low-light work.' },
  { id: 'slate', name: 'Slate', description: 'A muted professional neutral palette.' },
]

function chooseTheme(id) { emit('update-theme', id) }
async function saveProfile() {
  error.value = ''; profileNotice.value = ''; savingProfile.value = true
  try { const result = await api.updateProfile({ full_name: profileName.value.trim() }); emit('profile-updated', result.user); profileNotice.value = 'Profile saved.' } catch (err) { error.value = err.message } finally { savingProfile.value = false }
}
async function removeAccount() {
  error.value = ''
  if (confirmation.value !== 'DELETE') { error.value = 'Type DELETE exactly to unlock account deletion.'; return }
  deleting.value = true
  try { await api.deleteAccount(confirmation.value); emit('account-deleted') } catch (err) { error.value = err.message } finally { deleting.value = false }
}
</script>

<template>
  <div class="settings">
    <header><span class="mono dim">PREFERENCES & ACCOUNT</span><h2>Settings</h2><p>Personalize your workspace and manage your LogiSphere account.</p></header>
    <section class="panel section"><div><h3>Appearance</h3><p>Choose a professional color theme. Your preference is saved on this device.</p></div><div class="themes"><button v-for="item in themes" :key="item.id" class="theme-card" :class="[item.id, { selected: theme === item.id }]" @click="chooseTheme(item.id)"><span class="swatches"><i></i><i></i><i></i></span><strong>{{ item.name }}</strong><small>{{ item.description }}</small><b v-if="theme === item.id">Selected</b></button></div></section>
    <section class="panel section"><div><h3>Profile</h3><p>Edit the name shown in the sidebar. Your email and role are managed by your authenticated account.</p></div><form class="profile-form" @submit.prevent="saveProfile"><label>Display name<input v-model="profileName" maxlength="120" required placeholder="Your name" /></label><p>Signed in as <strong>{{ user?.email || 'your account' }}</strong>.</p><div class="account-info"><span>Role</span><strong>{{ user?.role || 'Operations user' }}</strong><span>Organization</span><strong>{{ user?.organization_id ? 'Connected organization' : '—' }}</strong></div><button class="primary" :disabled="savingProfile">{{ savingProfile ? 'Saving…' : 'Save profile' }}</button><small v-if="profileNotice" class="saved">{{ profileNotice }}</small></form></section>
    <section class="panel section danger-zone"><div><h3>Delete account</h3><p>This permanently removes your login and application profile. Shared organization records may be retained for operational and audit reasons.</p></div><form @submit.prevent="removeAccount"><label>Type <strong>DELETE</strong> to confirm<input v-model="confirmation" autocomplete="off" placeholder="DELETE" /></label><button class="delete" :disabled="deleting || confirmation !== 'DELETE'">{{ deleting ? 'Deleting account…' : 'Delete my account' }}</button><p v-if="error" class="error">{{ error }}</p></form></section>
  </div>
</template>

<style scoped>
.settings{max-width:950px}.settings header{margin-bottom:1.5rem}.settings header .mono{font-size:.66rem;letter-spacing:.1em}.settings h2{font-size:1.45rem;margin:.25rem 0}.settings header p,.section p{color:var(--text-dim);font-size:.86rem;line-height:1.5}.section{display:grid;grid-template-columns:.85fr 1.15fr;gap:2rem;padding:1.35rem;margin-bottom:1rem}.section h3{font-size:1rem}.section p{margin:.4rem 0}.themes{display:grid;grid-template-columns:repeat(3,1fr);gap:.7rem}.theme-card{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:.45rem;padding:.75rem;border:1px solid var(--line);text-align:left}.theme-card.selected{border:2px solid var(--signal);background:var(--panel-2)}.theme-card small{color:var(--text-dim);font-size:.7rem;line-height:1.4}.theme-card b{font-size:.65rem;color:var(--signal)}.swatches{display:flex;gap:.2rem}.swatches i{width:1rem;height:1rem;border-radius:50%;background:#257fc8}.swatches i:nth-child(2){background:#edf5fd}.swatches i:nth-child(3){background:#163d63}.midnight .swatches i{background:#2d8ddd}.midnight .swatches i:nth-child(2){background:#172333}.midnight .swatches i:nth-child(3){background:#d8e8fa}.slate .swatches i{background:#547a93}.slate .swatches i:nth-child(2){background:#eef2f4}.slate .swatches i:nth-child(3){background:#253a4a}.profile-form{display:flex;flex-direction:column;gap:.7rem}.profile-form label{display:flex;flex-direction:column;gap:.35rem;font-size:.78rem}.profile-form button{align-self:flex-start}.saved{color:var(--risk-low)}.account-info{display:grid;grid-template-columns:1fr 1fr;gap:.65rem;font-size:.8rem}.account-info span{color:var(--text-dim)}.danger-zone{border-color:#efc1c6}.danger-zone h3{color:var(--risk-critical)}.danger-zone form{display:flex;align-items:end;gap:.65rem;flex-wrap:wrap}.danger-zone label{display:flex;flex-direction:column;gap:.35rem;font-size:.78rem}.danger-zone input{width:150px}.delete{background:#c63f4d;color:#fff;border-color:#c63f4d}.delete:disabled{background:#e6b6bc;border-color:#e6b6bc}.error{width:100%;margin:0!important;color:var(--risk-critical)!important}@media(max-width:700px){.section{grid-template-columns:1fr;gap:1rem}.themes{grid-template-columns:1fr}.account-info{grid-template-columns:1fr}.danger-zone form{align-items:stretch}.danger-zone input{width:100%}}
</style>
