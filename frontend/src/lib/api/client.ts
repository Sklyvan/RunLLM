import { goto } from '$app/navigation';
import { PUBLIC_API_BASE_URL } from '$env/static/public';
import { supabase } from '$lib/supabase/client';

export class ApiError extends Error {
	constructor(
		public readonly status: number,
		message: string,
		public readonly body?: unknown
	) {
		super(message);
	}
}

export class MfaRequiredError extends ApiError {
	constructor(body: unknown) {
		super(409, 'mfa_required', body);
	}
}

async function authHeaders(): Promise<HeadersInit> {
	const { data } = await supabase().auth.getSession();
	const token = data.session?.access_token;
	return token ? { authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
	const headers = {
		'content-type': 'application/json',
		...(init.headers ?? {}),
		...(await authHeaders())
	};

	const response = await fetch(`${PUBLIC_API_BASE_URL}${path}`, { ...init, headers });

	if (response.status === 401) {
		await goto('/login');
		throw new ApiError(401, 'unauthorized');
	}

	if (response.status === 409) {
		const body = await response.json().catch(() => ({}));
		if (body?.detail === 'mfa_required') {
			throw new MfaRequiredError(body);
		}
	}

	if (!response.ok) {
		const body = await response.text();
		throw new ApiError(response.status, response.statusText, body);
	}

	if (response.status === 204) {
		return undefined as T;
	}
	return (await response.json()) as T;
}

