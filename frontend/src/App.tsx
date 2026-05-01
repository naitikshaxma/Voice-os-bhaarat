import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, useSearchParams, useNavigate, Navigate } from 'react-router-dom';
import IntroScreen from './components/IntroScreen';
import Index from './pages/Index';
import Auth from './pages/Auth';
import NotFound from './pages/NotFound';
import VoiceInteraction from './components/VoiceInteraction';

/* --------------------------------------------------------------------------
   Language data — same list used in LanguageSelector, duplicated here so the
   /assistant?lang=hi route can resolve the full Language object from the code.
-------------------------------------------------------------------------- */
const LANGUAGES = [
  { code: 'hi', name: 'Hindi',     nativeName: 'हिन्दी',    greeting: 'नमस्ते, मैं आपकी कैसे मदद कर सकता हूँ?' },
  { code: 'en', name: 'English',   nativeName: 'English',   greeting: 'Hello, how can I help you?' },
  { code: 'mr', name: 'Marathi',   nativeName: 'मराठी',     greeting: 'नमस्कार, मी तुम्हाला कशी मदत करू?' },
  { code: 'bn', name: 'Bengali',   nativeName: 'বাংলা',     greeting: 'নমস্কার, আমি আপনাকে কীভাবে সাহায্য করতে পারি?' },
  { code: 'ta', name: 'Tamil',     nativeName: 'தமிழ்',    greeting: 'வணக்கம், நான் உங்களுக்கு எப்படி உதவலாம்?' },
  { code: 'te', name: 'Telugu',    nativeName: 'తెలుగు',   greeting: 'నమస్కారం, నేను మీకు ఎలా సహాయం చేయగలను?' },
  { code: 'kn', name: 'Kannada',   nativeName: 'ಕನ್ನಡ',   greeting: 'ನಮಸ್ಕಾರ, ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം',  greeting: 'നമസ്കാരം, ഞാൻ നിങ്ങളെ എങ്ങനെ സഹായിക്കാം?' },
  { code: 'pa', name: 'Punjabi',   nativeName: 'ਪੰਜਾਬੀ',  greeting: 'ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਤੁਹਾਡੀ ਕਿਵੇਂ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?' },
  { code: 'gu', name: 'Gujarati',  nativeName: 'ગુજરાતી', greeting: 'નમસ્તે, હું તમને કેવી રીતે મદદ કરી શકું?' },
];

/** /assistant?lang=hi — direct route for spec compliance */
const AssistantRoute = () => {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const langCode = params.get('lang') ?? 'en';
  const language = LANGUAGES.find((l) => l.code === langCode) ?? LANGUAGES[1];

  const handleBack = () => {
    navigate('/language');
  };

  return <VoiceInteraction language={language} onBack={handleBack} />;
};

const HomeRoute = () => {
  const [showIntro, setShowIntro] = useState(true);
  const navigate = useNavigate();

  const handleIntroComplete = () => {
    setShowIntro(false);
    const token = localStorage.getItem('voice_os_token');
    if (token) {
      navigate('/language');
    } else {
      navigate('/auth');
    }
  };

  if (showIntro) {
    return <IntroScreen onComplete={handleIntroComplete} />;
  }

  // Fallback if intro finishes but navigate hasn't fully applied
  return null;
};

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const token = localStorage.getItem('voice_os_token');
  if (!token) {
    return <Navigate to="/auth" />;
  }
  return children;
};

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/language" element={
          <ProtectedRoute>
            <Index />
          </ProtectedRoute>
        } />
        <Route path="/assistant" element={
          <ProtectedRoute>
            <AssistantRoute />
          </ProtectedRoute>
        } />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
