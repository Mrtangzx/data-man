export interface Asset {
  id: string;
  kind: "avatar" | "voice";
  name: string;
  engine: string;
  status: string;
  source_name: string | null;
  content_type: string | null;
  size_bytes: number | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface Deployment {
  id: string;
  name: string;
  engine_kind: "realtime" | "render";
  target_kind: string;
  revision: {
    id: string;
    revision: number;
    adapter_type: string;
    image_digest: string | null;
    model_hash: string | null;
    capabilities: Record<string, unknown>;
  };
  observation: {
    observed_at: string;
    healthy: boolean;
    warm: boolean;
    latency_ms: number | null;
    details: Record<string, unknown>;
  } | null;
}

export interface RealtimeSession {
  session_id: string;
  state: string;
  state_version: number;
  credential_epoch: number;
  credential: string;
  expires_in_seconds: number;
  engine_type: string;
  client_config: Record<string, unknown>;
}

export interface RealtimeTurn {
  turn_id: string;
  sequence: number;
  user_text: string;
  assistant_text: string;
  state: string;
}

export interface VideoJob {
  id: string;
  state: string;
  desired_state: string;
  state_version: number;
  stage: string;
  progress: number | null;
  script: string;
  avatar_version_id: string;
  voice_enrollment_id: string;
  engine_deployment_id: string;
  output: Record<string, unknown>;
  artifact_id: string | null;
  download_url: string | null;
  error: Record<string, unknown> | null;
  event_cursor: number;
  created_at: string;
  updated_at: string;
}

export interface SystemSummary {
  profile: string;
  mock_mode: boolean;
  assets_ready: number;
  deployments_healthy: number;
  active_jobs: number;
  upstream_gate_resolved: boolean;
}

export interface LlmProvider {
  id: string;
  name: string;
  base_url: string;
  model: string;
  configured: boolean;
  api_key_hint: string;
}

export interface LlmProvidersResponse {
  providers: LlmProvider[];
  active_provider_id: string;
}

export interface ComputePlan {
  mode: string;
  provider: string;
  gpu: string;
  local_gpu_required: boolean;
  scale_to_zero: boolean;
  rate_usd_per_second: number;
  rate_usd_per_hour: number;
  monthly_credit_usd: number;
  free_quota_label: string;
  estimated_gpu_cost_per_output_minute_usd: number;
  estimate_assumption: string;
  checked_at: string;
  source_url: string;
  status: "recommended" | "configured";
  next_action: string;
}

export interface ApiErrorBody {
  code?: string;
  message?: string;
  details?: { fix?: string };
  request_id?: string;
}
