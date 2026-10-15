// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localisations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class LEn extends L {
  LEn([String locale = 'en']) : super(locale);

  @override
  String get ongletAgenda => 'Calendar';

  @override
  String get ongletTaches => 'Tasks';

  @override
  String get ongletReunions => 'Meetings';

  @override
  String get ongletRdv => 'Links';

  @override
  String get ongletReglages => 'Settings';

  @override
  String get verrouillerLeCoffre => 'Lock the vault';

  @override
  String get jourPrecedent => 'Previous day';

  @override
  String get jourSuivant => 'Next day';

  @override
  String get allerAUneDate => 'Go to a date';

  @override
  String get nouvelEvenement => 'New event';

  @override
  String get modifierLEvenement => 'Edit event';

  @override
  String get rienCeJourLa => 'Nothing on this day.';

  @override
  String get journee => 'All day';

  @override
  String get contenuIllisible => 'Unreadable content — key missing';

  @override
  String get sansTitre => 'Untitled';

  @override
  String get sceauIllisible => 'the seal is unreadable';

  @override
  String get phraseScelleeObsolete =>
      'The sealed passphrase no longer opens this vault — it has most likely changed since. Type it to seal it again.';

  @override
  String biometrieDesactivee(String biometrie) {
    return 'Opening with $biometrie has been switched off: the seal stored on this device is no longer readable — usually because a biometric was added or removed. Type your passphrase to restore it.';
  }

  @override
  String magasinIllisible(String raison) {
    return 'The secure store could not be read: $raison.';
  }

  @override
  String biometriePasDemandee(String biometrie) {
    return '$biometrie could not be asked for: the device was not ready to present the request. Nothing has changed — tap the icon in a moment, or type your passphrase.';
  }

  @override
  String get raisonInconnue => 'reason unknown';

  @override
  String get laBiometrie => 'biometrics';

  @override
  String get coffreEnregistre => 'Vault saved on this device';

  @override
  String get agendaChiffre => 'End-to-end encrypted calendar';

  @override
  String get deverrouiller => 'Unlock';

  @override
  String get seConnecter => 'Sign in';

  @override
  String ouvrirAvec(String biometrie) {
    return 'Open with $biometrie';
  }

  @override
  String phraseSceleeSurAppareil(String biometrie) {
    return 'The passphrase is sealed on this device, readable by $biometrie alone. Adding or removing a face or fingerprint cancels this access.';
  }

  @override
  String get afficherLaPhrase => 'Show the passphrase';

  @override
  String get masquerLaPhrase => 'Hide the passphrase';

  @override
  String connecteMaisCoffreFerme(String raison) {
    return 'You are signed in, but the vault stayed closed: $raison';
  }

  @override
  String get phraseNOuvrePasLeCoffre =>
      'this passphrase does not open the vault';

  @override
  String get serveur => 'Server';

  @override
  String get adresseElectronique => 'Email address';

  @override
  String get exempleAdresse => 'you@example.com';

  @override
  String get retenirCetAppareil => 'Remember this device';

  @override
  String get utiliserMonMotDePasse => 'Use my password';

  @override
  String get utiliserMaPhraseDeRecuperation => 'Use my recovery passphrase';

  @override
  String get utiliserUnAutreCompte => 'Use a different account';

  @override
  String get phraseDeRecuperation => 'Recovery passphrase';

  @override
  String get motDePasseMaitre => 'Master password';

  @override
  String get votreMotDePasse => 'Your password';

  @override
  String get ouvrirLeCoffre => 'Open the vault';

  @override
  String get utiliserLaPhrase => 'Use the passphrase';

  @override
  String get equipe => 'Team';

  @override
  String get retirerDeLEquipe => 'Remove from the team';

  @override
  String get perteDAccesOrganisation =>
      'This person will lose access to the organisation\'s calendars.';

  @override
  String get proprietaire => 'Owner';

  @override
  String get contenuNonDechiffre =>
      'This event\'s content could not be decrypted. Saving it would replace a title you were not able to read.';

  @override
  String get finAvantDebut => 'The end is before the start.';

  @override
  String get supprimerCetEvenement => 'Delete this event?';

  @override
  String get disparaitraPourTous => 'It will disappear for every participant.';

  @override
  String get titre => 'Title';

  @override
  String get lieu => 'Location';

  @override
  String get description => 'Description';

  @override
  String get journeeEntiere => 'All day';

  @override
  String get debut => 'Start';

  @override
  String get fin => 'End';

  @override
  String get calendrier => 'Calendar';

  @override
  String get enregistrer => 'Save';

  @override
  String get supprimer => 'Delete';

  @override
  String get annuler => 'Cancel';

  @override
  String get creer => 'Create';

  @override
  String get ceQuiEstChiffre =>
      'The title, location and description are encrypted on this device. The times leave in the clear: without them the server could neither answer \"busy\" to a booking link, nor send a reminder.';

  @override
  String get profil => 'Profile';

  @override
  String get profilEnregistre => 'Profile saved.';

  @override
  String get nonVerifiee => 'unverified';

  @override
  String get changementDAdresseParLeWeb =>
      'Changing it requires a verification, which is done from the web.';

  @override
  String get utiliserLeFuseauDeLAppareil => 'Use this device\'s time zone';

  @override
  String get retirerLaPhoto => 'Remove the photo link';

  @override
  String get photoEffaceeALEnregistrement => 'It will be erased when you save.';

  @override
  String get securite => 'Security';

  @override
  String get clesQuittentLaMemoire =>
      'The keys leave memory; the session stays open.';

  @override
  String get sceauBiometrique => 'Biometric unlock';

  @override
  String sceauPose(String biometrie) {
    return 'Sealed, readable by $biometrie alone.';
  }

  @override
  String get sceauAbsent =>
      'Nothing is sealed. The offer returns at the next unlock.';

  @override
  String get sceauInvalide =>
      'The seal is no longer readable: a biometric was added or removed on this device. Type your passphrase again at the next unlock.';

  @override
  String get sceauIndetermine =>
      'The state of the seal could not be read. This is neither a yes nor a no: the store did not answer.';

  @override
  String get sansBiometrieSurCetAppareil =>
      'No usable biometrics on this device.';

  @override
  String get retirerLeSceau => 'Remove the seal';

  @override
  String get sceauRetire =>
      'The seal has been removed. The passphrase will be asked for again at the next unlock.';

  @override
  String coffreFermePourOrganisation(String role) {
    return '$role · vault closed for this organisation';
  }

  @override
  String get disponibilites => 'Availability';

  @override
  String get aucunHoraire => 'No schedule';

  @override
  String get horairesDepuisLeWeb => 'They are set from the web.';

  @override
  String get seDeconnecter => 'Sign out';

  @override
  String aucunePlage(String fuseau) {
    return 'No hours · $fuseau';
  }

  @override
  String get aVenir => 'Upcoming';

  @override
  String get passees => 'Past';

  @override
  String get aucuneReunionAVenir => 'No upcoming meetings.';

  @override
  String get aucuneReunionPassee => 'No past meetings.';

  @override
  String get annulee => 'Cancelled';

  @override
  String get identiteIllisible => 'Identity unreadable — key missing';

  @override
  String get inviteInconnu => 'Unknown invitee';

  @override
  String fuseauDeLInvite(String fuseau) {
    return 'Invitee\'s time zone: $fuseau';
  }

  @override
  String get reponses => 'ANSWERS';

  @override
  String get annulerCetteReunion => 'Cancel this meeting?';

  @override
  String get invitePrevenuParServeur =>
      'The invitee will be told by the server.';

  @override
  String get annulerLaReunion => 'Cancel the meeting';

  @override
  String get clos => 'closed';

  @override
  String creneauxRetenus(int nombre) {
    String _temp0 = intl.Intl.pluralLogic(
      nombre,
      locale: localeName,
      other: '$nombre slots picked',
      one: '$nombre slot picked',
    );
    return '$_temp0';
  }

  @override
  String get sondages => 'Polls';

  @override
  String get aucunSondage => 'No polls.';

  @override
  String creneauxEtVotes(int creneaux, int votes) {
    return '$creneaux slots · $votes votes';
  }

  @override
  String get retenirCeCreneauQuestion => 'Pick this slot?';

  @override
  String sondageSeFermeEtEvenementCree(String date) {
    return 'The poll closes and the event is created on $date.';
  }

  @override
  String get supprimerLeSondage => 'Delete the poll';

  @override
  String get creneaux => 'Slots';

  @override
  String nombreDeCreneaux(int nombre) {
    String _temp0 = intl.Intl.pluralLogic(
      nombre,
      locale: localeName,
      other: '$nombre slots',
      one: '$nombre slot',
    );
    return '$_temp0';
  }

  @override
  String get creneauRetenu => 'Slot picked';

  @override
  String get retenirCeCreneau => 'Pick this slot';

  @override
  String get supprimerCeSondage => 'Delete this poll?';

  @override
  String get votesPerdus => 'The votes already cast will be lost.';

  @override
  String get masquerLesFaites => 'Hide completed';

  @override
  String get nouvelleTache => 'New task';

  @override
  String get aucuneTache => 'No tasks.';

  @override
  String get rienAFaire => 'Nothing to do.';

  @override
  String get supprimerCetteTache => 'Delete this task?';

  @override
  String get sansEcheance => 'No due date';

  @override
  String get retirerLEcheance => 'Remove the due date';

  @override
  String get rendezVous => 'Booking links';

  @override
  String get aucunTypeDeRendezVous => 'No booking links.';

  @override
  String get typesCreesDepuisLeWeb => 'Create one with the + button.';

  @override
  String get ferme => 'closed';

  @override
  String get copierLeLienDeReservation => 'Copy the booking link';

  @override
  String lienCopie(String lien) {
    return 'Link copied: $lien';
  }

  @override
  String serveurARepondu(int code) {
    return 'The server answered $code.';
  }

  @override
  String get phraseNOuvrePas => 'This passphrase does not open the vault.';

  @override
  String get coffreFermeChiffrementImpossible =>
      'The vault is closed: this content cannot be encrypted.';

  @override
  String get adresseDeServeurInvalide => 'Invalid server address.';

  @override
  String get sessionExpiree => 'The session has expired. Sign in again.';

  @override
  String get roleProprietaire => 'Owner';

  @override
  String get roleAdministrateur => 'Administrator';

  @override
  String get roleMembre => 'Member';

  @override
  String get invitePromptTitre => 'Open the vault';

  @override
  String get invitePromptRefus => 'Use the passphrase';

  @override
  String get verrouillageImmediat => 'Immediately';

  @override
  String get verrouillage1Minute => 'After 1 minute';

  @override
  String get verrouillage5Minutes => 'After 5 minutes';

  @override
  String get verrouillage15Minutes => 'After 15 minutes';

  @override
  String get codeDeVerification => 'Verification code';

  @override
  String get codeDeVerificationAide =>
      'Your account requires a second factor. Enter the code shown by your authenticator app.';

  @override
  String get codeDeVerificationRefuse =>
      'That code was not accepted. The next one may work: they change every thirty seconds.';

  @override
  String codeDeVerificationBloque(String heure) {
    return 'Too many attempts. The server will refuse until $heure.';
  }

  @override
  String get valider => 'Confirm';

  @override
  String get revenir => 'Back';

  @override
  String get erreurServeurInjoignable =>
      'Can\'t reach the server. Check your connection and the server address.';

  @override
  String get erreurServeurLent =>
      'The server isn\'t responding. Try again in a moment.';

  @override
  String get erreurCertificat =>
      'The secure connection to the server failed: its certificate isn\'t valid.';

  @override
  String get erreurAdresseInvalide => 'Invalid server address.';

  @override
  String get erreurSessionExpiree =>
      'Your session has expired. Please sign in again.';

  @override
  String get erreurPhraseIncorrecte =>
      'This passphrase doesn\'t open the vault.';

  @override
  String get erreurIdentifiants => 'Wrong email address or password.';

  @override
  String get erreurTropDEssais =>
      'Too many attempts. Wait a few minutes before trying again.';

  @override
  String get erreurServeur => 'The server ran into a problem. Try again later.';

  @override
  String get erreurInattendue => 'Something went wrong. Please try again.';

  @override
  String get coffreVerrouille =>
      'The vault is locked. Type your passphrase to open it.';

  @override
  String erreurStatut(int code) {
    return 'The server answered $code.';
  }

  @override
  String get retenir => 'Choose';

  @override
  String get retour => 'Back';

  @override
  String get notes => 'NOTES';

  @override
  String get votants => 'Voters';

  @override
  String get compte => 'Account';

  @override
  String get organisation => 'Organization';

  @override
  String get collaboration => 'Collaboration';

  @override
  String get retirer => 'Remove';

  @override
  String get apparence => 'Appearance';

  @override
  String get langue => 'Language';

  @override
  String get langueDeLAppareil => 'Device language';

  @override
  String get langueFrancais => 'Français';

  @override
  String get langueAnglais => 'English';

  @override
  String get theme => 'Theme';

  @override
  String get themeDeLAppareil => 'Same as device';

  @override
  String get themeClair => 'Light';

  @override
  String get themeSombre => 'Dark';

  @override
  String get aujourdHui => 'Today';

  @override
  String faites(int nombre) {
    return 'Done ($nombre)';
  }

  @override
  String get notesDeTache => 'Notes';

  @override
  String get vueJour => 'Day';

  @override
  String get vueSemaine => 'Week';

  @override
  String get vueMois => 'Month';

  @override
  String get vueListe => 'List';

  @override
  String get periodePrecedente => 'Previous';

  @override
  String get periodeSuivante => 'Next';

  @override
  String get rienSurLaPeriode => 'Nothing planned for this period.';

  @override
  String autresEvenements(int nombre) {
    return '+$nombre';
  }

  @override
  String nouvelEvenementA(String heure) {
    return 'New event at $heure';
  }

  @override
  String get lectureSeule =>
      'Shown here; change it where it comes from: a booking, a series or an external calendar.';

  @override
  String get modifierLaTache => 'Edit task';

  @override
  String get envoyerLeLienDeVisio => 'Send video link';

  @override
  String get modifierOuRenvoyerLeLien => 'Change or resend link';

  @override
  String get lienDeVisio => 'Video link (Zoom, Google Meet, Teams…)';

  @override
  String get envoyer => 'Send';

  @override
  String get lienEnvoye => 'Link sent to the invitee.';

  @override
  String get lienDoitCommencerParHttps => 'The link must start with https://';

  @override
  String get lienEnregistreMailEchoue =>
      'Link saved, but the email could not be sent. Try again in a moment.';

  @override
  String get adresseEmail => 'Email address';

  @override
  String get nom => 'Name';

  @override
  String get fuseauHoraire => 'Time zone';

  @override
  String get rechercherUnFuseau => 'Search a city or time zone';

  @override
  String get inviter => 'Invite';

  @override
  String get inviterUnMembre => 'Invite a member';

  @override
  String invitationEnvoyee(String email) {
    return 'Invitation sent to $email';
  }

  @override
  String get invitationLienSecurise =>
      'The server emailed the invitation. So that this person can read the team\'s encrypted data, also send them this secure link: the key it carries never goes through the server.';

  @override
  String get invitationSansCle =>
      'The server emailed the invitation. The vault was closed, so the team key was not attached: a member will share it from the web.';

  @override
  String get copierLeLien => 'Copy link';

  @override
  String get fermer => 'Close';

  @override
  String get nouveauType => 'New event type';

  @override
  String get modifierLeType => 'Edit event type';

  @override
  String get descriptionPublique => 'Description (shown on the booking page)';

  @override
  String get duree => 'Duration';

  @override
  String get preavisMinimum => 'Minimum notice';

  @override
  String get reservableSur => 'Bookable over';

  @override
  String get tamponAvant => 'Buffer before';

  @override
  String get tamponApres => 'Buffer after';

  @override
  String get ouvertALaReservation => 'Open for booking';

  @override
  String get typeDisponibilitesDepuisHoraire =>
      'Offered slots follow your availability (Settings › Availability).';

  @override
  String get lieuTelephone => 'Phone';

  @override
  String get lieuEnPersonne => 'In person';

  @override
  String get lieuAutre => 'Other';

  @override
  String get aucun => 'None';

  @override
  String nJours(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n days',
      one: '1 day',
    );
    return '$_temp0';
  }

  @override
  String nHeures(int n) {
    String _temp0 = intl.Intl.pluralLogic(
      n,
      locale: localeName,
      other: '$n h',
      one: '1 h',
    );
    return '$_temp0';
  }

  @override
  String get supprimerCeType => 'Delete this event type?';

  @override
  String get supprimerCeTypeExplication =>
      'Its booking page will stop existing.';

  @override
  String get typeAvecReservations =>
      'This type already has bookings: close it instead of deleting it.';

  @override
  String get heuresDeBureau => 'Office hours';

  @override
  String get indisponible => 'Unavailable';

  @override
  String get ajouterUnePlage => 'Add a range';

  @override
  String get definirMesDisponibilites => 'Set my availability';

  @override
  String get disponibilitesExplication =>
      'The days and hours people can book a meeting with you.';

  @override
  String get nouveauSondage => 'New poll';

  @override
  String get lienDuSondage => 'Poll link';

  @override
  String get lienDuSondageExplication =>
      'Send this link to the participants: they vote without an account, then you pick the winning slot.';

  @override
  String get creneauxProposes => 'Proposed slots';

  @override
  String get ajouterUnCreneau => 'Add a slot';

  @override
  String get auMoinsDeuxCreneaux => 'Offer at least two slots.';

  @override
  String get saisieRapide => 'Quick entry';

  @override
  String get saisieRapideExemple =>
      'Lunch with Sam tomorrow 12:30pm at the Café';

  @override
  String get photoDeProfil => 'Profile photo';

  @override
  String get choisirUnePhoto => 'Choose a photo';

  @override
  String get retirerLaPhotoTeleversee => 'Remove photo';

  @override
  String get photoTropLourde =>
      'This image is over 2 MB. Choose a lighter one.';

  @override
  String get photoEnregistree => 'Photo saved.';

  @override
  String get photoRetiree => 'Photo removed.';

  @override
  String get questionsAuxInvites => 'Questions for invitees';

  @override
  String get questionsExplication =>
      'Name and email are always asked. Answers are encrypted for you only.';

  @override
  String get ajouterUneQuestion => 'Add a question';

  @override
  String get modifierLaQuestion => 'Edit the question';

  @override
  String get libelleDeLaQuestion => 'Question';

  @override
  String get typeDeReponse => 'Answer type';

  @override
  String get reponseTexte => 'Short text';

  @override
  String get reponseLongue => 'Long text';

  @override
  String get reponseTelephone => 'Phone';

  @override
  String get reponseChoix => 'List of choices';

  @override
  String get reponseCase => 'Checkbox';

  @override
  String get reponseObligatoire => 'Answer required';

  @override
  String get choixUnParLigne => 'Choices, one per line';
}
