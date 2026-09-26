"""Rouvrir les chemins légitimes de `users`, et reprendre un droit que la précédente avait rendu.

`c1f4a90b7d33` a posé `FORCE ROW LEVEL SECURITY` sur `users` et quatre politiques. Mesuré sur une
base réelle le 2026-09-26 : **32 tests d'intégration sur 162 tombent**, et ils tombent tous pour la
même raison — l'application lit et écrit `users` à travers `db_session()`, qui ne déclare
personne.

─── Ce que la mesure a montré, et que la relecture ne montrait pas ───

Deux modes de défaillance, et le second est le dangereux.

En **lecture**, la ligne disparaît et l'appelant lève : « utilisateur inconnu », « identifiants
invalides ». Bruyant, donc trouvable.

En **écriture**, rien ne lève. `UPDATE users SET email_verified_at = now() WHERE id = :i` sans GUC
rend `rowcount = 0`, sans erreur, et personne ne regarde `rowcount`. Conséquence mesurée : la
vérification d'adresse **ne fait rien**, en silence. Le compte reste non vérifié, donc la connexion
le refuse et l'invitation le refuse — à trois appels de distance de la cause.

C'est la forme que Clara avait nommée : la lecture dit « absent », l'écriture dit « existe déjà ».
`keypairs.set` en est l'illustration exacte — son `UPDATE … WHERE zk_public_key IS NULL` ne touche
aucune ligne, et le service traduit ce zéro en `KeypairAlreadySet` sur un compte qui n'a jamais eu
de clé.

─── Le remède, et pourquoi il n'ajoute aucune fonction `SECURITY DEFINER` ───

Sur les dix-sept endroits qui touchent `users`, **seize** tiennent déjà un identifiant : celui de
l'appelant authentifié, ou celui qu'un jeton vient de résoudre. Il n'y avait rien à ouvrir, juste à
**déclarer plus tôt** ce que le code savait déjà. C'est fait côté Python, avec `bind_user`, qui
existait.

Le **dix-septième** est la connexion par adresse : elle ne tient qu'une adresse tapée dans un
formulaire, et aucun identifiant. C'est le seul endroit qui demandait quelque chose de nouveau.

Une fonction `SECURITY DEFINER` n'y aurait rien résolu. Sous `FORCE`, une fonction définie par le
propriétaire n'hérite d'aucune vue à elle — `_bind_user_and_org` et `store_member_key` l'ont déjà
écrit noir sur blanc, chacun après l'avoir mesuré. Elle aurait donc eu besoin, elle aussi, d'une
politique pour voir quoi que ce soit : la brèche en plus, sans le bénéfice.

D'où `users_email_lookup`, une politique à valeur déclarée, de la même forme que
`organizations_slug_lookup`, `invitations_token_read` et `organizations_invitation_read` :
**nommez une valeur, voyez la ligne qui la porte.**

Ce qu'elle ne rouvre pas est le point : une requête qui oublie son `WHERE` continue de ne rien
rendre, puisque rien n'a été déclaré. La politique s'ouvre sur une déclaration explicite, jamais
par défaut. Au maximum elle rend **une** ligne, à qui connaissait déjà l'adresse à demander — la
question à laquelle le formulaire de connexion répond de toute façon.

─── `audit_events` : la migration précédente a défait une garantie ───

`c1f4a90b7d33` accorde `SELECT, INSERT, UPDATE, DELETE ON ALL TABLES`. `scripts/bootstrap_roles.sql`
fait le même `GRANT`, puis **révoque `UPDATE, DELETE` sur `audit_events` en dernier**, et son
commentaire dit précisément pourquoi :

    « Running it after the migrations therefore hands UPDATE and DELETE back on `audit_events`
      and quietly destroys the one property that makes an audit log worth keeping […] No error,
      no failing test, nothing to notice. »

La migration n'a pas repris cette reprise. Le piège que le script décrivait s'est refermé par
l'autre bout : `ghostcal_app` a récupéré le droit d'effacer l'entrée qui dit ce qu'il a fait.

Deux tests l'ont attrapé — `test_the_application_role_cannot_delete_history` et son jumeau — et ils
méritent d'être nommés ici, parce qu'ils sont la seule chose qui séparait cette régression de la
production. `docs/base-de-donnees-locale.md` les rangeait parmi les faux positifs de locale ; ils
n'en sont pas. Sur cette base, `lc_messages` vaut déjà `C`, et ils échouent sur
`DID NOT RAISE ProgrammingError` : le refus n'a pas lieu du tout.

La révocation est donc reprise ici, **après** le `GRANT` de la migration précédente, exactement
comme le script la place après le sien.

─── Ce que cette migration ne prouve toujours PAS ───

Le propriétaire du schéma est `postgres`, **superutilisateur**. Un superutilisateur contourne la
RLS, `FORCE` ou non. Les trente-cinq fonctions `SECURITY DEFINER` de ce schéma tournent donc sans
politique, et **aucun de leurs chemins n'est mesuré ici** — `tests/integration/test_retention.py`
le dit déjà en sautant quatre tests pour ce motif exact, et `GHOSTCAL_TESTS_REQUIRE_PLAIN_OWNER`
existe pour ça.

Vérifié le 2026-09-26 sur une base montée exprès avec un propriétaire ordinaire : sept fonctions
`SECURITY DEFINER` joignent `users` (`busy_link_by_token`, `due_booking_reminders`,
`due_task_reminders`, `public_calendar_by_token`, `reminder_calendar_events`, `rotate_org_key`,
`upsert_oidc_identity`) et rendent zéro ligne dès que le propriétaire n'est plus superutilisateur.
Une jointure interne qui perd ses lignes ne lève rien : les rappels cesseraient d'être envoyés, les
liens publics rendraient 404, et rien ne le dirait.

Ce n'est pas corrigé ici, et ce n'est pas mesurable ici. C'est à faire avant de basculer un
déploiement dont le schéma n'appartient pas à un superutilisateur.

Revision ID: d9a4c72e15b8
Revises: c1f4a90b7d33
"""

