import { redirect } from 'react-router-dom';
import { tokenStore } from '../api/client';

export const requireAuth = () => {
  if (!tokenStore.get()) return redirect('/login');
  return null;
};
