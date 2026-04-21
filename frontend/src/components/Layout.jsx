import React, { useEffect, useRef, useState } from 'react';
import { Outlet, NavLink, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import api from '../api/client';
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '../branding';
import OrgSelector from './OrgSelector';
import UserAvatar from './UserAvatar';
import ConfirmDialog from './ConfirmDialog';
import { hasPermission as userHasPermission, hasRole } from '../utils/permissions';
import { getDisplayName } from '../utils/profile';
import {
  ApplicationsIcon,
  BellIcon,
  ChevronDownIcon,
  DashboardIcon,
  GroupsIcon,
  LogoutIcon,
  OrganizationIcon,
  ProductMark,
  RolesIcon,
  SearchIcon,
  SecurityIcon,
  SettingsIcon,
  UsersIcon,
  XIcon,
  DoubleTickIcon,
  MenuIcon
} from './Icons';

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: DashboardIcon },
  { to: '/my-apps', label: 'My Apps', icon: ApplicationsIcon, userOnly: true },
  { to: '/applications', label: 'Applications', icon: ApplicationsIcon, permission: 'app:read' },
  { to: '/users', label: 'Users', icon: UsersIcon, permission: 'user:read' },
  { to: '/groups', label: 'Groups', icon: GroupsIcon, permission: 'group:read' },
  { to: '/security', label: 'Security', icon: SecurityIcon, permission: 'audit:read' },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
];

const adminNavItems = [
  { to: '/organizations', label: 'Organizations', icon: OrganizationIcon },
];

const operationsItems = [
  { to: '/roles', label: 'Roles', icon: RolesIcon, permission: 'role:read' },
  { to: '/audit-log', label: 'Audit Log', icon: SecurityIcon, permission: 'audit:read' },
  { to: '/email-deliveries', label: 'Email Queue', icon: BellIcon, permission: 'audit:read' },
];

