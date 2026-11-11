/** 前端角色能力矩阵：与 backend/src/constants/roles.py PERMISSIONS 对应。 */
import type { Permission, Role } from '../types/models';

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: [
    'streams:read',
    'streams:write',
    'events:read',
    'runs:read',
    'runs:trigger',
    'rejected:read',
    'rejected:replay',
    'schema:read',
    'schema:write',
    'audit:read',
  ],
  engineer: ['streams:read', 'events:read', 'runs:read', 'runs:trigger', 'rejected:read', 'rejected:replay', 'schema:read', 'schema:write', 'audit:read'],
  viewer: ['streams:read', 'events:read', 'runs:read', 'rejected:read', 'schema:read'],
};

export const can = (role: Role | undefined, permission: Permission): boolean => {
  if (!role) return false;
  return ROLE_PERMISSIONS[role].includes(permission);
};
