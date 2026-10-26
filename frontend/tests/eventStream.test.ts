import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readEventStream } from '../src/services/eventStream.ts';

const stream = (parts: string[]) => new ReadableStream<Uint8Array>({ start(controller) {
  for (const part of parts) controller.enqueue(new TextEncoder().encode(part));
  controller.close();
} });

test('reads split SSE frames, CRLF and multibyte tokens until explicit DONE', async () => {
  const result: unknown[] = [];
  await readEventStream(stream(['data: {"token":', '"Tiếng Việt"}\r\n\r', '\ndata: [DONE]\n\n']), event => result.push(event));
  assert.deepEqual(result, [{ token: 'Tiếng Việt' }]);
});

test('a clean EOF without DONE is an interrupted answer', async () => {
  const tokens: unknown[] = [];
  await assert.rejects(readEventStream(stream(['data: {"token":"partial"}\n\n']), event => tokens.push(event)), /interrupted/);
  assert.deepEqual(tokens, [{ token: 'partial' }]);
});

test('network failure preserves partial tokens and never requests a replay', async () => {
  const tokens: unknown[] = [];
  const source = new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode('data: {"token":"first answer"}\n\n'));
    setTimeout(() => controller.error(new Error('disconnected')), 10);
  } });
  await assert.rejects(readEventStream(source, event => tokens.push(event)), /disconnected/);
  assert.deepEqual(tokens, [{ token: 'first answer' }]);
});

test('protocol and callback errors propagate instead of being swallowed', async () => {
  await assert.rejects(readEventStream(stream(['data: invalid\n\n']), () => {}), SyntaxError);
  await assert.rejects(readEventStream(stream(['data: {"token":"new prefix"}\n\ndata: [DONE]\n\n']), () => {
    throw new Error('changed prefix');
  }), /changed prefix/);
});
