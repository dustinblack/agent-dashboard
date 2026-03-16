import { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import Terminal from './components/Terminal';
import './App.css';

function App() {
  const [currentPath, setCurrentPath] = useState(window.location.pathname);

  useEffect(() => {
    const handleLocationChange = () => {
      setCurrentPath(window.location.pathname);
    };

    window.addEventListener('popstate', handleLocationChange);
    return () => window.removeEventListener('popstate', handleLocationChange);
  }, []);

  const renderContent = () => {
    if (currentPath.startsWith('/terminal/')) {
      const agentId = currentPath.split('/terminal/')[1];
      return (
        <Terminal 
          agentId={agentId} 
          onClose={() => window.close()} 
        />
      );
    }

    return (
      <div className="h-full w-full overflow-y-auto">
          <Dashboard onAttach={(id) => {
            const width = 1024;
            const height = 768;
            const left = (window.screen.width - width) / 2;
            const top = (window.screen.height - height) / 2;
            
            // Open a popup window with minimal browser chrome
            window.open(
              `/terminal/${id}`, 
              `agent_${id}`, 
              `width=${width},height=${height},left=${left},top=${top},menubar=no,toolbar=no,location=no,status=no,personalbar=no`
            );
          }} />
      </div>
    );
  };

  return (
    <div className="flex flex-col bg-slate-900 text-slate-100 font-sans h-screen w-screen overflow-hidden">
      {renderContent()}
    </div>
  );
}

export default App;
