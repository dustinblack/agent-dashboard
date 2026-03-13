import { useState } from 'react';
import Dashboard from './components/Dashboard';
import Terminal from './components/Terminal';
import './App.css';

function App() {
  const [activeAgentId, setActiveAgentId] = useState<string | null>(null);

  return (
    <div className="bg-slate-900 text-slate-100 font-sans h-screen w-screen overflow-hidden">
      {!activeAgentId ? (
        <div className="h-full w-full overflow-y-auto">
            <Dashboard onAttach={(id) => setActiveAgentId(id)} />
        </div>
      ) : (
        <Terminal 
          agentId={activeAgentId} 
          onClose={() => setActiveAgentId(null)} 
        />
      )}
    </div>
  );
}

export default App;
