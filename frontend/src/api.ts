import axios from 'axios';

const baseURL =
  import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;

const api = axios.create({
  baseURL,
  withCredentials: true, // Required for session cookies from OIDC
});

export interface Host {
  id: number;
  name: string;
  status: string;
  created_at: string;
  projects?: {
    projects_root: string;
    available_projects: string[];
    available_tools?: string[];
  };
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
  telemetry?: {
    project_dir?: string;
    task_description?: string;
    git_branch?: string;
    git_project?: string;
    model?: string;
    tokens?: number;
    context_tokens?: number;
    current_activity?: string;
    run_time_seconds?: number;
    input_tokens?: number;
    output_tokens?: number;
    cache_read_tokens?: number;
    cache_creation_tokens?: number;
    cost_usd?: number;
    agent_status?: string;
    mcp_servers?: string[];
    last_exit_code?: number;
    last_cmd?: string;
    worktree_path?: string;
  };
}

export const getHosts = async (): Promise<Host[]> => {
  const response = await api.get('/hosts');
  return response.data;
};

export const deleteHost = async (id: number): Promise<void> => {
  await api.delete(`/hosts/${id}`);
};

export const getAgents = async (): Promise<Agent[]> => {
  const response = await api.get('/agents', { params: { status: 'active' } });
  return response.data;
};

export const spawnAgent = async (
  hostId: number,
  toolName: string,
  projectDir?: string,
  taskDescription?: string,
  sessionMode?: string,
  useWorktree?: boolean,
  cols?: number,
  rows?: number,
): Promise<Agent> => {
  const response = await api.post('/agents/spawn', {
    host_id: hostId,
    tool_name: toolName,
    project_dir: projectDir,
    task_description: taskDescription,
    session_mode: sessionMode || 'resume',
    use_worktree: useWorktree || false,
    cols: cols || 120,
    rows: rows || 40,
  });
  return response.data;
};

export const stopAgent = async (agentId: string): Promise<void> => {
  await api.post(`/agents/${agentId}/stop`);
};

export const updateTaskDescription = async (
  agentId: string,
  taskDescription: string,
): Promise<void> => {
  await api.patch(`/agents/${agentId}/task-description`, {
    task_description: taskDescription,
  });
};

export interface AgentDetail extends Agent {
  host_name: string;
}

export const getAgentDetails = async (
  agentId: string,
): Promise<AgentDetail> => {
  const response = await api.get(`/agents/${agentId}/details`);
  return response.data;
};

export const getCompanions = async (agentId: string): Promise<Agent[]> => {
  const response = await api.get(`/agents/${agentId}/companions`);
  return response.data;
};

export const getMe = async () => {
  const response = await api.get('/me');
  return response.data;
};

export interface VersionInfo {
  current: string;
  is_dev: boolean;
  latest: string | null;
  latest_url: string | null;
  update_available: boolean;
}

export const getVersion = async (): Promise<VersionInfo> => {
  const response = await api.get('/version');
  return response.data;
};

export default api;
