<script lang="ts">
	import { onMount } from 'svelte';
	import { apiFetch, MfaRequiredError } from '$lib/api/client';

	interface SyncReport {
		created: number;
		skipped: number;
		failed: number;
		errors: [string, string][];
	}

	interface Status {
		has_credentials: boolean;
		last_sync_at: string | null;
		activity_count: number;
	}

	let email = $state('');
	let password = $state('');
	let mfaCode = $state('');
	let needsMfa = $state(false);
	let saving = $state(false);
	let syncing = $state(false);
	let error = $state<string | null>(null);
	let info = $state<string | null>(null);
	let status = $state<Status | null>(null);
	let lastReport = $state<SyncReport | null>(null);

	async function loadStatus() {
		try {
			status = await apiFetch<Status>('/api/v1/garmin/status');
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		}
	}

	onMount(loadStatus);

	async function saveCredentials() {
		saving = true;
		error = null;
		info = null;
		try {
			const result = await apiFetch<{ status: string }>('/api/v1/garmin/credentials', {
				method: 'POST',
				body: JSON.stringify({ email, password })
			});
			if (result.status === 'mfa_required') {
				needsMfa = true;
			} else {
				info = 'Garmin credentials saved.';
				password = '';
				await loadStatus();
			}
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			saving = false;
		}
	}

	async function submitMfa() {
		saving = true;
		error = null;
		try {
			await apiFetch('/api/v1/garmin/mfa', {
				method: 'POST',
				body: JSON.stringify({ code: mfaCode })
			});
			needsMfa = false;
			mfaCode = '';
			info = 'MFA accepted.';
			await loadStatus();
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			saving = false;
		}
	}

	async function syncNow() {
		syncing = true;
		error = null;
		info = null;
		try {
			lastReport = await apiFetch<SyncReport>('/api/v1/garmin/sync', { method: 'POST' });
			await loadStatus();
		} catch (err) {
			if (err instanceof MfaRequiredError) {
				needsMfa = true;
				return;
			}
			error = err instanceof Error ? err.message : String(err);
		} finally {
			syncing = false;
		}
	}
</script>

<div class="flex-1 max-w-2xl w-full mx-auto px-4 py-6 flex flex-col gap-6">
	<h1 class="text-xl font-semibold">Settings</h1>

	{#if status}
		<section class="rounded border border-zinc-200 dark:border-zinc-800 p-4 text-sm flex flex-col gap-1">
			<div>Garmin credentials: {status.has_credentials ? 'on file' : 'not set'}</div>
			<div>Last sync: {status.last_sync_at ?? 'never'}</div>
			<div>Activities stored: {status.activity_count}</div>
		</section>
	{/if}

	<section class="flex flex-col gap-3">
		<h2 class="text-sm font-medium">Garmin account</h2>
		<label class="flex flex-col gap-1 text-sm">
			Email
			<input
				type="email"
				bind:value={email}
				class="rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2"
			/>
		</label>
		<label class="flex flex-col gap-1 text-sm">
			Password
			<input
				type="password"
				bind:value={password}
				class="rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2"
			/>
		</label>
		<button
			onclick={saveCredentials}
			disabled={saving || !email || !password}
			class="self-start rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
		>
			Save
		</button>

		{#if needsMfa}
			<div class="border-t border-zinc-200 dark:border-zinc-800 pt-3 mt-3 flex flex-col gap-2">
				<p class="text-sm">Garmin requires a multi-factor code.</p>
				<input
					bind:value={mfaCode}
					inputmode="numeric"
					class="rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm"
					placeholder="MFA code"
				/>
				<button
					onclick={submitMfa}
					disabled={saving || !mfaCode}
					class="self-start rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
				>
					Submit code
				</button>
			</div>
		{/if}
	</section>

	<section class="flex flex-col gap-2">
		<h2 class="text-sm font-medium">Sync</h2>
		<button
			onclick={syncNow}
			disabled={syncing}
			class="self-start rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
		>
			{syncing ? 'Syncing…' : 'Sync now'}
		</button>
		{#if lastReport}
			<p class="text-sm text-zinc-500">
				created {lastReport.created}, skipped {lastReport.skipped}, failed {lastReport.failed}
			</p>
		{/if}
	</section>

	{#if error}
		<div class="text-sm text-red-600">{error}</div>
	{/if}
	{#if info}
		<div class="text-sm text-emerald-600">{info}</div>
	{/if}
</div>