export default function Layout() {
  const { claims, profile, logout, isSuperAdmin, orgId } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState('');
  const [planStatus, setPlanStatus] = useState(null);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('q') || '');
  const dropdownRef = useRef(null);
  const notificationsPanelRef = useRef(null);
  const bellButtonRef = useRef(null);
  const searchDebounceRef = useRef(null);

  useEffect(() => {
    const onClick = (event) => {
      if (!dropdownRef.current?.contains(event.target)) setProfileOpen(false);
      if (
        notificationsOpen &&
        !notificationsPanelRef.current?.contains(event.target) &&
        !bellButtonRef.current?.contains(event.target)
      ) {
        setNotificationsOpen(false);
      }
    };
    window.addEventListener('click', onClick);
    return () => window.removeEventListener('click', onClick);
  }, [notificationsOpen]);

  const fetchNotifications = async ({ withLoader = false } = {}) => {
    if (withLoader) setNotificationsLoading(true);
    setNotificationsError('');
    try {
      const res = await api.get('/api/v1/notifications?limit=20');
      setNotifications(res.data?.data || []);
      setUnreadCount(res.data?.unread_count || 0);
    } catch (err) {
      setNotificationsError(err.response?.data?.detail?.error_description || 'Unable to load notifications');
    } finally {
      if (withLoader) setNotificationsLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications({ withLoader: false });
    const timer = window.setInterval(() => {
      fetchNotifications({ withLoader: false });
    }, 30000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!orgId || isSuperAdmin) {
      setPlanStatus(null);
      return;
    }
    api.get(`/api/v1/organizations/${orgId}/plan-status`)
      .then((res) => setPlanStatus(res.data))
      .catch(() => setPlanStatus(null));
  }, [orgId, isSuperAdmin]);

  useEffect(() => {
    setSearchQuery(searchParams.get('q') || '');
  }, [searchParams]);

  useEffect(() => {
    return () => {
      if (searchDebounceRef.current) {
        window.clearTimeout(searchDebounceRef.current);
      }
    };
  }, []);

  useEffect(() => {
    setMobileNavOpen(false);
    setProfileOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    if (mobileNavOpen) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [mobileNavOpen]);

  const handleLogout = async () => {
    setLogoutBusy(true);
    try {
      await logout();
      navigate('/login');
    } finally {
      setLogoutBusy(false);
      setLogoutConfirmOpen(false);
    }
  };

  const requestLogout = () => {
    setProfileOpen(false);
    setMobileNavOpen(false);
    setLogoutConfirmOpen(true);
  };

  const submitSearch = (event) => {
    event.preventDefault();
    const term = searchQuery.trim();
    if (!term) {
      navigate('/dashboard');
      return;
    }
    navigate(`/search?q=${encodeURIComponent(term)}`);
  };

  const clearSearch = () => {
    if (searchDebounceRef.current) {
      window.clearTimeout(searchDebounceRef.current);
    }
    setSearchQuery('');
    navigate('/dashboard');
  };

  const handleSearchChange = (value) => {
    setSearchQuery(value);
    if (searchDebounceRef.current) {
      window.clearTimeout(searchDebounceRef.current);
    }

    const term = value.trim();
    if (!term) {
      return;
    }

    searchDebounceRef.current = window.setTimeout(() => {
      navigate(`/search?q=${encodeURIComponent(term)}`);
    }, 180);
  };

  const toggleNotifications = async () => {
    setNotificationsOpen((open) => !open);
    if (!notificationsOpen) {
      await fetchNotifications({ withLoader: true });
    }
  };

  const markNotificationRead = async (notificationId) => {
    try {
      await api.patch(`/api/v1/notifications/${notificationId}/read`);
      setNotifications((current) =>
        current.map((item) => (item.id === notificationId ? { ...item, read: true } : item))
      );
      setUnreadCount((current) => Math.max(0, current - 1));
    } catch {}
  };

  const markAllNotificationsRead = async () => {
    try {
      const res = await api.patch('/api/v1/notifications/read-all');
      setNotifications((current) => current.map((item) => ({ ...item, read: true })));
      setUnreadCount(res.data?.unread_count || 0);
    } catch {}
  };

  const clearNotification = async (notificationId) => {
    try {
      const res = await api.delete(`/api/v1/notifications/${notificationId}`);
      setNotifications((current) => current.filter((item) => item.id !== notificationId));
      setUnreadCount(res.data?.unread_count ?? unreadCount);
    } catch {}
  };

  const clearAllNotifications = async () => {
    try {
      await api.delete('/api/v1/notifications');
      setNotifications([]);
      setUnreadCount(0);
    } catch {}
  };

  const formatNotificationTime = (isoValue) => {
    const when = new Date(isoValue);
    const diffSeconds = Math.floor((Date.now() - when.getTime()) / 1000);
    if (Number.isNaN(diffSeconds)) return '';
    if (diffSeconds < 60) return 'just now';
    if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
    if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
    if (diffSeconds < 604800) return `${Math.floor(diffSeconds / 86400)}d ago`;
    return when.toLocaleDateString();
  };

  const hasPermission = (permission) => isSuperAdmin || userHasPermission(claims, permission);
  const isOrgAdmin = hasRole(claims, 'org:admin');
  const account = profile || { email: claims?.email, first_name: claims?.given_name, last_name: claims?.family_name };
  const accountName = getDisplayName(account, 'Account');
  const accountEmail = profile?.email || claims?.email || '';
  const visibleNavItems = navItems.filter((item) => {
    if (item.userOnly && (isSuperAdmin || isOrgAdmin)) {
      return false;
    }
    return !item.permission || hasPermission(item.permission);
  });
  const visibleOperationsItems = operationsItems.filter((item) => !item.permission || hasPermission(item.permission));
  const brandBlock = (
    <div className="flex items-center gap-3">
      <ProductMark className="h-9 w-9" />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold text-gray-900">{PRODUCT_NAME}</h1>
        <p className="line-clamp-2 text-xs leading-4 text-gray-500">{PRODUCT_TAGLINE}</p>
      </div>
    </div>
  );
  const sidebarNav = (
    <>
      <div className="border-b border-gray-200 px-5 py-4">
        <OrgSelector />
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-5">
        <div className="space-y-1">
          {visibleNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`
              }
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </NavLink>
          ))}
        </div>

        {isSuperAdmin ? (
          <div className="space-y-1">
            <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Platform</p>
            {adminNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                    isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </div>
        ) : null}

        <div className="space-y-1">
          <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-gray-500">Operations</p>
          {visibleOperationsItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`
              }
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </NavLink>
          ))}
          {!isSuperAdmin && isOrgAdmin ? (
            <NavLink
              to="/upgrade-access"
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive ? 'bg-amber-100 text-amber-900' : 'text-amber-800 hover:bg-amber-50 hover:text-amber-900'
                }`
              }
            >
              <SecurityIcon className="h-5 w-5" />
              Billing & Plans
            </NavLink>
          ) : null}
        </div>
      </nav>

      <div className="border-t border-gray-200 px-5 py-4">
        <button onClick={requestLogout} className="btn-secondary w-full justify-center">
          <LogoutIcon className="h-4 w-4" />
          Sign out
        </button>
      </div>
    </>
  );

  return (
    <div className="app-shell">
      {mobileNavOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            className="absolute inset-0 bg-slate-900/35"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 flex w-[min(22rem,88vw)] flex-col border-r border-gray-200 bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-5">
              {brandBlock}
              <button
                onClick={() => setMobileNavOpen(false)}
                className="rounded-lg border border-gray-200 p-2 text-gray-500 hover:bg-gray-50 hover:text-gray-900"
                aria-label="Close navigation"
              >
                <XIcon className="h-4 w-4" />
              </button>
            </div>
            {sidebarNav}
          </aside>
        </div>
      ) : null}

      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-gray-200 bg-white lg:flex">
        <div className="flex h-[73px] items-center border-b border-gray-200 px-6">
          {brandBlock}
        </div>
        {sidebarNav}
      </aside>

      <div className="min-h-screen lg:ml-64">
        <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/95 backdrop-blur">
          <div className="flex min-h-[73px] items-center gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <button
              onClick={() => setMobileNavOpen(true)}
              className="rounded-lg border border-gray-200 bg-white p-2 text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900 lg:hidden"
              aria-label="Open navigation"
            >
              <MenuIcon className="h-5 w-5" />
            </button>

            <div className="min-w-0 lg:hidden">
              <p className="truncate text-sm font-semibold text-gray-900">{PRODUCT_NAME}</p>
              <p className="truncate text-[11px] text-gray-500">{accountEmail || PRODUCT_TAGLINE}</p>
            </div>

            <div className="relative hidden max-w-lg flex-1 md:block">
              <form onSubmit={submitSearch}>
                <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  className="input-field pr-10 pl-10"
                  placeholder="Search users, apps, groups, events"
                  value={searchQuery}
                  onChange={(event) => handleSearchChange(event.target.value)}
                />
                {searchQuery ? (
                  <button
                    type="button"
                    onClick={clearSearch}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-700"
                    aria-label="Clear search"
                  >
                    <XIcon className="h-4 w-4" />
                  </button>
                ) : null}
              </form>
            </div>

            <button
              ref={bellButtonRef}
              onClick={toggleNotifications}
              className="relative rounded-lg border border-gray-200 bg-white p-2 text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
              aria-label="Notifications"
            >
              <BellIcon className="h-5 w-5" />
              {unreadCount > 0 ? (
                <span className="absolute -right-1 -top-1 flex min-h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[11px] font-semibold text-white">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              ) : null}
            </button>

            <div className="relative z-20 ml-auto" ref={dropdownRef}>
              <button
                onClick={() => setProfileOpen((v) => !v)}
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                <UserAvatar
                  user={account}
                  imageUrl={profile?.profile_image_url}
                  className="h-8 w-8"
                  textClassName="text-xs"
                />
                <span className="hidden max-w-[180px] truncate sm:block">{accountName}</span>
                <ChevronDownIcon className="h-4 w-4 text-gray-400" />
              </button>
              {profileOpen ? (
                <div className="absolute right-0 mt-2 w-56 rounded-lg border border-gray-200 bg-white p-2 shadow-lg">
                  <div className="mb-2 flex items-center gap-3 rounded-md bg-gray-50 px-3 py-2">
                    <UserAvatar
                      user={account}
                      imageUrl={profile?.profile_image_url}
                      className="h-10 w-10"
                      textClassName="text-sm"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-gray-900">{accountName}</p>
                      <p className="truncate text-xs text-gray-500">{accountEmail || 'Signed-in account'}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setProfileOpen(false);
                      navigate('/settings');
                    }}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <SettingsIcon className="h-4 w-4" />
                    Profile settings
                  </button>
                  <button
                    onClick={requestLogout}
                    className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-red-700 hover:bg-red-50"
                  >
                    <LogoutIcon className="h-4 w-4" />
                    Sign out
                  </button>
                </div>
              ) : null}
            </div>
          </div>
          <div className="border-t border-gray-200 px-4 py-3 md:hidden">
            <form onSubmit={submitSearch} className="relative">
              <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                className="input-field pr-10 pl-10"
                placeholder="Search users, apps, groups, events"
                value={searchQuery}
                onChange={(event) => handleSearchChange(event.target.value)}
              />
              {searchQuery ? (
                <button
                  type="button"
                  onClick={clearSearch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-gray-700"
                  aria-label="Clear search"
                >
                  <XIcon className="h-4 w-4" />
                </button>
              ) : null}
            </form>
          </div>
        </header>

        <main className="p-4 sm:p-6 lg:p-8">
          {!isSuperAdmin && isOrgAdmin && planStatus?.access_tier === 'limited' ? (
            <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-amber-900">Free Tier Organization</p>
                  <p className="text-sm text-amber-800">
                    Your organization is currently on the free self-serve tier. Choose a paid plan to unlock higher limits and full admin access.
                  </p>
                </div>
                <button
                  onClick={() => navigate('/upgrade-access')}
                  className="inline-flex items-center justify-center rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100"
                >
                  View Plans
                </button>
              </div>
            </div>
          ) : null}
          <Outlet />
        </main>
      </div>

      {notificationsOpen ? (
        <div className="fixed inset-0 z-40 bg-slate-900/25">
          <aside
            ref={notificationsPanelRef}
            className="absolute right-0 top-0 h-full w-full max-w-md border-l border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Notifications</h2>
                <p className="text-xs text-slate-500">{unreadCount} unread</p>
              </div>
              <button
                onClick={() => setNotificationsOpen(false)}
                className="rounded-lg border border-slate-200 p-1.5 text-slate-500 hover:bg-slate-50 hover:text-slate-800"
                aria-label="Close notifications"
              >
                <XIcon className="h-4 w-4" />
              </button>
            </div>

            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
              <button onClick={() => fetchNotifications({ withLoader: true })} className="text-sm font-medium text-indigo-600 hover:text-indigo-700">
                Refresh
              </button>
              <div className="flex items-center gap-4">
                <button onClick={markAllNotificationsRead} className="text-sm font-medium text-slate-600 hover:text-slate-900">
                  Mark all read
                </button>
                <button onClick={clearAllNotifications} className="text-sm font-medium text-red-600 hover:text-red-700">
                  Clear all
                </button>
              </div>
            </div>

            <div className="h-[calc(100%-122px)] overflow-y-auto px-4 py-4">
              {notificationsLoading ? (
                <p className="py-10 text-center text-sm text-slate-500">Loading notifications...</p>
              ) : notificationsError ? (
                <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{notificationsError}</p>
              ) : notifications.length === 0 ? (
                <p className="py-10 text-center text-sm text-slate-500">No notifications yet.</p>
              ) : (
                <div className="space-y-3">
                  {notifications.map((item) => (
                    <article
                      key={item.id}
                      className={`rounded-xl border p-3 ${
                        item.read
                          ? 'border-slate-200 bg-white'
                          : 'border-indigo-200 bg-indigo-50/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
                          <p className="mt-1 text-sm leading-6 text-slate-600">{item.message}</p>
                          <p className="mt-2 text-xs text-slate-500">{formatNotificationTime(item.created_at)}</p>
                        </div>
                        {!item.read ? (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => markNotificationRead(item.id)}
                              className="rounded-md border border-indigo-200 bg-white px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                              title="Mark as read"
                              aria-label="Mark as read"
                            >
                              {/* ✓✓ */}<DoubleTickIcon/>
                            </button>
                            <button
                              onClick={() => clearNotification(item.id)}
                              className="rounded-md border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                              title="Clear notification"
                              aria-label="Clear notification"
                            >
                              x
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-medium uppercase tracking-wide text-slate-400">Read</span>
                            <button
                              onClick={() => clearNotification(item.id)}
                              className="rounded-md border border-red-200 bg-white px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                              title="Clear notification"
                              aria-label="Clear notification"
                            >
                              x
                            </button>
                          </div>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      ) : null}

      <ConfirmDialog
        open={logoutConfirmOpen}
        title="Sign Out"
        description="Do you really want to sign out of SigAuth?"
        confirmLabel="Sign out"
        cancelLabel="Stay signed in"
        tone="danger"
        busy={logoutBusy}
        onConfirm={handleLogout}
        onClose={() => {
          if (!logoutBusy) {
            setLogoutConfirmOpen(false);
          }
        }}
      />
    </div>
  );
}
