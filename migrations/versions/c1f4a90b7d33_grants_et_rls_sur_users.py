"""Droits complets pour `ghostcal_app`, et RLS forcée sur `users`.

Prépare la bascule du rôle applicatif. Aujourd'hui la production se connecte en
`postgres`, **superutilisateur**, qui contourne toute politique de sécurité au niveau
ligne — même sous `FORCE ROW LEVEL SECURITY`. Toute l'isolation repose donc sur les
clauses `WHERE` du code, et trois requêtes les avaient oubliées (member-keys, rotation,
analytics). Elles sont corrigées ; la cause, non.

Deux choses ici, et une seule est risquée.

─── 1. Les droits : `ON ALL TABLES`, pas une énumération ───

`ghostcal_app` n'avait de droits que sur six tables. L'énumérer table par table
garantirait qu'une table future casse l'application jusqu'à une migration de droits.

Le vrai argument est ailleurs : **les droits sont au niveau table, la RLS au niveau
ligne**. `ghostcal_app` reste `NOSUPERUSER NOBYPASSRLS`, donc les politiques gardent les
lignes quelle que soit l'étendue des droits. Élargir les droits n'élargit pas ce qu'on
voit — c'est la RLS qui décide.

C'est aussi le motif que `scripts/bootstrap_roles.sql` a déjà choisi.

─── 2. La RLS sur `users` : la partie à valider ───

`users` n'avait **aucune** politique, et `rowsecurity = false`. Même sous `ghostcal_app`,
la jointure `User ⨝ Membership` resterait donc ouverte : c'est ce qui rendait le filtre
applicatif indispensable plutôt que redondant.

`FORCE` en plus d'`ENABLE` : sans lui, le **propriétaire** de la table échappe aux
politiques. Or c'est sous le propriétaire que tournent les fonctions `SECURITY DEFINER`.

⚠️ **ET C'EST PRÉCISÉMENT LE RISQUE.** `provision_account` est `SECURITY DEFINER` et fait
`INSERT INTO users` — au moment de l'inscription, quand « le créateur n'est pas encore
membre » et qu'aucun GUC de session n'est posé. Sous `FORCE`, cette fonction devient
soumise aux politiques comme tout le monde. Sans politique d'insertion permissive,
**l'inscription casse**.

Le dépôt connaît déjà cette interaction : `auth_repository._bind_user_and_org` l'écrit
noir sur blanc — « under FORCE ROW LEVEL SECURITY the definer functions inherit no sight
of their own ». La leçon existait ; elle n'avait pas traversé jusqu'à `users`.

D'où la politique `users_insert` en `WITH CHECK (true)` : insérer une ligne `users`
n'expose rien — le risque est en lecture, et la lecture est fermée par `users_select`.

─── Ce que cette migration ne prouve PAS ───

Elle est écrite sans base de données sous la main. La CI l'exécutera, mais **sous le rôle
admin** : elle vérifiera la syntaxe, pas la sémantique. Ce qu'il faut éprouver avant de
basculer la chaîne de connexion, et qui demande une vraie base :

1. une **inscription** aboutit (c'est `provision_account` sous `FORCE`) ;
2. une **connexion** aboutit ;
3. la **liste des membres** d'une organisation rend ses membres, et eux seuls ;
4. la **mise à jour de profil** et le **changement de clés** aboutissent ;
5. la **suppression de compte** aboutit.

Tant que ces cinq-là n'ont pas tourné sous `ghostcal_app`, la bascule ne doit pas se
faire. L'application reste en superutilisateur entre les deux : rien n'est protégé, mais
rien n'est cassé — c'est un état sûr pour s'arrêter.

Revision ID: c1f4a90b7d33
Revises: a7d3f81c60e2
"""

from __future__ import annotations

from alembic import op

revision = "c1f4a90b7d33"
# Rattachée à la migration du second facteur, arrivée entre-temps. Les deux
# partaient du même parent, ce qui donnait deux têtes et un `upgrade head`
# impossible.
down_revision = "b8e2f47a91c3"
branch_labels = None
depends_on = None

