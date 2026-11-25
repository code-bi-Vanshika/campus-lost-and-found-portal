import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { setUser, homeFor } from '../auth.js';
import { $, busy, inlineError, param, safeNext } from '../ui.js';

const user = await initLayout();
if (user) location.replace(homeFor(user));
if (param('registered')) $('#notice').innerHTML = '<div class="alert alert-ok">Account created. Log in to continue.</div>';

$('#login-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const email = $('#email').value.trim(), password = $('#password').value;
  if (!email || !password) { inlineError($('#form-error'), 'Enter your email and password.'); return; }
  busy($('#submit'), async () => {
    try {
      const data = await api.login(email, password);
      setUser(data.user);
      location.href = safeNext(param('next'), homeFor(data.user));
    } catch (err) { inlineError($('#form-error'), err.message); }
  });
});
