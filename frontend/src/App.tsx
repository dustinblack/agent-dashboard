import { useState } from 'react';
import Dashboard from './components/Dashboard';
import Terminal from './components/Terminal';
import './App.css';

function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  return (
    <div className="bg-slate-900 text-slate-100 font-sans h-screen w-screen overflow-hidden">
      {!activeSessionId ? (
        <div className="h-full w-full overflow-y-auto">
            <Dashboard onAttach={(id) => setActiveSessionId(id)} />
        </div>
      ) : (
        <Terminal 
          sessionId={activeSessionId} 
          onClose={() => setActiveSessionId(null)} 
        />
      )}
    </div>
  );
}

export default App;