_USER_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
_ORG_GUC = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    # ── Droits ──────────────────────────────────────────────────────────────────────
    # `IF EXISTS` sur le rôle : une base de développement ou de CI peut ne pas l'avoir,
    # et une migration qui échoue là empêcherait toute la suite de s'appliquer.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
            GRANT USAGE ON SCHEMA public TO ghostcal_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON ALL TABLES IN SCHEMA public TO ghostcal_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ghostcal_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ghostcal_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public
              GRANT USAGE, SELECT ON SEQUENCES TO ghostcal_app;
          END IF;
        END
        $$
        """
    )

    # ── RLS sur `users` ─────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")

    # Lecture : soi-même, ou quelqu'un qui partage l'organisation courante. C'est ce dont
    # l'application a besoin — listes de membres, clés publiques de l'équipe — et rien de
    # plus. Un annuaire de tous les utilisateurs du serveur n'est pas au menu.
    op.execute(
        f"""
        CREATE POLICY users_select ON users
            FOR SELECT
            USING (
                id = {_USER_GUC}
                OR id IN (
                    SELECT m.user_id FROM memberships m
                    WHERE m.organization_id = {_ORG_GUC}
                )
            )
        """
    )

    # Insertion : la ligne qu'on insère doit être celle qu'on déclare être.
    #
    # `WITH CHECK (true)` ne suffisait pas, et la raison est instructive :
    # `provision_account` fait `INSERT INTO users … RETURNING id`, et **la clause
    # `RETURNING` exige que la ligne soit lisible** — donc que `users_select` la laisse
    # passer. Au moment de l'inscription, `app.current_user_id` n'est pas posé, puisque
    # l'utilisateur n'existe pas encore. La lecture échouait, pas l'écriture.
    #
    # Le remède est déjà dans la fonction, deux instructions plus bas, appliqué à
    # l'organisation : engendrer l'identifiant soi-même, poser le GUC dessus, puis insérer
    # avec cet identifiant explicite. Son commentaire le dit — « the row that defines the
    # tenant is the row being inserted ». La même chose valait pour `users` ; personne ne
    # l'avait vu parce que `users` n'était sous aucune politique.
    op.execute(
        f"""
        CREATE POLICY users_insert ON users
            FOR INSERT
            WITH CHECK (id = {_USER_GUC})
        """
    )

    # Écriture et suppression : soi-même uniquement. `WITH CHECK` autant que `USING`,
    # sinon on pourrait modifier sa propre ligne pour en faire celle d'un autre.
    op.execute(
        f"""
        CREATE POLICY users_update ON users
            FOR UPDATE
            USING (id = {_USER_GUC})
            WITH CHECK (id = {_USER_GUC})
        """
    )
    op.execute(f"CREATE POLICY users_delete ON users FOR DELETE USING (id = {_USER_GUC})")

    # ── `provision_account` pose le contexte de l'utilisateur qu'elle crée ──────────
    #
    # Même correction que celle faite le 2026-08-?? pour l'organisation, appliquée à
    # l'utilisateur : engendrer l'identifiant, le déclarer, puis insérer.
    #
    # Sans cela, `INSERT … RETURNING id` échoue sous FORCE, parce que `RETURNING` relit la
    # ligne et qu'aucune politique ne la désigne encore. Le GUC est transaction-local
    # (`true`) et restauré en fin de fonction, comme celui de l'organisation.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION provision_account(
            p_email text, p_name text, p_password_hash text, p_org_name text, p_org_slug text
        ) RETURNS TABLE(user_id uuid, organization_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $fn$
        DECLARE
            v_user_id uuid;
            v_org_id uuid;
            v_prev_org text;
            v_prev_user text;
        BEGIN
            v_user_id := gen_random_uuid();
            v_prev_user := current_setting('app.current_user_id', true);
            PERFORM set_config('app.current_user_id', v_user_id::text, true);

            INSERT INTO users (id, email, name, timezone)
                VALUES (v_user_id, p_email, p_name, 'UTC');
            INSERT INTO user_credentials (user_id, password_hash)
                VALUES (v_user_id, p_password_hash);

            v_org_id := gen_random_uuid();
            v_prev_org := current_setting('app.current_org_id', true);
            PERFORM set_config('app.current_org_id', v_org_id::text, true);

            INSERT INTO organizations (id, name, slug)
                VALUES (v_org_id, p_org_name, p_org_slug);
            INSERT INTO memberships (organization_id, user_id, role)
                VALUES (v_org_id, v_user_id, 'owner');

            PERFORM set_config('app.current_org_id', coalesce(v_prev_org, ''), true);
            PERFORM set_config('app.current_user_id', coalesce(v_prev_user, ''), true);

            RETURN QUERY SELECT v_user_id, v_org_id;
        END;
        $fn$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_delete ON users")
    op.execute("DROP POLICY IF EXISTS users_update ON users")
    op.execute("DROP POLICY IF EXISTS users_insert ON users")
    op.execute("DROP POLICY IF EXISTS users_select ON users")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
    # Les droits ne sont pas révoqués : les retirer casserait une application déjà
    # basculée sur `ghostcal_app`, et un `downgrade` sert à défaire un défaut, pas à
    # provoquer une panne. Les révoquer à la main si c'est vraiment voulu.
