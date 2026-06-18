import { api } from "./client";

export interface GenerateRequest {
  description: string;
  project_id?: string;
}

export interface GenerateResponse {
  generation_id: string;
  detected_intent: string;
  suggested_stub_name: string;
  spec_format: string;
  spec_content: string;
  estimated_stub_count: number;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
}

export interface GenerationHistoryItem {
  generation_id: string;
  detected_intent: string;
  suggested_stub_name: string;
  estimated_stub_count: number;
  model_used: string;
  created_at: string;
}

export const aiApi = {
  generate: (body: GenerateRequest) =>
    api.post<GenerateResponse>("/api/v1/ai/generate", body),

  history: () =>
    api.get<GenerationHistoryItem[]>("/api/v1/ai/history"),
};
