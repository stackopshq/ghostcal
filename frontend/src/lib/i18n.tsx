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
  // booking
  "booking.selectTime": "Select a time",
  "booking.timezone": "Time zone",
  "booking.loading": "Loading availability…",
  "booking.noTimes": "No times available in the next two weeks.",
  "booking.yourName": "Your name",
  "booking.yourEmail": "Your email",
  "booking.guests": "Add guests (emails, comma-separated)",
  "booking.confirm": "Confirm booking",
  "booking.confirming": "Confirming…",
  "booking.errTaken": "That slot was just taken. Pick another time.",
  "booking.errGeneric": "Could not confirm the booking. Please try again.",
  "booking.booked": "You're booked",
  "booking.with": "with {host}",
  "booking.emailFollow": "A confirmation will follow by email.",
  "booking.choose": "Choose…",
  // manage
  "manage.linkInvalid": "Link not valid",
  "manage.linkInvalidSub": "This management link is invalid or has expired.",
  "manage.notActive": "This booking is no longer active.",
  "manage.cancelled": "Your meeting has been cancelled.",
  "manage.rescheduledTo": "Rescheduled to {when}. A new confirmation is on its way.",
  "manage.reschedule": "Reschedule",
  "manage.cancelMeeting": "Cancel meeting",
  "manage.pickNew": "Pick a new time",
  "manage.confirmNew": "Confirm new time",
  "manage.back": "Back",
  "manage.errLoadTimes": "Could not load available times.",
  "manage.errCancel": "Could not cancel. Please try again.",
  "manage.errReschedule": "That time is no longer available. Pick another.",
  // poll
  "poll.asking": "{owner} is asking",
  "poll.minTimes": "{n} min · times in {tz}",
  "poll.confirmedTime": "Confirmed time",
  "poll.thanks": "Thanks — your vote is in. ✓",
  "poll.closed": "This poll is closed.",
  "poll.notExist": "This poll doesn't exist.",
  "poll.pickOne": "Pick at least one time.",
  "poll.errVote": "Could not record your vote.",
  "poll.submit": "Submit vote",
  // invitation
  "inv.notFound": "Invitation not found",
  "inv.expired": "This invitation is invalid or has expired.",
  "inv.invitedToJoin": "You've been invited to join",
  "inv.asRole": "as {role} · {email}",
  "inv.errAccept": "Could not accept the invitation. Make sure you're signed in.",
  "inv.joining": "Joining…",
  "inv.accept": "Accept invitation",
  "inv.signinPrompt": "Sign in or create an account with {email}, then reopen this link to join.",
  "inv.signUp": "Sign up",
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
  "booking.selectTime": "Choisir un créneau",
  "booking.timezone": "Fuseau horaire",
  "booking.loading": "Chargement des disponibilités…",
  "booking.noTimes": "Aucun créneau disponible dans les deux prochaines semaines.",
  "booking.yourName": "Votre nom",
  "booking.yourEmail": "Votre e-mail",
  "booking.guests": "Ajouter des invités (e-mails, séparés par des virgules)",
  "booking.confirm": "Confirmer la réservation",
  "booking.confirming": "Confirmation…",
  "booking.errTaken": "Ce créneau vient d'être pris. Choisissez-en un autre.",
  "booking.errGeneric": "Impossible de confirmer la réservation. Réessayez.",
  "booking.booked": "C'est réservé",
  "booking.with": "avec {host}",
  "booking.emailFollow": "Une confirmation suivra par e-mail.",
  "booking.choose": "Choisir…",
  "manage.linkInvalid": "Lien non valide",
  "manage.linkInvalidSub": "Ce lien de gestion est invalide ou a expiré.",
  "manage.notActive": "Cette réservation n'est plus active.",
  "manage.cancelled": "Votre rendez-vous a été annulé.",
  "manage.rescheduledTo": "Replanifié au {when}. Une nouvelle confirmation arrive.",
  "manage.reschedule": "Replanifier",
  "manage.cancelMeeting": "Annuler le rendez-vous",
  "manage.pickNew": "Choisir un nouveau créneau",
  "manage.confirmNew": "Confirmer le nouveau créneau",
  "manage.back": "Retour",
  "manage.errLoadTimes": "Impossible de charger les créneaux disponibles.",
  "manage.errCancel": "Impossible d'annuler. Réessayez.",
  "manage.errReschedule": "Ce créneau n'est plus disponible. Choisissez-en un autre.",
  "poll.asking": "{owner} demande",
  "poll.minTimes": "{n} min · horaires en {tz}",
  "poll.confirmedTime": "Créneau confirmé",
  "poll.thanks": "Merci — votre vote est enregistré. ✓",
  "poll.closed": "Ce sondage est clôturé.",
  "poll.notExist": "Ce sondage n'existe pas.",
  "poll.pickOne": "Choisissez au moins un créneau.",
  "poll.errVote": "Impossible d'enregistrer votre vote.",
  "poll.submit": "Envoyer le vote",
  "inv.notFound": "Invitation introuvable",
  "inv.expired": "Cette invitation est invalide ou a expiré.",
  "inv.invitedToJoin": "Vous êtes invité à rejoindre",
  "inv.asRole": "en tant que {role} · {email}",
  "inv.errAccept": "Impossible d'accepter l'invitation. Vérifiez que vous êtes connecté.",
  "inv.joining": "Adhésion…",
  "inv.accept": "Accepter l'invitation",
  "inv.signinPrompt":
    "Connectez-vous ou créez un compte avec {email}, puis rouvrez ce lien pour rejoindre.",
  "inv.signUp": "S'inscrire",
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
  "booking.selectTime": "Elige una hora",
  "booking.timezone": "Zona horaria",
  "booking.loading": "Cargando disponibilidad…",
  "booking.noTimes": "No hay horas disponibles en las próximas dos semanas.",
  "booking.yourName": "Tu nombre",
  "booking.yourEmail": "Tu correo electrónico",
  "booking.guests": "Añadir invitados (correos, separados por comas)",
  "booking.confirm": "Confirmar reserva",
  "booking.confirming": "Confirmando…",
  "booking.errTaken": "Ese hueco se acaba de ocupar. Elige otra hora.",
  "booking.errGeneric": "No se pudo confirmar la reserva. Inténtalo de nuevo.",
  "booking.booked": "Reserva confirmada",
  "booking.with": "con {host}",
  "booking.emailFollow": "Recibirás una confirmación por correo.",
  "booking.choose": "Elegir…",
  "manage.linkInvalid": "Enlace no válido",
  "manage.linkInvalidSub": "Este enlace de gestión no es válido o ha caducado.",
  "manage.notActive": "Esta reserva ya no está activa.",
  "manage.cancelled": "Tu reunión ha sido cancelada.",
  "manage.rescheduledTo": "Reprogramada para {when}. Llegará una nueva confirmación.",
  "manage.reschedule": "Reprogramar",
  "manage.cancelMeeting": "Cancelar reunión",
  "manage.pickNew": "Elige una hora nueva",
  "manage.confirmNew": "Confirmar nueva hora",
  "manage.back": "Atrás",
  "manage.errLoadTimes": "No se pudieron cargar las horas disponibles.",
  "manage.errCancel": "No se pudo cancelar. Inténtalo de nuevo.",
  "manage.errReschedule": "Esa hora ya no está disponible. Elige otra.",
  "poll.asking": "{owner} pregunta",
  "poll.minTimes": "{n} min · horas en {tz}",
  "poll.confirmedTime": "Hora confirmada",
  "poll.thanks": "Gracias — tu voto está registrado. ✓",
  "poll.closed": "Esta encuesta está cerrada.",
  "poll.notExist": "Esta encuesta no existe.",
  "poll.pickOne": "Elige al menos una hora.",
  "poll.errVote": "No se pudo registrar tu voto.",
  "poll.submit": "Enviar voto",
  "inv.notFound": "Invitación no encontrada",
  "inv.expired": "Esta invitación no es válida o ha caducado.",
  "inv.invitedToJoin": "Te han invitado a unirte a",
  "inv.asRole": "como {role} · {email}",
  "inv.errAccept": "No se pudo aceptar la invitación. Asegúrate de haber iniciado sesión.",
  "inv.joining": "Uniéndote…",
  "inv.accept": "Aceptar invitación",
  "inv.signinPrompt":
    "Inicia sesión o crea una cuenta con {email}, luego vuelve a abrir este enlace para unirte.",
  "inv.signUp": "Registrarse",
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
