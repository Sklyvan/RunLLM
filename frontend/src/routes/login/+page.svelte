<script lang="ts">
	import { goto } from '$app/navigation';
	import { signIn, signUp } from '$lib/stores/auth.svelte';

	let email = $state('');
	let password = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	async function submit(mode: 'signin' | 'signup') {
		loading = true;
		error = null;
		try {
			if (mode === 'signin') {
				await signIn(email, password);
			} else {
				await signUp(email, password);
			}
			await goto('/');
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex-1 flex items-center justify-center px-4">
	<div class="w-full max-w-sm flex flex-col gap-4">
		<h1 class="text-2xl font-semibold">RunLLM</h1>
		<p class="text-sm text-zinc-500">Sign in to talk to your AI running coach.</p>

		<label class="flex flex-col gap-1 text-sm">
			Email
			<input
				type="email"
				bind:value={email}
				class="rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
				autocomplete="email"
			/>
		</label>
		<label class="flex flex-col gap-1 text-sm">
			Password
			<input
				type="password"
				bind:value={password}
				class="rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
				autocomplete="current-password"
			/>
		</label>

		{#if error}
			<div class="text-sm text-red-600">{error}</div>
		{/if}

		<div class="flex gap-2">
			<button
				onclick={() => submit('signin')}
				disabled={loading}
				class="flex-1 rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
			>
				Sign in
			</button>
			<button
				onclick={() => submit('signup')}
				disabled={loading}
				class="flex-1 rounded border border-zinc-300 dark:border-zinc-700 px-4 py-2 text-sm"
			>
				Sign up
			</button>
		</div>
	</div>
</div>

