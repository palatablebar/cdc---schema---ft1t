import type { ReactNode } from 'react';
import { useAuthStore } from '../../stores/authStore';
import type { Permission } from '../../types/models';

interface Props {
  permission: Permission;
  children: ReactNode;
  fallback: ReactNode;
}

/** 权限闸门：无权时显示只读说明（不是静默隐藏，viewer 要知道为什么点不了）。 */
export const RequireRole = ({ permission, children, fallback }: Props) => {
  const allowed = useAuthStore((state) => state.can(permission));
  return <>{allowed ? children : fallback}</>;
};
