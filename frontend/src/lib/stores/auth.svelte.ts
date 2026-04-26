import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '$lib/supabase/client';

interface AuthState {
	session: Session | null;
	user: User | null;
	loading: boolean;
}

export const authStore = $state<AuthState>({
	session: null,
	user: null,
	loading: true
});

export async function initAuth(): Promise<void> {
	const { data } = await supabase().auth.getSession();
	authStore.session = data.session;
	authStore.user = data.session?.user ?? null;
	authStore.loading = false;

	supabase().auth.onAuthStateChange((_event, session) => {
		authStore.session = session;
		authStore.user = session?.user ?? null;
	});
}

export async function signIn(email: string, password: string): Promise<void> {
	const { error } = await supabase().auth.signInWithPassword({ email, password });
	if (error) throw error;
}

export async function signUp(email: string, password: string): Promise<void> {
	const { error } = await supabase().auth.signUp({ email, password });
	if (error) throw error;
}

export async function signOut(): Promise<void> {
	await supabase().auth.signOut();
}

