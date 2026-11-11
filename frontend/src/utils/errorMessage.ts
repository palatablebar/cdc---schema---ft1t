import { ApiError } from '../types/api';

/** 统一错误文案：403 要说清角色不够，422 要带上后端 detail。 */
export const errorMessage = (error: unknown): string => {
  if (error instanceof ApiError) {
    if (error.status === 403) return `403 权限不足：${error.message}`;
    if (error.status === 401) return '401 登录已失效，请重新登录';
    if (error.detail) return `${error.message}（${error.detail}）`;
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return '未知错误';
};
