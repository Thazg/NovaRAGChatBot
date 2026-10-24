type Source = {
  id?: string;
  file_name: string;
  page: number | null;
  line_start: number | null;
  line_end: number | null;
};

export function formatSource(source: Source): string {
  const location = [source.file_name];
  if (source.page) location.push(`Page ${source.page}`);
  if (source.line_start) location.push(`Lines ${source.line_start}–${source.line_end || source.line_start}`);
  if (!source.page && !source.line_start) location.push('location unavailable; reindex this document');
  return `Source: ${location.join(' · ')}`;
}

/** The same readable citations for display, clipboard, sharing and text export. */
export function formatAnswerWithSources(content: string, sources: Source[], markdown = false): string {
  const escape = (text: string) => markdown ? text.replace(/[\\`*_[\]<>]/g, '\\$&') : text;
  let cited = false;
  const answer = content.replace(/\[(E\d+)\]/g, (match, id: string) => {
    const source = sources.find(item => item.id === id);
    if (!source) return match;
    cited = true;
    return `(${escape(formatSource(source))})`;
  });
  if (cited || !sources.length) return answer;
  return `${answer}\n\n${sources.map(source => escape(formatSource(source))).join('\n')}`;
}
