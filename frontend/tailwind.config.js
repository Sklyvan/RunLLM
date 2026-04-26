/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{html,js,svelte,ts}'],
	darkMode: 'class',
	theme: {
		extend: {
			fontFamily: {
				sans: ['system-ui', '-apple-system', 'Segoe UI', 'sans-serif']
			}
		}
	},
	plugins: []
};

