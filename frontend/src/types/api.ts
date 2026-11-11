export interface ApiErrorShape {
  code: string;
  message: string;
  detail?: string;
  trace_id?: string;
  extra?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;

  constructor(status: number, payload: ApiErrorShape) {
    super(payload.message || payload.code);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload.code;
    this.detail = payload.detail ?? '';
  }
}

export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}
