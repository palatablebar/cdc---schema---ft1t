import type { SchemaField } from '../types/models';

/** 把字段集合渲染成一行 DDL 摘要，供页面顶部显示（只做字符串拼装）。 */
export const ddlSignature = (fields: SchemaField[]): string =>
  fields
    .map((field) => {
      const parts = [field.name, field.type];
      if (!field.nullable) parts.push('NOT NULL');
      if (field.default !== null && field.default !== undefined) parts.push(`DEFAULT ${String(field.default)}`);
      if (field.is_pk) parts.push('PK');
      return parts.join(' ');
    })
    .join(', ');

export const fieldTypeText = (field: SchemaField | null): string => {
  if (!field) return '—';
  const bits = [field.type];
  if (!field.nullable) bits.push('NOT NULL');
  if (field.default !== null && field.default !== undefined) bits.push(`DEFAULT ${String(field.default)}`);
  return bits.join(' · ');
};

export const highlightSql = (sql: string): string =>
  sql
    .replace(/(--[^\n]*)/g, '<span class="faint">$1</span>')
    .replace(
      /\b(ALTER|TABLE|ADD|COLUMN|DROP|CREATE|SELECT|FROM|WHERE|UPDATE|SET|NOT|NULL|DEFAULT|TYPE|USING|BEGIN|COMMIT|PRIMARY|KEY|COUNT|GROUP|BY|HAVING|AS|INTO|VALUES|IS)\b/g,
      '<span class="kw">$1</span>',
    );
