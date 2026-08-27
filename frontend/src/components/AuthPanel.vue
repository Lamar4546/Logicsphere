<script setup>
import { computed, reactive, ref } from 'vue'
import { api } from '../services/api.js'
import logoUrl from '../assets/logisphere-logo.png'

const recoveryQuery = new URLSearchParams(window.location.search)
const recoveryHash = new URLSearchParams(window.location.hash.slice(1))
const recoveryToken = ref(recoveryHash.get('access_token') || '')
const recoveryErrorCode = recoveryHash.get('error_code') || recoveryHash.get('error')
const requestedReset = recoveryQuery.get('auth') === 'reset'
const expiredRecoveryLink = requestedReset && Boolean(recoveryErrorCode)
const mode = ref(expiredRecoveryLink ? 'forgot' : requestedReset && recoveryToken.value ? 'reset' : 'login')
const error = ref(expiredRecoveryLink ? 'This password-reset link has expired or was already used. Request a new one below.' : '')
const notice = ref('')
const loading = ref(false)
const showPassword = ref(false)
const loginForm = reactive({ email: '', password: '' })
const registerForm = reactive({ company_name: '', full_name: '', email: '', password: '', industry: '', country: '' })
const resetForm = reactive({ email: '', password: '', confirmPassword: '' })
const emit = defineEmits(['authenticated'])
const title = computed(() => mode.value === 'login' ? 'Welcome back' : mode.value === 'register' ? 'Create your control tower' : mode.value === 'forgot' ? 'Reset your password' : 'Choose a new password')
const subtitle = computed(() => mode.value === 'login' ? 'Sign in to manage autonomous logistics operations.' : mode.value === 'register' ? 'Set up your organization and let AI handle routine logistics work.' : mode.value === 'forgot' ? 'We will email a secure recovery link if this account exists.' : 'Set a new password for your LogiSphere account.')

// Supabase returns an error in the URL fragment before the app loads when a
// recovery OTP has expired. Remove it after translating it into a clear UI
// state so refreshing this page does not repeat the dead recovery flow.
if (expiredRecoveryLink) window.history.replaceState({}, '', window.location.pathname)

function selectMode(nextMode) { mode.value = nextMode; error.value = ''; notice.value = ''; showPassword.value = false }
async function doLogin() { error.value = ''; loading.value = true; try { await api.login({ email: loginForm.email.trim(), password: loginForm.password }); emit('authenticated') } catch (err) { error.value = err.message || String(err) } finally { loading.value = false } }
async function doRegister() { error.value = ''; loading.value = true; try { await api.register({ company_name: registerForm.company_name.trim(), full_name: registerForm.full_name.trim(), email: registerForm.email.trim(), password: registerForm.password, industry: registerForm.industry.trim(), country: registerForm.country.trim() }); emit('authenticated') } catch (err) { error.value = err.message || String(err) } finally { loading.value = false } }
async function doForgotPassword() { error.value = ''; notice.value = ''; loading.value = true; try { const result = await api.requestPasswordReset(resetForm.email.trim()); notice.value = result.message } catch (err) { error.value = err.message || String(err) } finally { loading.value = false } }
async function doResetPassword() {
  error.value = ''; notice.value = ''
  if (resetForm.password !== resetForm.confirmPassword) { error.value = 'Passwords do not match.'; return }
  loading.value = true
  try {
    const result = await api.resetPassword({ recovery_token: recoveryToken.value, password: resetForm.password })
    window.history.replaceState({}, '', window.location.pathname)
    recoveryToken.value = ''
    selectMode('login')
    notice.value = result.message
  } catch (err) { error.value = err.message || String(err) } finally { loading.value = false }
}
</script>

