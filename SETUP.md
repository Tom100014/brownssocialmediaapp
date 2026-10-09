# Black Card Protocol – Setup

1. Supabase-Projekt anlegen, `supabase/migrations/init.sql` im SQL-Editor ausführen.
2. Env-Variablen (Vercel + `.env.local`): `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. Supabase → Authentication → URL Configuration: Site URL und Redirect-URLs auf die Deploy-URL setzen (`/login`, `/auth/reset`).
4. Registrieren, dann Admin setzen:
   `update public.profiles set role = 'admin' where id = (select id from auth.users where email = 'DEINE@EMAIL');`
5. Partner registrieren sich unter /login → „Café / Restaurant“ und werden im Admin-Bereich freigegeben.