from __future__ import annotations

from alembic import op

revision = "d9a4c72e15b8"
down_revision = "c1f4a90b7d33"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── La connexion par adresse ────────────────────────────────────────────────────
    #
    # `lower(email)` des deux côtés : `get_by_email` compare déjà en minuscules, et une
    # politique qui comparerait autrement laisserait passer la lecture pour une casse et
    # pas pour l'autre — c'est-à-dire par intermittence, ce qui est pire que pas du tout.
    op.execute(
        """
        CREATE POLICY users_email_lookup ON users
            FOR SELECT
            USING (
                lower(email) = NULLIF(current_setting('app.login_email', true), '')
            )
        """
    )

    # ── Le SSO déclare l'adresse qu'il cherche, et l'utilisateur qu'il crée ────────
    #
    # `upsert_oidc_identity` fait les deux choses que `users` interdit désormais sans
    # déclaration : chercher un compte **par adresse**, et en insérer un.
    #
    # Son propre commentaire porte déjà le raisonnement, appliqué à l'organisation — « the row
    # that defines the tenant is the row being inserted », et « SECURITY DEFINER alone does not
    # get through ». Il manquait seulement de valoir aussi pour l'utilisateur, ce que
    # `c1f4a90b7d33` vient de faire pour `provision_account`. C'est le même geste, ici.
    #
    # Mesuré sur une base à propriétaire ordinaire — la seule qui puisse en juger, voir
    # `docs/base-de-donnees-locale.md` : sans ceci, les quatre tests d'`test_oidc.py` tombent,
    # et c'était le dernier écart imputable à ce chantier sur cette base. Sur une base dont le
    # propriétaire est superutilisateur, ils passent dans les deux cas — ce qui est exactement
    # la raison pour laquelle ce correctif ne pouvait pas être trouvé là.
    #
    # Les deux GUC sont transaction-locaux (`true`) et restaurés, comme celui de
    # l'organisation deux instructions plus bas.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION upsert_oidc_identity(
            p_provider text, p_issuer text, p_subject text, p_email text, p_name text,
            p_org_name text, p_org_slug text, p_email_verified boolean
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        AS $fn$
        DECLARE
            v_user_id uuid;
            v_org_id uuid;
            v_verified timestamptz;
            v_prev_org text;
            v_prev_user text;
            v_prev_email text;
        BEGIN
            -- Returning user: the identity is already linked, so none of the email reasoning
            -- applies — the binding was established on a previous login.
            SELECT user_id INTO v_user_id FROM identities
                WHERE provider = p_provider AND issuer = p_issuer AND subject = p_subject;
            IF v_user_id IS NOT NULL THEN
                RETURN v_user_id;
            END IF;

            -- First login for this subject. Refuse outright unless the IdP vouched for the
            -- address: everything below treats the email as proof of who the caller is.
            IF p_email_verified IS NOT TRUE THEN
                RAISE EXCEPTION 'oidc email not verified by the provider'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            -- `users_email_lookup` ouvre la ligne qui porte l'adresse déclarée, et elle seule.
            -- Sans cette déclaration la recherche ne rend rien, et un compte local existant
            -- passe pour absent : le SSO en créerait un second sur la même adresse, ou
            -- adopterait ce que le contrôle ci-dessous existe pour refuser.
            v_prev_email := current_setting('app.login_email', true);
            PERFORM set_config('app.login_email', lower(p_email), true);

            SELECT id, email_verified_at INTO v_user_id, v_verified
                FROM users WHERE email = p_email;

            PERFORM set_config('app.login_email', coalesce(v_prev_email, ''), true);

            IF v_user_id IS NOT NULL AND v_verified IS NULL THEN
                -- An account exists on this address but never proved ownership of it. Adopting
                -- it would hand the SSO user whatever the squatter set up, including the org key.
                RAISE EXCEPTION 'an unverified local account already holds this email'
                    USING ERRCODE = 'insufficient_privilege';
            END IF;

            IF v_user_id IS NULL THEN
                -- L'identifiant est engendré ici plutôt que par le défaut de colonne, pour la
                -- même raison que l'organisation plus bas : `users_insert` le contrôle, et
                -- `RETURNING` exige en plus que la ligne soit lisible sous `users_select`.
                v_user_id := gen_random_uuid();
                v_prev_user := current_setting('app.current_user_id', true);
                PERFORM set_config('app.current_user_id', v_user_id::text, true);

                INSERT INTO users (id, email, name, timezone, email_verified_at)
                    VALUES (v_user_id, p_email, p_name, 'UTC', now());

                -- The id is generated here rather than by the column default, because the
                -- tenant_isolation policy on `organizations` is checked against it and there is
                -- otherwise nothing to point `app.current_org_id` at: the row that defines the
                -- tenant is the row being inserted. FORCE ROW LEVEL SECURITY means even the
                -- table owner is subject to that check, so SECURITY DEFINER alone does not get
                -- through.
                v_org_id := gen_random_uuid();
                v_prev_org := current_setting('app.current_org_id', true);
                PERFORM set_config('app.current_org_id', v_org_id::text, true);

                INSERT INTO organizations (id, name, slug)
                    VALUES (v_org_id, p_org_name, p_org_slug);
                INSERT INTO memberships (organization_id, user_id, role)
                    VALUES (v_org_id, v_user_id, 'owner');

                -- Restored so a caller doing more work in this transaction is not silently left
                -- inside a tenant, or as a user, it never selected. `true` keeps every call
                -- transaction-local.
                PERFORM set_config('app.current_org_id', coalesce(v_prev_org, ''), true);
                PERFORM set_config('app.current_user_id', coalesce(v_prev_user, ''), true);
            END IF;

            INSERT INTO identities (user_id, provider, issuer, subject)
                VALUES (v_user_id, p_provider, p_issuer, p_subject)
                ON CONFLICT (provider, issuer, subject) DO NOTHING;
            RETURN v_user_id;
        END;
        $fn$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION upsert_oidc_identity"
        "(text, text, text, text, text, text, text, boolean) FROM PUBLIC"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') "
        "THEN GRANT EXECUTE ON FUNCTION upsert_oidc_identity"
        "(text, text, text, text, text, text, text, boolean) TO ghostcal_app; END IF; END $$;"
    )

    # ── `audit_events` redevient inaltérable ────────────────────────────────────────
    #
    # `IF EXISTS` sur le rôle, comme la migration précédente : une base de développement
    # peut ne pas l'avoir, et échouer ici empêcherait toute la suite de s'appliquer.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ghostcal_app') THEN
            REVOKE UPDATE, DELETE ON audit_events FROM ghostcal_app;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_email_lookup ON users")
    # Ni le `GRANT` sur `audit_events`, ni l'ancienne version d'`upsert_oidc_identity` ne sont
    # rétablis. Les deux réarmeraient exactement ce que cette migration corrige — un journal
    # d'audit effaçable, et un SSO qui ne voit pas les comptes existants — et un `downgrade`
    # sert à défaire un correctif, pas à réintroduire un défaut.
    #
    # `upsert_oidc_identity` reste donc dans sa forme corrigée. Elle est compatible avec le
    # schéma d'avant : les GUC qu'elle pose sont transaction-locaux et restaurés, et sans
    # politique sur `users` ils ne changent rien à ce qu'elle voit.