<template>
  <section class="auth-card">
    <div class="form-side">
      <div class="mobile-logo"><img :src="logoUrl" alt="LogiSphere AI" /></div>
      <div v-if="mode !== 'forgot' && mode !== 'reset'" class="mode-switch" role="tablist" aria-label="Authentication options"><button :class="{ active: mode === 'login' }" role="tab" :aria-selected="mode === 'login'" @click="selectMode('login')">Sign in</button><button :class="{ active: mode === 'register' }" role="tab" :aria-selected="mode === 'register'" @click="selectMode('register')">Create account</button></div>
      <header><span class="eyebrow">AUTONOMOUS LOGISTICS</span><h1>{{ title }}</h1><p>{{ subtitle }}</p></header>
      <form v-if="mode === 'login'" @submit.prevent="doLogin">
        <label><span>Business email</span><input v-model="loginForm.email" type="email" autocomplete="email" placeholder="you@company.com" required /></label>
        <label><span>Password</span><div class="password-field"><input v-model="loginForm.password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="Enter your password" required /><button type="button" @click="showPassword = !showPassword">{{ showPassword ? 'Hide' : 'Show' }}</button></div></label>
        <button class="primary submit" :disabled="loading">{{ loading ? 'Signing in…' : 'Sign in to LogiSphere' }} <span>→</span></button>
        <button type="button" class="forgot-link" @click="selectMode('forgot')">Forgot password?</button>
      </form>
      <form v-else-if="mode === 'register'" @submit.prevent="doRegister">
        <div class="two-col"><label><span>Company name</span><input v-model="registerForm.company_name" autocomplete="organization" placeholder="Acme Logistics" required /></label><label><span>Your name</span><input v-model="registerForm.full_name" autocomplete="name" placeholder="Full name" required /></label></div>
        <label><span>Business email</span><input v-model="registerForm.email" type="email" autocomplete="email" placeholder="you@company.com" required /></label>
        <label><span>Password</span><div class="password-field"><input v-model="registerForm.password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" minlength="8" placeholder="At least 8 characters" required /><button type="button" @click="showPassword = !showPassword">{{ showPassword ? 'Hide' : 'Show' }}</button></div></label>
        <div class="two-col optional"><label><span>Industry <em>optional</em></span><input v-model="registerForm.industry" placeholder="Logistics" /></label><label><span>Country <em>optional</em></span><input v-model="registerForm.country" autocomplete="country-name" placeholder="Jamaica" /></label></div>
        <button class="primary submit" :disabled="loading">{{ loading ? 'Creating workspace…' : 'Create organization' }} <span>→</span></button>
      </form>
      <form v-else-if="mode === 'forgot'" @submit.prevent="doForgotPassword">
        <label><span>Business email</span><input v-model="resetForm.email" type="email" autocomplete="email" placeholder="you@company.com" required /></label>
        <button class="primary submit" :disabled="loading">{{ loading ? 'Sending link…' : 'Email recovery link' }} <span>→</span></button>
        <button type="button" class="forgot-link" @click="selectMode('login')">Back to sign in</button>
      </form>
      <form v-else @submit.prevent="doResetPassword">
        <label><span>New password</span><div class="password-field"><input v-model="resetForm.password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" minlength="8" placeholder="At least 8 characters" required /><button type="button" @click="showPassword = !showPassword">{{ showPassword ? 'Hide' : 'Show' }}</button></div></label>
        <label><span>Confirm password</span><input v-model="resetForm.confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" minlength="8" placeholder="Repeat your password" required /></label>
        <button class="primary submit" :disabled="loading">{{ loading ? 'Updating password…' : 'Update password' }} <span>→</span></button>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="notice" role="status">{{ notice }}</p>
      <p v-if="mode === 'login' || mode === 'register'" class="switch-copy">{{ mode === 'login' ? 'New to LogiSphere?' : 'Already have an account?' }} <button @click="selectMode(mode === 'login' ? 'register' : 'login')">{{ mode === 'login' ? 'Create an account' : 'Sign in' }}</button></p>
    </div>
    <aside class="visual-side"><div class="visual-grid"></div><div class="visual-content"><img :src="logoUrl" alt="LogiSphere — AI agent for smarter logistics" /><span>AI AGENT FOR SMARTER LOGISTICS</span><h2>Move with certainty.</h2><p>See every shipment, automate routine decisions, and step in only when the stakes are high.</p><div class="capabilities"><span>◉ Live visibility</span><span>✦ Agent automation</span><span>⌁ Human control</span></div></div></aside>
  </section>
</template>

