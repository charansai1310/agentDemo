import React, { useState, useRef, useEffect } from 'react';
import './MessageInput.css';

function MessageInput({ onSend, connected, userType }) {
  const [message, setMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    adjustTextareaHeight();
  }, [message]);

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }
  };

  const handleFileSelect = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Check file type
    const allowedTypes = ['.txt', '.doc', '.docx'];
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!allowedTypes.includes(fileExtension)) {
      alert('Please select a .txt, .doc, or .docx file');
      return;
    }

    // Check file size (10MB limit)
    if (file.size > 10 * 1024 * 1024) {
      alert('File size must be less than 10MB');
      return;
    }

    setSelectedFile(file);
    
    // Read file content based on file type
    const reader = new FileReader();
    reader.onload = (e) => {
      let content = e.target.result;
      
      // For .docx files, we'll send the text content
      // Note: Full DOCX parsing would require a library, but we'll try to extract text
      if (fileExtension === '.docx' || fileExtension === '.doc') {
        // For now, send as base64 and let backend handle it
        const base64Reader = new FileReader();
        base64Reader.onload = (base64Event) => {
          setFileContent(base64Event.target.result);
        };
        base64Reader.readAsDataURL(file);
      } else {
        // Plain text file
        setFileContent(content);
      }
    };
    
    if (fileExtension === '.docx' || fileExtension === '.doc') {
      // Let the base64 handler take care of it
      reader.readAsArrayBuffer(file);
    } else {
      reader.readAsText(file);
    }
    
    // Clear the input
    event.target.value = '';
  };

  const removeFile = () => {
    setSelectedFile(null);
    setFileContent('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!connected) {
      alert('Not connected to server');
      return;
    }

    if (!message.trim() && !selectedFile) {
      return;
    }

    const fileData = selectedFile ? {
      name: selectedFile.name,
      content: fileContent
    } : null;

    onSend(message, fileData);
    setMessage('');
    removeFile();
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const openFileDialog = () => {
    fileInputRef.current?.click();
  };

  const getPlaceholder = () => {
    if (userType === 'Customer') {
      return 'Ask about audits, request executions, or create new audits...';
    } else {
      return 'Generate audit code, upload MOP files, or create custom audits...';
    }
  };

  return (
    <div className="message-input">
      <form onSubmit={handleSubmit} className="input-form">
        <div className="input-container">
          {selectedFile && (
            <div className="file-preview">
              <div className="file-info">
                <span className="file-icon">📎</span>
                <span className="file-name">{selectedFile.name}</span>
                <button
                  type="button"
                  className="file-remove"
                  onClick={removeFile}
                  title="Remove file"
                >
                  ×
                </button>
              </div>
            </div>
          )}
          
          <div className="input-row">
            <button
              type="button"
              className="file-button"
              onClick={openFileDialog}
              title="Upload file (.txt, .doc, .docx)"
              disabled={!connected}
            >
              📎
            </button>
            
            <textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder={connected ? getPlaceholder() : 'Connecting...'}
              disabled={!connected}
              className="message-textarea"
              rows="1"
            />
            
            <button
              type="submit"
              className="send-button"
              disabled={!connected || (!message.trim() && !selectedFile)}
              title="Send message"
            >
              ➤
            </button>
          </div>
          
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.doc,.docx"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
        </div>
        
        <div className="input-help">
          <span className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '🟢 Connected' : '🔴 Disconnected'}
          </span>
          <span className="input-hint">
            Press Enter to send, Shift+Enter for new line
          </span>
        </div>
      </form>
    </div>
  );
}

export default MessageInput;