import React, { useState } from 'react';
import './LoginPage.css';

function LoginPage({ onLogin }) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (userType) => {
    setIsLoading(true);
    setError('');

    try {
      // Generate session ID
      const sessionId = Math.random().toString(36).substr(2, 9);
      
      // Simulate login process
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const userData = {
        username: userType,
        user_type: userType,
        session_id: sessionId,
        customer_id: 'CUST-001'
      };
      
      onLogin(userData);
    } catch (err) {
      setError('Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-header">
          <h1>Audit Management System</h1>
          <p>Select your role to continue</p>
        </div>
        
        {error && (
          <div className="error-message">
            {error}
          </div>
        )}
        
        <div className="login-buttons">
          <button
            className="login-btn customer-btn"
            onClick={() => handleLogin('Customer')}
            disabled={isLoading}
          >
            {isLoading ? 'Connecting...' : 'Login as Customer'}
          </button>
          
          <button
            className="login-btn engineer-btn"
            onClick={() => handleLogin('Engineer')}
            disabled={isLoading}
          >
            {isLoading ? 'Connecting...' : 'Login as Engineer'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default LoginPage;