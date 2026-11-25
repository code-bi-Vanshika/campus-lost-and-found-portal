import { initLayout } from '../layout.js';
import { api } from '../api.js';
import { homeFor } from '../auth.js';
import { $, busy, inlineError } from '../ui.js';

const user = await initLayout();
if (user) location.replace(homeFor(user));

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const setErr = (id, msg) => { const el = $('#' + id + '-err'); el.textContent = msg || ''; $('#' + id).classList.toggle('invalid', !!msg); return !msg; };

$('#register-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const name = $('#name').value.trim(), email = $('#email').value.trim(), phone = $('#phone').value.trim();
  const pw = $('#password').value, pw2 = $('#password2').value;
  const ok = [
    setErr('name', !name ? 'Enter your full name.' : name.length > 100 ? 'Name must be 100 characters or fewer.' : ''),
    setErr('email', !EMAIL.test(email) || email.length > 150 ? 'Enter a valid email address.' : ''),
    setErr('phone', phone.length > 15 ? 'Phone must be 15 characters or fewer.' : ''),
    setErr('password', pw.length < 12 || pw.length > 128 ? 'Use 12 to 128 characters.' : ''),
    setErr('password2', pw !== pw2 ? 'Passwords do not match.' : '')
  ].every(Boolean);
  if (!ok) return;
  busy($('#submit'), async () => {
    try {
      await api.register({ name, email, password: pw, phone: phone || null });
      location.href = 'login.html?registered=1';
    } catch (err) {
      if (err.status === 409) setErr('email', err.message); else inlineError($('#form-error'), err.message);
    }
  });
});
