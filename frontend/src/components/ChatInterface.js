import React, { useState, useEffect, useRef } from 'react';
import ProfileMenu from './ProfileMenu';
import MessageList from './MessageList';
import MessageInput from './MessageInput';
import './ChatInterface.css';

function ChatInterface({ user, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (ws) {
        ws.close();
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const connectWebSocket = () => {
    try {
      const websocket = new WebSocket('ws://localhost:8080');
      
      websocket.onopen = () => {
        console.log('Connected to WebSocket');
        setConnected(false); // Will be true after auth
        setError(null);
        reconnectAttempts.current = 0;
        
        // Send authentication
        const credentials = {
          Customer: { username: 'Customer', password: 'Customer@123' },
          Engineer: { username: 'Engineer', password: 'Engineer@123' }
        };
        
        const creds = credentials[user.user_type];
        websocket.send(JSON.stringify({
          type: 'auth',
          username: creds.username,
          password: creds.password
        }));
      };
      
      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWebSocketMessage(data);
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };
      
      websocket.onclose = (event) => {
        console.log('WebSocket connection closed:', event.code);
        setConnected(false);
        
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          setError(`Connection lost. Reconnecting... (${reconnectAttempts.current}/${maxReconnectAttempts})`);
          setTimeout(connectWebSocket, 2000 * reconnectAttempts.current);
        } else {
          setError('Connection failed. Please refresh the page.');
        }
      };
      
      websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        setError('Connection error occurred');
      };
      
      setWs(websocket);
    } catch (err) {
      console.error('Failed to create WebSocket connection:', err);
      setError('Failed to connect to server');
    }
  };

  const handleWebSocketMessage = (data) => {
    console.log('Received message:', data);
    
    if (data.type === 'auth_success') {
      setConnected(true);
      setError(null);
      // Don't add system message here - just connect silently
    } else if (data.type === 'error') {
      setError(data.message);
      setTyping(false);
    } else if (data.type === 'message' || data.content) {
      setTyping(false);
      addMessage('assistant', data.content || data.message);
    }
  };

  const addMessage = (type, content) => {
    const message = {
      id: Date.now() + Math.random(),
      type,
      content,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, message]);
  };

  const sendMessage = (content, file = null) => {
    if (!ws || !connected) {
      setError('Not connected to server');
      return;
    }

    if (!content.trim() && !file) {
      return;
    }

    // Add user message to chat
    if (content.trim()) {
      addMessage('user', content);
    }
    
    if (file) {
      addMessage('file', `📎 ${file.name}`);
    }

    // Prepare message data
    const messageData = {
      type: 'message',
      content: content.trim()
    };

    // Add file data if present
    if (file) {
      messageData.file = {
        name: file.name,
        content: file.content
      };
    }

    // Send to WebSocket
    try {
      ws.send(JSON.stringify(messageData));
      setTyping(true);
      setError(null);
    } catch (err) {
      console.error('Error sending message:', err);
      setError('Failed to send message');
      setTyping(false);
    }
  };

  const clearError = () => {
    setError(null);
  };

  return (
    <div className="chat-interface">
      <ProfileMenu user={user} onLogout={onLogout} />
      
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={clearError} className="error-close">×</button>
        </div>
      )}
      
      <div className="chat-main">
        <MessageList 
          messages={messages} 
          typing={typing}
          userType={user.user_type}
        />
        <MessageInput 
          onSend={sendMessage}
          connected={connected}
          userType={user.user_type}
        />
      </div>
    </div>
  );
}

export default ChatInterface;