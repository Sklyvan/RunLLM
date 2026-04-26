<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { authStore, initAuth, signOut } from '$lib/stores/auth.svelte';

	let { children } = $props();

	let theme = $state<'light' | 'dark'>('light');

	onMount(async () => {
		const stored = localStorage.getItem('theme');
		theme = stored === 'dark' ? 'dark' : 'light';
		applyTheme();
		await initAuth();
	});

	$effect(() => {
		if (authStore.loading) return;
		const path = $page.url.pathname;
		if (!authStore.user && path !== '/login') {
			goto('/login');
		}
	});

	function applyTheme() {
		document.documentElement.classList.toggle('dark', theme === 'dark');
		localStorage.setItem('theme', theme);
	}

	function toggleTheme() {
		theme = theme === 'dark' ? 'light' : 'dark';
		applyTheme();
	}

	async function logout() {
		await signOut();
		goto('/login');
	}
</script>

<div class="min-h-screen flex flex-col">
	{#if authStore.user}
		<header class="border-b border-zinc-200 dark:border-zinc-800 px-6 py-3 flex items-center justify-between">
			<a href="/" class="font-semibold">RunLLM</a>
			<nav class="flex items-center gap-4 text-sm">
				<span class="text-zinc-500">{authStore.user.email}</span>
				<a href="/settings" class="hover:underline">Settings</a>
				<button onclick={toggleTheme} class="hover:underline">{theme === 'dark' ? '☀' : '☾'}</button>
				<button onclick={logout} class="hover:underline">Sign out</button>
			</nav>
		</header>
	{/if}
	<main class="flex-1 flex flex-col">
		{@render children()}
	</main>
</div>