<style>
.auth-card{display:grid;grid-template-columns:minmax(350px,.92fr) 1.08fr;width:min(1080px,calc(100vw - 2.5rem));min-height:min(590px,calc(100dvh - 2.5rem));max-height:calc(100dvh - 2.5rem);margin:auto;background:var(--panel);border:1px solid var(--line);border-radius:22px;overflow:hidden;box-shadow:0 28px 75px rgba(0,0,0,.2)}.form-side{display:flex;flex-direction:column;justify-content:center;max-width:440px;width:100%;padding:clamp(1.35rem,3.2vh,2.4rem);margin:auto}.mobile-logo{display:none}.mode-switch{display:inline-flex;align-self:flex-start;padding:4px;border-radius:9px;background:var(--panel-2);margin-bottom:clamp(.8rem,2.4vh,1.5rem)}.mode-switch button{border:0;background:transparent;color:var(--text-dim);padding:.45rem .75rem;font-size:.78rem}.mode-switch button.active{background:var(--panel);color:var(--signal);box-shadow:0 1px 3px rgba(0,0,0,.16);font-weight:650}.eyebrow{display:block;color:var(--signal);font:.65rem var(--font-mono);letter-spacing:.12em;font-weight:700}.form-side h1{color:var(--text);font-size:clamp(1.7rem,3vw,2.05rem);margin:.45rem 0}.form-side header p{margin:0 0 clamp(.9rem,2.4vh,1.45rem);color:var(--text-dim);font-size:.88rem;line-height:1.48}.form-side form{display:flex;flex-direction:column;gap:.7rem}.form-side label{display:flex;flex-direction:column;gap:.32rem;color:var(--text);font-size:.77rem;font-weight:650}.form-side label span{display:flex;justify-content:space-between}.form-side em{font-style:normal;color:var(--text-dim);font-weight:400}.form-side input{height:40px}.password-field{position:relative}.password-field input{padding-right:4.4rem}.password-field button{position:absolute;right:.35rem;top:50%;transform:translateY(-50%);border:0;background:transparent;color:var(--signal);padding:.25rem .4rem;font-size:.74rem}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:.7rem}.submit{display:flex;justify-content:space-between;align-items:center;width:100%;padding:.68rem 1rem;margin-top:.15rem}.submit span{font-size:1.15rem}.forgot-link{align-self:flex-start;border:0;background:transparent;color:var(--signal);padding:.12rem 0;font-size:.75rem}.error,.notice{margin:.65rem 0 0;padding:.65rem .75rem;border-radius:7px;font-size:.8rem}.error{background:color-mix(in srgb,var(--risk-critical) 12%,var(--panel));color:var(--risk-critical)}.notice{background:color-mix(in srgb,var(--risk-low) 12%,var(--panel));color:var(--risk-low)}.switch-copy{margin:.9rem 0 0;text-align:center;color:var(--text-dim);font-size:.8rem}.switch-copy button{border:0;background:transparent;color:var(--signal);padding:0;font-weight:650}.visual-side{position:relative;display:grid;place-items:center;overflow:hidden;background:linear-gradient(145deg,#0a3970,#176fba 58%,#6db7ee);color:#fff}.visual-grid{position:absolute;inset:0;opacity:.2;background-image:linear-gradient(rgba(255,255,255,.22) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.22) 1px,transparent 1px);background-size:44px 44px;transform:perspective(400px) rotateX(62deg) scale(1.8) translateY(29%)}.visual-content{position:relative;max-width:400px;padding:2rem;text-align:center}.visual-content img{width:min(100%,290px);border-radius:16px;mix-blend-mode:screen;filter:drop-shadow(0 16px 25px rgba(0,0,0,.22))}.visual-content>span{display:block;margin-top:.3rem;color:#cde8ff;font:.65rem var(--font-mono);letter-spacing:.16em}.visual-content h2{font-size:1.8rem;margin:1.4rem 0 .55rem}.visual-content p{margin:0;color:#e2f2ff;line-height:1.55;font-size:.86rem}.capabilities{display:flex;justify-content:center;flex-wrap:wrap;gap:.5rem;margin-top:1.2rem}.capabilities span{padding:.38rem .55rem;border:1px solid rgba(255,255,255,.28);border-radius:999px;background:rgba(0,20,50,.14);font-size:.7rem}@media(max-height:650px) and (min-width:801px){.visual-content{transform:scale(.78)}.form-side{padding:1rem}.mode-switch{margin-bottom:.65rem}.form-side header p{margin-bottom:.75rem}.switch-copy{margin-top:.55rem}}@media(max-width:800px){.auth-card{grid-template-columns:1fr;width:min(580px,100%);min-height:100dvh;max-height:none;border:0;border-radius:0}.visual-side{display:none}.form-side{padding:clamp(1.5rem,7vw,2rem);max-width:520px}.mobile-logo{display:block;margin-bottom:1rem}.mobile-logo img{width:150px;display:block;border-radius:10px}.mode-switch{margin-bottom:1.5rem}.form-side h1{font-size:1.8rem}}@media(max-width:440px){.two-col{grid-template-columns:1fr}.optional{display:none}.form-side h1{font-size:1.65rem}}
</style>
