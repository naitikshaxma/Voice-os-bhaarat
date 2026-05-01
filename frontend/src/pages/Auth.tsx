import { useState } from 'react';
import Login from './Login';
import Signup from './Signup';

const Auth = () => {
  const [mode, setMode] = useState<'login' | 'signup'>('login');

  return (
    <div className="min-h-screen bg-black text-white relative">
      <div className="relative z-10 min-h-screen flex items-center justify-center px-4">
        <div className="w-full max-w-md rounded-2xl bg-[#0b0b0b] border border-[#2a2a2a] p-6 shadow-[0_0_45px_rgba(245,158,11,0.12)]">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-heading font-bold text-[#f5f5f5]">
              Voice OS <span className="text-[#f59e0b]">Bharat</span>
            </h1>
            <p className="text-sm text-[#9ca3af] mt-2">Sign in to continue</p>
          </div>

          <div className="flex gap-2 mb-4">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`flex-1 rounded-lg py-2 text-sm font-medium ${mode === 'login' ? 'bg-[#f59e0b] text-black' : 'bg-[#151515] text-[#9ca3af]'}`}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode('signup')}
              className={`flex-1 rounded-lg py-2 text-sm font-medium ${mode === 'signup' ? 'bg-[#f59e0b] text-black' : 'bg-[#151515] text-[#9ca3af]'}`}
            >
              Signup
            </button>
          </div>

          {mode === 'login' ? <Login /> : <Signup />}
        </div>
      </div>
    </div>
  );
};

export default Auth;
