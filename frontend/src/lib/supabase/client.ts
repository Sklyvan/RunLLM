import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { PUBLIC_SUPABASE_ANON_KEY, PUBLIC_SUPABASE_URL } from '$env/static/public';

let _client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
	if (_client === null) {
		_client = createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY, {
			auth: {
				persistSession: true,
				autoRefreshToken: true
			}
		});
	}
	return _client;
}

