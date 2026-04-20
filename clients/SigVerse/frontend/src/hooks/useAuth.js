import { createContext, createElement, useContext, useEffect, useState } from 'react';
import { getMe } from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = () => {
    return getMe()
      .then((res) => {
        const nextUser = res.data?.data || null;
        setUser(nextUser);
        return nextUser;
      })
      .catch(() => {
        setUser(null);
        return null;
      });
  };

  useEffect(() => {
    let cancelled = false;
    refreshUser().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = () => {
    return refreshUser();
  };

  const logout = () => {
    setUser(null);
  };

  return createElement(
    AuthContext.Provider,
    { value: { user, loading, login, logout, setUser, refreshUser } },
    children
  );
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
