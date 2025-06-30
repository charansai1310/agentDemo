import React, { useEffect, useRef } from 'react';
import './MessageList.css';

function MessageList({ messages, typing, userType }) {
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, typing]);

  const formatMessage = (content) => {
    // Handle code blocks
    if (content.includes('```')) {
      const parts = content.split('```');
      return parts.map((part, index) => {
        if (index % 2 === 1) {
          // Code block
          const lines = part.split('\n');
          const language = lines[0] || '';
          const code = lines.slice(1).join('\n');
          return (
            <div key={index} className="code-block">
              {language && <div className="code-language">{language}</div>}
              <pre className="code-content">
                <code>{code}</code>
              </pre>
            </div>
          );
        } else {
          // Regular text
          return <span key={index}>{part}</span>;
        }
      });
    }
    
    // Handle line breaks
    return content.split('\n').map((line, index) => (
      <React.Fragment key={index}>
        {line}
        {index < content.split('\n').length - 1 && <br />}
      </React.Fragment>
    ));
  };

  const formatTimestamp = (timestamp) => {
    return timestamp.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const getExampleCommands = () => {
    if (userType === 'Customer') {
      return [
        'show me all audits',
        'run audit 1',
        'show security audits',
        'create audit for network monitoring',
        'show audit history'
      ];
    } else {
      return [
        'generate code for network security audit',
        'create audit for checking disk space',
        'upload MOP file and generate code',
        'approve "Network Security Audit" "Security"',
        'improve error handling in the code'
      ];
    }
  };

  return (
    <div className="message-list">
      <div className="messages-container">
        {messages.length === 0 && (
          <div className="welcome-message">
            <h3>Welcome, {userType}!</h3>
            <p>Here are some commands you can try:</p>
            <ul className="example-commands">
              {getExampleCommands().map((command, index) => (
                <li key={index} className="example-command">
                  <code>{command}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
        
        {messages.map((message) => (
          <div key={message.id} className={`message ${message.type}`}>
            <div className="message-content">
              {message.type === 'system' && (
                <div className="message-header">
                  <span className="message-sender">System</span>
                </div>
              )}
              {message.type === 'assistant' && (
                <div className="message-header">
                  <span className="message-sender">Assistant</span>
                </div>
              )}
              {message.type === 'file' && (
                <div className="message-header">
                  <span className="message-sender">File Upload</span>
                </div>
              )}
              
              <div className="message-text">
                {formatMessage(message.content)}
              </div>
              
              <div className="message-timestamp">
                {formatTimestamp(message.timestamp)}
              </div>
            </div>
          </div>
        ))}
        
        {typing && (
          <div className="message assistant">
            <div className="message-content">
              <div className="message-header">
                <span className="message-sender">Assistant</span>
              </div>
              <div className="message-text">
                <div className="typing-indicator">
                  <span>Assistant is typing</span>
                  <div className="typing-dots">
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                    <div className="typing-dot"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}

export default MessageList;