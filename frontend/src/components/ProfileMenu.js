import React, { useState, useRef, useEffect } from 'react';
import './ProfileMenu.css';

function ProfileMenu({ user, onLogout }) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const toggleMenu = () => {
    setIsOpen(!isOpen);
  };

  const handleLogout = () => {
    setIsOpen(false);
    onLogout();
  };

  return (
    <div className="profile-menu" ref={menuRef}>
      <div className="profile-header">
        <h2>Audit Management System</h2>
        <button className="profile-button" onClick={toggleMenu}>
          <span className="profile-icon">👤</span>
        </button>
      </div>
      
      {isOpen && (
        <div className="profile-dropdown">
          <div className="profile-info">
            <div className="info-item">
              <span className="info-label">User Type:</span>
              <span className="info-value">{user.user_type}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Customer ID:</span>
              <span className="info-value">{user.customer_id}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Session ID:</span>
              <span className="info-value">{user.session_id}</span>
            </div>
          </div>
          <div className="profile-actions">
            <button className="logout-button" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProfileMenu;