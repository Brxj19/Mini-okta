import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import LoadingScreen from './LoadingScreen';

export default function ProtectedRoute({ children }) {
  const { isAuthenticated, authLoading } = useAuth();

  if (authLoading) return <LoadingScreen />;

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return children;
}
