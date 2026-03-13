import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  withCredentials: true, // Required for session cookies from OIDC
});

export interface Host {
  id: number;
  name: string;
  status: string;
  created_at: string;
}

export interface Agent {
  id: number;
  agent_id: string;
  host_id: number;
  status: string;
  tool_name?: string;
  pid?: number;
  started_at: string;
  ended_at?: string;
}

export const getHosts = async (): Promise<Host[]> => {
  const response = await api.get('/hosts');
  return response.data;
};

export const getAgents = async (): Promise<Agent[]> => {
  const response = await api.get('/agents');
  return response.data;
};

export const spawnAgent = async (hostId: number, toolName: string): Promise<Agent> => {
  const response = await api.post('/agents/spawn', { host_id: hostId, tool_name: toolName });
  return response.data;
};

export const stopAgent = async (agentId: string): Promise<void> => {
  await api.post(`/agents/${agentId}/stop`);
};

export const getMe = async () => {
  const response = await api.get('/me');
  return response.data;
};

export default api;
