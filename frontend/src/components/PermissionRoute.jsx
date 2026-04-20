import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { hasAnyPermission, hasRole } from '../utils/permissions';
import LoadingScreen from './LoadingScreen';

export default function PermissionRoute({
  children,
  anyOf = [],
  superAdminOnly = false,
  disallowSuperAdmin = false,
  disallowRoles = [],
  redirectTo = '/dashboard',
}) {
  const { claims, isSuperAdmin, authLoading } = useAuth();

  if (authLoading) return <LoadingScreen />;

  if (superAdminOnly) {
    return isSuperAdmin ? children : <Navigate to={redirectTo} replace />;
  }

  if (disallowSuperAdmin && isSuperAdmin) {
    return <Navigate to={redirectTo} replace />;
  }

  if (disallowRoles.some((role) => hasRole(claims, role))) {
    return <Navigate to={redirectTo} replace />;
  }

  if (isSuperAdmin || hasAnyPermission(claims, anyOf)) {
    return children;
  }

  return <Navigate to={redirectTo} replace />;
}
