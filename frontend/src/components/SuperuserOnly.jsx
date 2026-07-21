import { useAuth } from '../context/AuthContext';

/** Renders children only for signed-in superusers. */
export default function SuperuserOnly({ children, fallback = null }) {
  const { isSuperuser } = useAuth();
  if (!isSuperuser) return fallback;
  return children;
}
