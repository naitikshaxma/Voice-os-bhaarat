import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const API = import.meta.env.VITE_API_URL || '';
const BACKEND_URL = import.meta.env.DEV ? '' : API;

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!email.trim() || !password.trim()) {
      setError('Email and password are required.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password: password.trim() }),
      });
      const json = await res.json();
      if (!res.ok || !json?.data?.access_token) {
        throw new Error(json?.error || json?.detail?.error || json?.detail || 'Login failed');
      }
      localStorage.setItem('voice_os_token', json.data.access_token);
      localStorage.setItem('voice_os_auth_user_id', json.data.user_id || '');
      localStorage.setItem('voice_os_auth_email', json.data.email || email.trim());
      localStorage.setItem('voice_os_auth_name', json.data.name || '');
      navigate('/language');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="Email"
        className="w-full rounded-lg bg-[#101010] border border-[#242424] px-3 py-2 text-sm text-white focus:outline-none focus:border-[#f59e0b]"
      />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
        className="w-full rounded-lg bg-[#101010] border border-[#242424] px-3 py-2 text-sm text-white focus:outline-none focus:border-[#f59e0b]"
      />
      {error && <div className="text-xs text-red-400">{error}</div>}
      <button
        type="button"
        disabled={busy}
        onClick={handleLogin}
        className="w-full rounded-lg bg-[#f59e0b] hover:bg-[#d97706] text-black py-2 text-sm font-medium disabled:opacity-50"
      >
        {busy ? 'Please wait...' : 'Login'}
      </button>
    </div>
  );
};

export default Login;
