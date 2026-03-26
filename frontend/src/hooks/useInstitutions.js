import { useState, useEffect } from 'react';
import * as API from '../api/index.js';

export function useInstitutions() {
  const [institutions, setInstitutions] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    API.getInstitutions()
      .then((d) => {
        setInstitutions(d.institutions);
      })
      .catch((e) => setError(e.message));
  }, []);

  return { institutions, error };
}
