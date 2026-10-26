import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveAPIBaseURL } from '../src/services/apiOrigin.ts';

test('local API defaults preserve the browser host for refresh cookies', () => {
  assert.equal(resolveAPIBaseURL(false, undefined, '127.0.0.1'), 'http://127.0.0.1:8000');
  assert.equal(resolveAPIBaseURL(false, '', 'localhost'), 'http://localhost:8000');
});

test('an explicit dev API is normalized while production always uses its same-origin proxy', () => {
  assert.equal(resolveAPIBaseURL(false, ' http://127.0.0.1:8001/// ', 'localhost'), 'http://127.0.0.1:8001');
  assert.equal(resolveAPIBaseURL(true, 'https://direct-provider.example/', 'nova.example'), '/api');
});
