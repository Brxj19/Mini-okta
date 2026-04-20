import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import api from '../api/client';
import {
  LOGOUT_SYNC_KEY,
  clearStoredAuth,
  getStoredActiveOrgId,
  readRememberBrowserPreference,
  storeActiveOrgId,
  syncRememberBrowserPreference,
} from '../utils/authStorage';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [claims, setClaims] = useState(null);
  const [profile, setProfile] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [profileLoading, setProfileLoading] = useState(true);
  const [orgId, setOrgId] = useState(null);
  const [rememberBrowser, setRememberBrowser] = useState(() => readRememberBrowserPreference());

  const clearAuthState = useCallback(() => {
    setClaims(null);
    setProfile(null);
    setProfileLoading(false);
    setOrgId(null);
    setAuthLoading(false);
    clearStoredAuth();
  }, []);

  const refreshSession = useCallback(async () => {
    setAuthLoading(true);
    setProfileLoading(true);

    try {
      const [contextRes, profileRes] = await Promise.all([
        api.get('/api/v1/me/context'),
        api.get('/api/v1/me/profile'),
      ]);

      const nextClaims = {
        sub: contextRes.data?.user_id,
        email: contextRes.data?.email,
        org_id: contextRes.data?.org_id,
        is_super_admin: !!contextRes.data?.is_super_admin,
        roles: contextRes.data?.roles || [],
        permissions: contextRes.data?.permissions || [],
      };

      setClaims(nextClaims);
      setProfile(profileRes.data || null);

      const nextOrgId = nextClaims.is_super_admin
        ? getStoredActiveOrgId() || nextClaims.org_id || null
        : nextClaims.org_id || null;

      setOrgId(nextOrgId);
      return nextClaims;
    } catch (error) {
      if (error?.response?.status === 401) {
        clearAuthState();
        return null;
      }
      throw error;
    } finally {
      setAuthLoading(false);
      setProfileLoading(false);
    }
  }, [clearAuthState]);

  const login = useCallback(async () => {
    await refreshSession();
  }, [refreshSession]);

  const logout = useCallback(async () => {
    try {
      await api.post('/api/v1/logout');
    } catch {}
    clearAuthState();
    window.localStorage.setItem(LOGOUT_SYNC_KEY, String(Date.now()));
  }, [clearAuthState]);

  const refreshProfile = useCallback(async () => {
    if (!claims) {
      setProfile(null);
      setProfileLoading(false);
      return null;
    }

    setProfileLoading(true);
    try {
      const res = await api.get('/api/v1/me/profile');
      const nextProfile = res.data || null;
      setProfile(nextProfile);
      return nextProfile;
    } finally {
      setProfileLoading(false);
    }
  }, [claims]);

  const updateOrgId = useCallback((nextOrgId) => {
    if (claims?.is_super_admin) {
      setOrgId(nextOrgId);
      storeActiveOrgId(nextOrgId, rememberBrowser);
      return;
    }

    setOrgId(claims?.org_id || null);
  }, [claims, rememberBrowser]);

  const updateRememberBrowserPreference = useCallback((enabled) => {
    const nextValue = Boolean(enabled);
    syncRememberBrowserPreference(nextValue);
    setRememberBrowser(nextValue);
    if (claims?.is_super_admin) {
      storeActiveOrgId(orgId, nextValue);
    }
  }, [claims, orgId]);

  useEffect(() => {
    refreshSession().catch(() => {
      clearAuthState();
    });
  }, [refreshSession, clearAuthState]);

  useEffect(() => {
    const handleStorage = (event) => {
      if (event.key !== LOGOUT_SYNC_KEY || !event.newValue) return;
      clearAuthState();
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    };

    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [clearAuthState]);

  const value = {
    claims,
    profile,
    authLoading,
    profileLoading,
    orgId,
    setOrgId: updateOrgId,
    login,
    logout,
    refreshProfile,
    refreshSession,
    setProfile,
    rememberBrowser,
    setRememberBrowserPreference: updateRememberBrowserPreference,
    isSuperAdmin: !!claims?.is_super_admin,
    isAuthenticated: !!claims,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
