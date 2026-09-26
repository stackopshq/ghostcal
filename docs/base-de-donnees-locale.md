# Monter une base locale pour les tests d'intégration

Les 162 tests d'intégration **se sautent** quand aucune base n'est joignable. C'est voulu :
quelqu'un sans infrastructure obtient quand même une passe utile. Mais tant qu'ils sautent,
ils ne mesurent rien — et tout ce qui touche à la sécurité au niveau ligne ne se vérifie
que là.

Ce document existe parce que **trois personnes ont buté sur le même montage**, et pour des
raisons dont aucune n'était le sujet qu'elles traitaient.

## Sans conteneur

Ni podman ni docker ne sont nécessaires. PostgreSQL suffit :

    brew install postgresql@17
    export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

## Les trois pièges, dans l'ordre où ils mordent

### 1. Le chemin du socket est limité à 103 octets

Un répertoire de travail profond fait échouer le démarrage sur :

    n'a pas pu créer la socket de domaine Unix dans le répertoire « … »

Le message ne nomme pas la limite. Posez le socket ailleurs, avec `-k` :

    initdb -D "$PGDATA" -U postgres --auth=trust
    mkdir -p /tmp/gcpg
    pg_ctl -D "$PGDATA" -o "-p 55433 -k /tmp/gcpg" -l "$PGDATA/../pg.log" start

### 2. La locale des messages fait échouer trois tests, et ce n'est pas le code

`test_the_application_role_cannot_delete_history`, son jumeau `…_rewrite_history` et
`test_a_runaway_statement_is_cancelled_…` cherchent `permission denied` dans le message
d'erreur. Sur une machine en français, PostgreSQL dit « droit refusé ».

Le refus a bien lieu — c'est le **texte** qui diffère. Trois échecs qui n'en sont pas, et
qui ressemblent à s'y méprendre à un défaut de droits :

    psql -c "ALTER SYSTEM SET lc_messages = 'C';"   # hors transaction
    pg_ctl … restart

### 3. `greenlet` est élagué sur Apple Silicon

Le marqueur de plateforme de SQLAlchemy nomme `aarch64` mais pas `arm64`. Sans lui, les
tests d'intégration passent de « sautés » à **« en erreur »**, et huit autres échouent
vraiment : la ligne de base paraît franchement rouge. Il est déclaré explicitement dans
`pyproject.toml` depuis le 2026-09-26 ; si vous partez d'un commit antérieur :

    uv pip install greenlet

## Le rôle applicatif

Les politiques ne s'appliquent qu'à un rôle qui ne les contourne pas. C'est ce que fait
`scripts/init/01-app-role.sh` dans le conteneur ; à la main :

    createdb -p 55433 -U postgres ghostcal
    psql -p 55433 -U postgres -d ghostcal <<'SQL'
    CREATE ROLE ghostcal_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
        PASSWORD 'motdepasse';
    GRANT USAGE ON SCHEMA public TO ghostcal_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ghostcal_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ghostcal_app;
    SQL

`NOSUPERUSER NOBYPASSRLS` n'est pas décoratif : **un superutilisateur contourne toute
politique, même sous `FORCE ROW LEVEL SECURITY`.** Se connecter en `postgres` ferait passer
au vert des tests d'isolation qui ne prouveraient plus rien.

## L'environnement

Deux URL, et elles ne sont pas interchangeables : l'application se connecte en rôle
restreint, Alembic en rôle privilégié.

    export GHOSTCAL_ENVIRONMENT=development
    export GHOSTCAL_DATABASE_URL="postgresql+asyncpg://ghostcal_app:motdepasse@127.0.0.1:55433/ghostcal"
    export GHOSTCAL_DATABASE_ADMIN_URL="postgresql+asyncpg://postgres@127.0.0.1:55433/ghostcal"
    export GHOSTCAL_REDIS_URL="redis://127.0.0.1:6379/0"
    export GHOSTCAL_SECRET_KEY="… au moins 32 caractères …"
    export GHOSTCAL_TOKEN_ENCRYPTION_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    export GHOSTCAL_FRONTEND_BASE_URL="http://localhost:3000"
    export GHOSTCAL_EMAIL_FROM="test@example.org"
    export GHOSTCAL_TESTS_REQUIRE_DB=1

`GHOSTCAL_TESTS_REQUIRE_DB=1` transforme le saut en échec. **Posez-la** : sans elle, une
base mal configurée rend une passe verte qui n'a rien mesuré. C'est ce que fait la CI.

`redis` n'a pas besoin de tourner pour les tests d'intégration ; l'URL doit seulement être
valide.

## Enfin

    uv run alembic upgrade head
    uv run pytest tests/integration -q

Attendu sur `main` au 2026-09-26 : **162 passés, 4 sautés**.

Si vous obtenez autre chose, relisez les trois pièges avant de conclure à une régression.
