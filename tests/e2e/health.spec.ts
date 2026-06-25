import { test, expect } from '@playwright/test';

test('API health check', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
});

test('API health returns JSON with status ok', async ({ request }) => {
  const response = await request.get('/health');
  const body = await response.json();
  expect(body).toHaveProperty('status');
});
