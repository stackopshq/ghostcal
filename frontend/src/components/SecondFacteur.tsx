"use client";

// Le second facteur, côté réglages.
//
// Les cinq routes existaient — écrites, testées, migrées, déployées — et pas une ligne de
// cette interface ne les appelait. Un compte pouvait donc avoir un second facteur si on
// l'activait à la main par l'API, et dans ce cas il ne pouvait plus se connecter au web du
// tout, faute d'un champ pour le code.

import { useCallback, useEffect, useState } from "react";
import { Champ, inputClass, primaryButtonClass } from "@/components/AuthCard";
import { ApiError } from "@/lib/api";
import {
  activerLeSecondFacteur,
  demarrerLeSecondFacteur,
  desactiverLeSecondFacteur,
  type EtatDuSecondFacteur,
  lireLeSecondFacteur,
  refaireLesCodesDeRecuperation,
} from "@/lib/auth";
import { useT } from "@/lib/i18n";
import {
  etapeDuSecondFacteur,
  resteDeCodesInquietant,
} from "@/lib/secondFacteurEtat";

const boutonDiscret =
  "rounded-pill border border-border-strong px-4 py-2 text-sm font-medium text-foreground transition hover:border-accent hover:text-accent disabled:opacity-60";

export default function SecondFacteur() {
  const t = useT();
  const [etat, setEtat] = useState<EtatDuSecondFacteur | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [occupe, setOccupe] = useState(false);

  // L'enrôlement en cours : le secret rendu par `/mfa/setup`, puis le code qui l'active.
  const [enrolement, setEnrolement] = useState<{
    secret: string;
    otpauth_uri: string;
  } | null>(null);
  const [motDePasse, setMotDePasse] = useState("");
  const [code, setCode] = useState("");
  // Rendus UNE SEULE FOIS par le serveur : seules leurs empreintes sont gardées.
  const [codesDeRecuperation, setCodesDeRecuperation] = useState<
    string[] | null
  >(null);

  // `lire` RETOURNE l'état au lieu de le poser : une fonction sans effet de bord se rappelle
  // depuis un effet sans déclencher la cascade de rendus que le linteur refuse, et les autres
  // appelants restent libres de choisir quand poser le résultat.
  const lire = useCallback(async (): Promise<EtatDuSecondFacteur> => {
    try {
      return await lireLeSecondFacteur();
    } catch {
      // Un serveur trop ancien pour connaître la route est traité comme « pas de second
      // facteur » : afficher un incident pour une fonction que personne n'a demandée serait
      // du bruit sur une page de réglages.
      return { enabled: false, pending: false, recovery_codes_remaining: 0 };
    }
  }, []);

  useEffect(() => {
    lire().then(setEtat);
  }, [lire]);

  const recharger = useCallback(async () => setEtat(await lire()), [lire]);

  // Une seule traduction des échecs, pour les quatre actions : elles partagent les mêmes.
  function direLEchec(err: unknown) {
    if (!(err instanceof ApiError)) return setErreur(t("common.errGeneric"));
    if (err.status === 401) return setErreur(t("mfa.errRefused"));
    if (err.status === 409) return setErreur(t("mfa.errConflict"));
    if (err.status === 429) return setErreur(t("mfa.errLocked"));
    setErreur(t("common.errGeneric"));
  }

  async function agir(quoi: () => Promise<void>) {
    setErreur(null);
    setOccupe(true);
    try {
      await quoi();
    } catch (err) {
      direLEchec(err);
    } finally {
      setOccupe(false);
    }
  }

  function oublierLaSaisie() {
    setMotDePasse("");
    setCode("");
  }

  const etape = etapeDuSecondFacteur(
    etat,
    enrolement !== null,
    codesDeRecuperation !== null,
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-foreground">
          {t("mfa.title")}
        </h2>
        <p className="mt-1 text-sm text-muted">{t("mfa.sub")}</p>
      </div>

      {etape === "chargement" && (
        <p className="text-sm text-muted">{t("common.loading")}</p>
      )}

      {/* ── Les codes de récupération, rendus une seule fois ──
          Affichés AVANT tout le reste dès qu'ils existent : c'est le seul instant où ils
          sont lisibles, et une page qui les enterre sous un formulaire les fait fermer sans
          être notés. */}
      {etape === "codes-a-noter" && codesDeRecuperation && (
        <div className="space-y-3">
          <p className="rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-sm text-foreground">
            {t("mfa.codesWarn")}
          </p>
          <ul className="grid grid-cols-2 gap-2 rounded-lg bg-surface-2 p-3 font-mono text-sm text-foreground">
            {codesDeRecuperation.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <button
            type="button"
            className={primaryButtonClass}
            onClick={() => {
              setCodesDeRecuperation(null);
              setEnrolement(null);
              oublierLaSaisie();
              void recharger();
            }}
          >
            {t("mfa.codesNoted")}
          </button>
        </div>
      )}

      {/* ── Désactivé : demander le mot de passe pour commencer ── */}
      {etape === "inactif" && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void agir(async () => {
              setEnrolement(await demarrerLeSecondFacteur(motDePasse));
              setMotDePasse("");
            });
          }}
        >
          {/* Le mot de passe est redemandé alors que la session est ouverte : l'opération
              remet le secret à zéro, et une session laissée sur un poste partagé ne doit pas
              suffire à déplacer le second facteur vers un autre téléphone. */}
          <Champ label={t("mfa.confirmPassword")}>
            <input
              required
              type="password"
              autoComplete="current-password"
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              className={inputClass}
            />
          </Champ>
          <button
            type="submit"
            disabled={occupe}
            className={primaryButtonClass}
          >
            {t("mfa.enable")}
          </button>
        </form>
      )}

      {/* ── Enrôlement en cours : le secret, puis un premier code ── */}
      {etape === "enrolement" && enrolement && (
        <div className="space-y-3">
          <p className="text-sm text-muted">{t("mfa.scanHint")}</p>
          <div className="rounded-lg bg-surface-2 p-3">
            <code className="break-all font-mono text-sm text-foreground">
              {enrolement.secret}
            </code>
          </div>
          {/* Un lien `otpauth://`, que le téléphone ouvre directement dans son application
              d'authentification si l'on consulte cette page depuis l'appareil. */}
          <p className="text-sm">
            <a
              href={enrolement.otpauth_uri}
              className="text-accent underline underline-offset-2"
            >
              {t("mfa.openInApp")}
            </a>
          </p>
          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void agir(async () => {
                const { recovery_codes } = await activerLeSecondFacteur(code);
                setCodesDeRecuperation(recovery_codes);
                setCode("");
              });
            }}
          >
            <Champ label={t("mfa.firstCode")}>
              <input
                required
                autoFocus
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className={inputClass}
              />
            </Champ>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={occupe}
                className={primaryButtonClass}
              >
                {t("mfa.activate")}
              </button>
              <button
                type="button"
                className={boutonDiscret}
                onClick={() => {
                  setEnrolement(null);
                  oublierLaSaisie();
                  setErreur(null);
                }}
              >
                {t("common.cancel")}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Actif : l'état, et les deux actions qui restent ── */}
      {etape === "actif" && etat && (
        <div className="space-y-4">
          <p className="text-sm text-foreground">{t("mfa.enabled")}</p>
          <p
            className={
              resteDeCodesInquietant(etat.recovery_codes_remaining)
                ? "text-sm text-warn"
                : "text-sm text-muted"
            }
          >
            {t("mfa.codesLeft", { n: etat.recovery_codes_remaining })}
          </p>

          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              void agir(async () => {
                const { recovery_codes } = await refaireLesCodesDeRecuperation(
                  motDePasse,
                  code,
                );
                setCodesDeRecuperation(recovery_codes);
                oublierLaSaisie();
              });
            }}
          >
            <Champ label={t("mfa.confirmPassword")}>
              <input
                required
                type="password"
                autoComplete="current-password"
                value={motDePasse}
                onChange={(e) => setMotDePasse(e.target.value)}
                className={inputClass}
              />
            </Champ>
            <Champ label={t("login.codeOrRecovery")}>
              <input
                required
                autoComplete="one-time-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className={inputClass}
              />
            </Champ>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" disabled={occupe} className={boutonDiscret}>
                {t("mfa.regenerate")}
              </button>
              <button
                type="button"
                disabled={occupe}
                className={boutonDiscret}
                onClick={() => {
                  if (!confirm(t("mfa.confirmDisable"))) return;
                  void agir(async () => {
                    await desactiverLeSecondFacteur(motDePasse, code);
                    oublierLaSaisie();
                    await recharger();
                  });
                }}
              >
                {t("mfa.disable")}
              </button>
            </div>
          </form>
        </div>
      )}

      {erreur && <p className="text-sm text-red-400">{erreur}</p>}
    </div>
  );
}
