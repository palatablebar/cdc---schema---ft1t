import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import { onUnauthorized } from './api/client';
import { router } from './router';
import { useAuthStore } from './stores/authStore';
import { useStreamStore } from './stores/streamStore';

export const App = () => {
  const loadMe = useAuthStore((state) => state.loadMe);
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);
  const loadBoard = useStreamStore((state) => state.loadBoard);

  useEffect(() => {
    void loadMe();
    onUnauthorized(() => {
      logout();
      window.location.assign('/login');
    });
  }, [loadMe, logout]);

  useEffect(() => {
    if (user) void loadBoard();
  }, [user, loadBoard]);

  return <RouterProvider router={router} />;
};
