import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  withCredentials: true, // Required for session cookies from OIDC
});

export interface Machine {
  id: number;
  name: string;
  created_at: string;
}

export interface Session {
  id: number;
  session_id: string;
  machine_id: number;
  status: string;
  started_at: string;
  ended_at?: string;
}

export const getMachines = async (): Promise<Machine[]> => {
  const response = await api.get('/machines');
  return response.data;
};

export const getSessions = async (): Promise<Session[]> => {
  const response = await api.get('/sessions');
  return response.data;
};

export const getMe = async () => {
  const response = await api.get('/me');
  return response.data;
};

export default api;
