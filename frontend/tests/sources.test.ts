import { test } from 'node:test';
import assert from 'node:assert/strict';
import { formatSource, formatAnswerWithSources } from '../src/services/sources.ts';

test('source is plain file, page and exact extracted line range', () => {
  assert.equal(formatSource({ file_name: 'report.pdf', page: 4, line_start: 12, line_end: 18 }), 'Source: report.pdf, Page 4, Lines 12–18');
});

test('clipboard/share/export replace internal IDs with readable source locations', () => {
  const sources = [{ id: 'E1', file_name: 'paper_[v2].pdf', page: 2, line_start: 6, line_end: 9 }];
  assert.equal(formatAnswerWithSources('Evidence [E1].', sources),
    'Evidence (Source: paper_[v2].pdf, Page 2, Lines 6–9).');
  assert.equal(formatAnswerWithSources('Uncited answer.', sources),
    'Uncited answer.\n\nSource: paper_[v2].pdf, Page 2, Lines 6–9');
  assert.match(formatAnswerWithSources('Evidence [E1].', sources, true), /paper\\_\\\[v2\\\]/);
  assert.equal(formatAnswerWithSources('Unknown [E9].', []), 'Unknown [E9].');
});

test('text files and legacy indexes do not invent page or line numbers', () => {
  assert.equal(formatSource({ file_name: 'notes.txt', page: null, line_start: 3, line_end: 7 }), 'Source: notes.txt, Lines 3–7');
  assert.match(formatSource({ file_name: 'old.pdf', page: null, line_start: null, line_end: null }), /location unavailable; reindex/);
});
