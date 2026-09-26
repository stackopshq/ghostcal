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
  String get retirerLaPhoto => 'Remove the photo';

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
  String get typesCreesDepuisLeWeb =>
      'They are created from the web: fifteen or so settings that do not sit well under a thumb.';

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
}
