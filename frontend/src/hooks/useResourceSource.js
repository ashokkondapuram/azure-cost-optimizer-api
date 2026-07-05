import { useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

/**
 * dataSource: 'db' (default) | 'live' (admin only, after Fetch from Azure).
 */
export default function useResourceSource() {
  const { isAdmin } = useAuth();
  const [dataSource, setDataSource] = useState('db');

  const fetchFromAzure = useCallback(() => {
    if (isAdmin) setDataSource('live');
  }, [isAdmin]);
  const resetToDatabase = useCallback(() => setDataSource('db'), []);

  return {
    dataSource: isAdmin ? dataSource : 'db',
    isLive: isAdmin && dataSource === 'live',
    fetchFromAzure,
    resetToDatabase,
    isAdmin,
  };
}
