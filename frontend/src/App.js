import React, { useState } from 'react';
import LoginPage from './components/LoginPage';
import ChatInterface from './components/ChatInterface';

function App() {
  const [user, setUser] = useState(null);

  return (
    <div className="app">
      {!user ? (
        <LoginPage onLogin={setUser} />
      ) : (
        <ChatInterface user={user} onLogout={() => setUser(null)} />
      )}
    </div>
  );
}

export default App;