<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'dompurify';
	import { apiFetch } from '$lib/api/client';
	import { authStore } from '$lib/stores/auth.svelte';

	interface Message {
		role: 'user' | 'assistant';
		content: string;
		toolsUsed?: string[];
	}

	let messages = $state<Message[]>([]);
	let input = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	function renderMarkdown(content: string): string {
		const html = marked.parse(content, { async: false }) as string;
		return DOMPurify.sanitize(html);
	}

	async function send() {
		if (!input.trim() || loading) return;
		const message = input.trim();
		input = '';
		messages = [...messages, { role: 'user', content: message }];
		loading = true;
		error = null;
		try {
			const result = await apiFetch<{ response: string; tools_used: string[] }>(
				'/api/v1/chat',
				{
					method: 'POST',
					body: JSON.stringify({ message })
				}
			);
			messages = [
				...messages,
				{ role: 'assistant', content: result.response, toolsUsed: result.tools_used }
			];
		} catch (err) {
			error = err instanceof Error ? err.message : String(err);
		} finally {
			loading = false;
		}
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}
</script>

{#if authStore.user}
	<div class="flex-1 flex flex-col max-w-3xl w-full mx-auto px-4 py-6 gap-4">
		<div class="flex-1 flex flex-col gap-3 overflow-y-auto">
			{#if messages.length === 0}
				<p class="text-zinc-500 text-sm">
					Ask anything about your training. Detailed splits and time-series load on demand.
				</p>
			{/if}
			{#each messages as message}
				{#if message.role === 'user'}
					<div class="bubble-user whitespace-pre-wrap">{message.content}</div>
				{:else}
					<div class="bubble-assistant prose-tight">
						{@html renderMarkdown(message.content)}
						{#if message.toolsUsed && message.toolsUsed.length > 0}
							<div class="text-xs text-zinc-500 mt-1">
								tools: {message.toolsUsed.join(', ')}
							</div>
						{/if}
					</div>
				{/if}
			{/each}
			{#if loading}
				<div class="bubble-assistant text-zinc-500">…thinking</div>
			{/if}
			{#if error}
				<div class="text-red-600 text-sm">{error}</div>
			{/if}
		</div>
		<div class="flex gap-2">
			<textarea
				bind:value={input}
				onkeydown={onKey}
				rows="2"
				placeholder="Message your coach…"
				class="flex-1 rounded border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
			></textarea>
			<button
				onclick={send}
				disabled={loading || !input.trim()}
				class="rounded bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
			>
				Send
			</button>
		</div>
	</div>
{/if}

