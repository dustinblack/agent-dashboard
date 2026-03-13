import { useState } from 'react';
import Dashboard from './components/Dashboard';
import Terminal from './components/Terminal';
import './App.css';

function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans">
      {!activeSessionId ? (
        <Dashboard onAttach={(id) => setActiveSessionId(id)} />
      ) : (
        <div className="h-screen w-screen bg-black flex flex-col">
          <Terminal 
            sessionId={activeSessionId} 
            onClose={() => setActiveSessionId(null)} 
          />
        </div>
      )}
    </div>
  );
}

export default App;
