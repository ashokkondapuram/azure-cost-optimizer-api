import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import { fetchNavAccessMe } from '../api/settings';
import { canViewNavPath } from '../utils/navAccess';

export function useNavAccess() {
  const { user, isSuperuser } = useAuth();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['nav-access', user?.id],
    queryFn: fetchNavAccessMe,
    enabled: !!user?.id,
    staleTime: 60_000,
    retry: 0,
  });

  const allowedPaths = data?.allowed_paths ?? user?.allowed_paths;

  const canView = (path) => canViewNavPath(path, allowedPaths, { isSuperuser });

  return {
    allowedPaths,
    catalog: data?.catalog,
    loading: isLoading && !isError,
    canView,
    refetch,
  };
}
