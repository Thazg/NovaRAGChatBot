/** Read one SSE response. A closed connection is not a completion event. */
export async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: unknown) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let data: string[] = [];
  let completed = false;

  const line = (value: string) => {
    if (value === '') {
      if (!data.length) return;
      const payload = data.join('\n');
      data = [];
      if (payload === '[DONE]') {
        completed = true;
        return;
      }
      // Callback/protocol errors must propagate, not be swallowed as parse errors.
      onEvent(JSON.parse(payload));
    } else if (value.startsWith('data:')) {
      data.push(value.slice(5).replace(/^ /, ''));
    }
  };

  try {
    while (!completed) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary: number;
      while ((boundary = buffer.indexOf('\n')) >= 0 && !completed) {
        line(buffer.slice(0, boundary).replace(/\r$/, ''));
        buffer = buffer.slice(boundary + 1);
      }
      if (done) {
        if (!completed) throw new Error('Response interrupted. Regenerate the answer to try again.');
        break;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
