"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type Locale = "en" | "fr" | "es";

export const LOCALES: { code: Locale; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "fr", label: "FR" },
  { code: "es", label: "ES" },
];

const STORAGE_KEY = "gc_locale";

type Dict = Record<string, string>;

const en: Dict = {
  // common
  "common.signIn": "Sign in",
  "common.email": "Email",
  "common.password": "Password",
  "common.errGeneric": "Something went wrong. Please try again.",
  "common.loading": "Loading…",
  // landing
  "landing.tagline":
    "Fast, correct scheduling. Pick a time in seconds — the tool gets out of your way.",
  "landing.getStarted": "Get started",
  "landing.tryDemo": "or try the demo booking page →",
  // login
  "login.title": "Sign in",
  "login.submitting": "Signing in…",
  "login.newHere": "New to GhostCal?",
  "login.create": "Create an account",
  "login.errVerify": "Please verify your email before signing in.",
  "login.errInvalid": "Invalid email or password.",
  // register
  "register.title": "Create your account",
  "register.haveAccount": "Already have an account?",
  "register.yourName": "Your name",
  "register.passwordPh": "Password (min 8 characters)",
  "register.submit": "Create account",
  "register.submitting": "Creating…",
  "register.errTaken": "That email is already registered.",
  "register.errGeneric": "Could not create the account. Check your details and try again.",
  "register.checkInbox": "Check your inbox",
  "register.checkInboxSub": "We sent a verification link to {email}. Confirm it to activate your account.",
  "register.expires": "The link expires in 24 hours. You can close this tab.",
  "register.backToSignIn": "Back to sign in",
  // verify
  "verify.verifying": "Verifying your email…",
  "verify.oneMoment": "One moment.",
  "verify.okTitle": "Email verified ✓",
  "verify.okSub": "Your account is active.",
  "verify.okBody": "You can now sign in to GhostCal.",
  "verify.failTitle": "Verification failed",
  "verify.failSub": "This link is invalid or has expired.",
  "verify.failBody": "Request a fresh verification link by signing up again.",
  "verify.createNew": "Create a new account",
};

const fr: Dict = {
  "common.signIn": "Se connecter",
  "common.email": "E-mail",
  "common.password": "Mot de passe",
  "common.errGeneric": "Une erreur est survenue. Réessayez.",
  "common.loading": "Chargement…",
  "landing.tagline":
    "Une planification rapide et fiable. Choisissez un créneau en quelques secondes — l'outil s'efface.",
  "landing.getStarted": "Commencer",
  "landing.tryDemo": "ou essayez la page de réservation de démo →",
  "login.title": "Se connecter",
  "login.submitting": "Connexion…",
  "login.newHere": "Nouveau sur GhostCal ?",
  "login.create": "Créer un compte",
  "login.errVerify": "Veuillez vérifier votre e-mail avant de vous connecter.",
  "login.errInvalid": "E-mail ou mot de passe invalide.",
  "register.title": "Créer votre compte",
  "register.haveAccount": "Vous avez déjà un compte ?",
  "register.yourName": "Votre nom",
  "register.passwordPh": "Mot de passe (8 caractères min.)",
  "register.submit": "Créer le compte",
  "register.submitting": "Création…",
  "register.errTaken": "Cet e-mail est déjà enregistré.",
  "register.errGeneric": "Impossible de créer le compte. Vérifiez vos informations et réessayez.",
  "register.checkInbox": "Vérifiez votre boîte mail",
  "register.checkInboxSub":
    "Nous avons envoyé un lien de vérification à {email}. Confirmez-le pour activer votre compte.",
  "register.expires": "Le lien expire dans 24 heures. Vous pouvez fermer cet onglet.",
  "register.backToSignIn": "Retour à la connexion",
  "verify.verifying": "Vérification de votre e-mail…",
  "verify.oneMoment": "Un instant.",
  "verify.okTitle": "E-mail vérifié ✓",
  "verify.okSub": "Votre compte est actif.",
  "verify.okBody": "Vous pouvez maintenant vous connecter à GhostCal.",
  "verify.failTitle": "Échec de la vérification",
  "verify.failSub": "Ce lien est invalide ou a expiré.",
  "verify.failBody": "Demandez un nouveau lien en vous inscrivant à nouveau.",
  "verify.createNew": "Créer un nouveau compte",
};

const es: Dict = {
  "common.signIn": "Iniciar sesión",
  "common.email": "Correo electrónico",
  "common.password": "Contraseña",
  "common.errGeneric": "Algo salió mal. Inténtalo de nuevo.",
  "common.loading": "Cargando…",
  "landing.tagline":
    "Programación rápida y precisa. Elige una hora en segundos: la herramienta no te estorba.",
  "landing.getStarted": "Empezar",
  "landing.tryDemo": "o prueba la página de reserva de demostración →",
  "login.title": "Iniciar sesión",
  "login.submitting": "Iniciando sesión…",
  "login.newHere": "¿Nuevo en GhostCal?",
  "login.create": "Crear una cuenta",
  "login.errVerify": "Verifica tu correo antes de iniciar sesión.",
  "login.errInvalid": "Correo o contraseña no válidos.",
  "register.title": "Crea tu cuenta",
  "register.haveAccount": "¿Ya tienes una cuenta?",
  "register.yourName": "Tu nombre",
  "register.passwordPh": "Contraseña (mín. 8 caracteres)",
  "register.submit": "Crear cuenta",
  "register.submitting": "Creando…",
  "register.errTaken": "Ese correo ya está registrado.",
  "register.errGeneric": "No se pudo crear la cuenta. Revisa tus datos e inténtalo de nuevo.",
  "register.checkInbox": "Revisa tu bandeja de entrada",
  "register.checkInboxSub":
    "Enviamos un enlace de verificación a {email}. Confírmalo para activar tu cuenta.",
  "register.expires": "El enlace caduca en 24 horas. Puedes cerrar esta pestaña.",
  "register.backToSignIn": "Volver a iniciar sesión",
  "verify.verifying": "Verificando tu correo…",
  "verify.oneMoment": "Un momento.",
  "verify.okTitle": "Correo verificado ✓",
  "verify.okSub": "Tu cuenta está activa.",
  "verify.okBody": "Ya puedes iniciar sesión en GhostCal.",
  "verify.failTitle": "Verificación fallida",
  "verify.failSub": "Este enlace no es válido o ha caducado.",
  "verify.failBody": "Solicita un nuevo enlace de verificación registrándote de nuevo.",
  "verify.createNew": "Crear una cuenta nueva",
};

const messages: Record<Locale, Dict> = { en, fr, es };

function detect(): Locale {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored && messages[stored]) return stored;
  const nav = (navigator.language || "en").slice(0, 2) as Locale;
  return messages[nav] ? nav : "en";
}

type Ctx = {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
};

const I18nContext = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLoc] = useState<Locale>("en");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoc(detect());
  }, []);

  function setLocale(l: Locale) {
    localStorage.setItem(STORAGE_KEY, l);
    setLoc(l);
  }

  function t(key: string, params?: Record<string, string | number>): string {
    let s = messages[locale][key] ?? en[key] ?? key;
    if (params) {
      for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, String(v));
    }
    return s;
  }

  return <I18nContext.Provider value={{ locale, setLocale, t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): Ctx {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

export function useT() {
  return useI18n().t;
}
