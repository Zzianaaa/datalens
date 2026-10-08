// Spreadsheet formula prefixes are escaped for text cells.
export function csvCell(value) {
  if (value == null) return '';
  let text = String(value);
  if (typeof value === 'string' && /^[\s]*[=+\-@]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export function resultCSV(result) {
  return '\uFEFF' + [result.columns, ...result.rows].map(row => row.map(csvCell).join(',')).join('\r\n');
}
