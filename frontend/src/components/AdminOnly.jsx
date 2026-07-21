import { useAuth } from '../context/AuthContext';

/** Renders children only for signed-in administrators. */
export default function AdminOnly({ children, fallback = null }) {
  const { isAdmin } = useAuth();
  if (!isAdmin) return fallback;
  return children;
}
