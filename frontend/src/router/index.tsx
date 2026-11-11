import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DeckShell } from '../components/layout/DeckShell';
import { EventsPage } from '../pages/Events';
import { LoginPage } from '../pages/Login';
import { RejectedPage } from '../pages/Rejected';
import { RunDetailPage } from '../pages/RunDetail';
import { RunsPage } from '../pages/Runs';
import { SchemaDiffPage } from '../pages/SchemaDiff';
import { StreamsPage } from '../pages/Streams';
import { requireAuth } from './guards';

const shell = (element: React.ReactNode) => <DeckShell>{element}</DeckShell>;

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/', loader: requireAuth, element: <Navigate to="/streams" replace /> },
  { path: '/streams', loader: requireAuth, element: shell(<StreamsPage />) },
  { path: '/events', loader: requireAuth, element: shell(<EventsPage />) },
  { path: '/runs', loader: requireAuth, element: shell(<RunsPage />) },
  { path: '/runs/:id', loader: requireAuth, element: shell(<RunDetailPage />) },
  { path: '/rejected', loader: requireAuth, element: shell(<RejectedPage />) },
  { path: '/schema', loader: requireAuth, element: shell(<SchemaDiffPage />) },
  { path: '*', element: <Navigate to="/streams" replace /> },
]);
