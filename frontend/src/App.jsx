import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import PermissionRoute from './components/PermissionRoute';
import AppLayout from './layouts/AppLayout';
import Home from './pages/Home';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import Organizations from './pages/Organizations';
import OrganizationNew from './pages/OrganizationNew';
import OrganizationDetail from './pages/OrganizationDetail';
import Users from './pages/Users';
import UserNew from './pages/UserNew';
import UserDetail from './pages/UserDetail';
import Groups from './pages/Groups';
import GroupNew from './pages/GroupNew';
import GroupDetail from './pages/GroupDetail';
import Applications from './pages/Applications';
import ApplicationNew from './pages/ApplicationNew';
import ApplicationDetail from './pages/ApplicationDetail';
import Roles from './pages/Roles';
import AuditLog from './pages/AuditLog';
import AuditLogDetail from './pages/AuditLogDetail';
import PasswordResetRequest from './pages/PasswordResetRequest';
import PasswordResetConfirm from './pages/PasswordResetConfirm';
import PasswordSetup from './pages/PasswordSetup';
import EmailDeliveries from './pages/EmailDeliveries';
import Security from './pages/Security';
import Settings from './pages/Settings';
import UpgradeAccess from './pages/UpgradeAccess';
import MyApps from './pages/MyApps';
import SearchResults from './pages/SearchResults';
import NotFound from './pages/NotFound';
import LoadingScreen from './components/LoadingScreen';
import ToastViewport from './components/ToastViewport';

export default function App() {
  const { isAuthenticated, authLoading } = useAuth();
  const secure = (element, anyOf = []) => (
    <PermissionRoute anyOf={anyOf}>
      {element}
    </PermissionRoute>
  );
  const superAdminOnly = (element) => (
    <PermissionRoute superAdminOnly>
      {element}
    </PermissionRoute>
  );
  const userAppsOnly = (element) => (
    <PermissionRoute disallowSuperAdmin disallowRoles={['org:admin']}>
      {element}
    </PermissionRoute>
  );

  return (
    <>
      <ToastViewport />
      <Routes>
        <Route path="/" element={authLoading ? <LoadingScreen /> : (isAuthenticated ? <Navigate to="/dashboard" replace /> : <Home />)} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/password-reset/request" element={<PasswordResetRequest />} />
        <Route path="/password-reset/confirm" element={<PasswordResetConfirm />} />
        <Route path="/setup-password" element={<PasswordSetup />} />
        <Route path="/" element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="my-apps" element={userAppsOnly(<MyApps />)} />
          <Route path="organizations" element={superAdminOnly(<Organizations />)} />
          <Route path="organizations/new" element={superAdminOnly(<OrganizationNew />)} />
          <Route path="organizations/:id" element={superAdminOnly(<OrganizationDetail />)} />
          <Route path="users" element={secure(<Users />, ['user:read'])} />
          <Route path="users/new" element={secure(<UserNew />, ['user:create'])} />
          <Route path="users/:id" element={secure(<UserDetail />, ['user:read'])} />
          <Route path="groups" element={secure(<Groups />, ['group:read'])} />
          <Route path="groups/new" element={secure(<GroupNew />, ['group:create'])} />
          <Route path="groups/:id" element={secure(<GroupDetail />, ['group:read'])} />
          <Route path="applications" element={secure(<Applications />, ['app:read'])} />
          <Route path="applications/new" element={secure(<ApplicationNew />, ['app:create'])} />
          <Route path="applications/:id" element={secure(<ApplicationDetail />, ['app:read'])} />
          <Route path="roles" element={secure(<Roles />, ['role:read'])} />
          <Route path="security" element={secure(<Security />, ['audit:read'])} />
          <Route path="settings" element={<Settings />} />
          <Route path="search" element={<SearchResults />} />
          <Route path="audit-log" element={secure(<AuditLog />, ['audit:read'])} />
          <Route path="audit-log/:eventId" element={secure(<AuditLogDetail />, ['audit:read'])} />
          <Route path="email-deliveries" element={secure(<EmailDeliveries />, ['audit:read'])} />
          <Route path="upgrade-access" element={secure(<UpgradeAccess />, ['org:read'])} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}
