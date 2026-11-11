interface Props {
  value: number | string | null | undefined;
  width?: number;
}

/** 等宽数字单元：LSN / 计数定宽，避免表格抖动。 */
export const MonoNum = ({ value, width }: Props) => (
  <span className="mono" style={width ? { display: 'inline-block', minWidth: width, textAlign: 'right' } : undefined}>
    {value === null || value === undefined ? '—' : value}
  </span>
);
