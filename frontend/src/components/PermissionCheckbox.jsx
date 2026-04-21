import React from 'react';

const ALL_PERMISSIONS = {
  'User': ['user:create', 'user:read', 'user:update', 'user:delete', 'user:reset_password'],
  'Application': ['app:create', 'app:read', 'app:update', 'app:delete', 'app:group:assign', 'app:group:update'],
  'Group': ['group:create', 'group:read', 'group:update', 'group:delete', 'group:member:add', 'group:member:remove', 'group:role:assign', 'group:role:update'],
  'Organization': ['org:read', 'org:update'],
  'Role': ['role:create', 'role:read', 'role:update'],
  'Audit': ['audit:read'],
};

export default function PermissionCheckbox({ selected = [], onChange }) {
  const handleToggle = (perm) => {
    if (selected.includes(perm)) {
      onChange(selected.filter(p => p !== perm));
    } else {
      onChange([...selected, perm]);
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {Object.entries(ALL_PERMISSIONS).map(([category, perms]) => (
        <div key={category} className="card">
          <h4 className="text-sm font-semibold text-dark-200 mb-3">{category}</h4>
          <div className="space-y-2">
            {perms.map(perm => (
              <label key={perm} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  checked={selected.includes(perm)}
                  onChange={() => handleToggle(perm)}
                  className="w-4 h-4 rounded border-dark-500 bg-dark-700 text-primary-500 focus:ring-primary-500/50"
                />
                <span className="text-sm text-dark-300 group-hover:text-dark-100 transition-colors">
                  {perm}
                </span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
