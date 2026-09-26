// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localisations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class LFr extends L {
  LFr([String locale = 'fr']) : super(locale);

  @override
  String get ongletAgenda => 'Agenda';

  @override
  String get ongletTaches => 'Tâches';

  @override
  String get ongletReunions => 'Réunions';

  @override
  String get ongletRdv => 'RDV';

  @override
  String get ongletReglages => 'Réglages';

  @override
  String get verrouillerLeCoffre => 'Verrouiller le coffre';

  @override
  String get jourPrecedent => 'Jour précédent';

  @override
  String get jourSuivant => 'Jour suivant';

  @override
  String get allerAUneDate => 'Aller à une date';

  @override
  String get nouvelEvenement => 'Nouvel événement';

  @override
  String get modifierLEvenement => 'Modifier l\'événement';

  @override
  String get rienCeJourLa => 'Rien ce jour-là.';

  @override
  String get journee => 'Journée';

  @override
  String get contenuIllisible => 'Contenu illisible — clé manquante';

  @override
  String get sansTitre => 'Sans titre';

  @override
  String get sceauIllisible => 'le sceau est illisible';

  @override
  String get phraseScelleeObsolete =>
      'La phrase scellée n\'ouvre plus ce coffre — elle a sans doute changé depuis. Tapez-la pour la resceller.';

  @override
  String biometrieDesactivee(String biometrie) {
    return 'L\'ouverture par $biometrie a été désactivée : le sceau posé sur cet appareil n\'est plus lisible — le plus souvent parce qu\'une biométrie y a été ajoutée ou retirée. Tapez votre phrase pour la rétablir.';
  }

  @override
  String magasinIllisible(String raison) {
    return 'Le magasin sécurisé n\'a pas pu être lu : $raison.';
  }

  @override
  String biometriePasDemandee(String biometrie) {
    return '$biometrie n\'a pas pu être demandé : l\'appareil n\'était pas en état de présenter la demande. Rien n\'a changé — touchez l\'icône dans un instant, ou tapez votre phrase.';
  }

  @override
  String get raisonInconnue => 'raison inconnue';

  @override
  String get laBiometrie => 'la biométrie';

  @override
  String get coffreEnregistre => 'Coffre enregistré sur cet appareil';

  @override
  String get agendaChiffre => 'Agenda chiffré de bout en bout';

  @override
  String get deverrouiller => 'Déverrouiller';

  @override
  String get seConnecter => 'Se connecter';

  @override
  String ouvrirAvec(String biometrie) {
    return 'Ouvrir avec $biometrie';
  }

  @override
  String phraseSceleeSurAppareil(String biometrie) {
    return 'La phrase est scellée sur cet appareil, relisible par $biometrie seul. Ajouter ou retirer un visage ou une empreinte annule cet accès.';
  }

  @override
  String get afficherLaPhrase => 'Afficher la phrase';

  @override
  String get masquerLaPhrase => 'Masquer la phrase';

  @override
  String connecteMaisCoffreFerme(String raison) {
    return 'Vous êtes connecté, mais le coffre est resté fermé : $raison';
  }

  @override
  String get phraseNOuvrePasLeCoffre => 'cette phrase n\'ouvre pas le coffre';

  @override
  String get serveur => 'Serveur';

  @override
  String get adresseElectronique => 'Adresse e-mail';

  @override
  String get exempleAdresse => 'vous@exemple.ch';

  @override
  String get retenirCetAppareil => 'Retenir cet appareil';

  @override
  String get utiliserMonMotDePasse => 'Utiliser mon mot de passe';

  @override
  String get utiliserMaPhraseDeRecuperation =>
      'Utiliser ma phrase de récupération';

  @override
  String get utiliserUnAutreCompte => 'Utiliser un autre compte';

  @override
  String get phraseDeRecuperation => 'Phrase de récupération';

  @override
  String get motDePasseMaitre => 'Mot de passe maître';

  @override
  String get votreMotDePasse => 'Votre mot de passe';

  @override
  String get ouvrirLeCoffre => 'Ouvrir le coffre';

  @override
  String get utiliserLaPhrase => 'Utiliser la phrase';

  @override
  String get equipe => 'Équipe';

  @override
  String get retirerDeLEquipe => 'Retirer de l\'équipe';

  @override
  String get perteDAccesOrganisation =>
      'Cette personne perdra l’accès aux calendriers de l’organisation.';

  @override
  String get proprietaire => 'Propriétaire';

  @override
  String get contenuNonDechiffre =>
      'Le contenu de cet événement n\'a pas pu être déchiffré. L\'enregistrer remplacerait un titre que vous n\'avez pas pu lire.';

  @override
  String get finAvantDebut => 'La fin est avant le début.';

  @override
  String get supprimerCetEvenement => 'Supprimer cet événement ?';

  @override
  String get disparaitraPourTous =>
      'Il disparaîtra pour tous les participants.';

  @override
  String get titre => 'Titre';

  @override
  String get lieu => 'Lieu';

  @override
  String get description => 'Description';

  @override
  String get journeeEntiere => 'Journée entière';

  @override
  String get debut => 'Début';

  @override
  String get fin => 'Fin';

  @override
  String get calendrier => 'Calendrier';

  @override
  String get enregistrer => 'Enregistrer';

  @override
  String get supprimer => 'Supprimer';

  @override
  String get annuler => 'Annuler';

  @override
  String get creer => 'Créer';

  @override
  String get ceQuiEstChiffre =>
      'Le titre, le lieu et la description sont chiffrés sur cet appareil. Les heures partent en clair : sans elles, le serveur ne pourrait ni répondre « occupé » à un lien de réservation, ni envoyer de rappel.';

  @override
  String get profil => 'Profil';

  @override
  String get profilEnregistre => 'Profil enregistré.';

  @override
  String get nonVerifiee => 'non vérifiée';

  @override
  String get changementDAdresseParLeWeb =>
      'La changer demande une vérification, qui se fait depuis le web.';

  @override
  String get utiliserLeFuseauDeLAppareil =>
      'Utiliser le fuseau de cet appareil';

  @override
  String get retirerLaPhoto => 'Retirer la photo';

  @override
  String get photoEffaceeALEnregistrement =>
      'Elle sera effacée à l’enregistrement.';

  @override
  String get securite => 'Sécurité';

  @override
  String get clesQuittentLaMemoire =>
      'Les clés quittent la mémoire ; la session reste ouverte.';

  @override
  String get sceauBiometrique => 'Ouverture biométrique';

  @override
  String sceauPose(String biometrie) {
    return 'Scellée, relisible par $biometrie seul.';
  }

  @override
  String get sceauAbsent =>
      'Rien n\'est scellé. La proposition revient au prochain déverrouillage.';

  @override
  String get sceauInvalide =>
      'Le sceau n\'est plus lisible : une biométrie a été ajoutée ou retirée sur cet appareil. Retapez votre phrase au prochain déverrouillage.';

  @override
  String get sceauIndetermine =>
      'L\'état du sceau n\'a pas pu être lu. Ce n\'est ni un oui ni un non : le magasin n\'a pas répondu.';

  @override
  String get sansBiometrieSurCetAppareil =>
      'Aucune biométrie utilisable sur cet appareil.';

  @override
  String get retirerLeSceau => 'Retirer le sceau';

  @override
  String get sceauRetire =>
      'Le sceau a été retiré. La phrase sera redemandée au prochain déverrouillage.';

  @override
  String coffreFermePourOrganisation(String role) {
    return '$role · coffre fermé pour cette organisation';
  }

  @override
  String get disponibilites => 'Disponibilités';

  @override
  String get aucunHoraire => 'Aucun horaire';

  @override
  String get horairesDepuisLeWeb => 'Ils se définissent depuis le web.';

  @override
  String get seDeconnecter => 'Se déconnecter';

  @override
  String aucunePlage(String fuseau) {
    return 'Aucune plage · $fuseau';
  }

  @override
  String get aVenir => 'À venir';

  @override
  String get passees => 'Passées';

  @override
  String get aucuneReunionAVenir => 'Aucune réunion à venir.';

  @override
  String get aucuneReunionPassee => 'Aucune réunion passée.';

  @override
  String get annulee => 'Annulée';

  @override
  String get identiteIllisible => 'Identité illisible — clé manquante';

  @override
  String get inviteInconnu => 'Invité inconnu';

  @override
  String fuseauDeLInvite(String fuseau) {
    return 'Fuseau de l’invité : $fuseau';
  }

  @override
  String get reponses => 'RÉPONSES';

  @override
  String get annulerCetteReunion => 'Annuler cette réunion ?';

  @override
  String get invitePrevenuParServeur =>
      'L’invité en sera informé par le serveur.';

  @override
  String get annulerLaReunion => 'Annuler la réunion';

  @override
  String get clos => 'clos';

  @override
  String creneauxRetenus(int nombre) {
    String _temp0 = intl.Intl.pluralLogic(
      nombre,
      locale: localeName,
      other: '$nombre créneaux retenus',
      one: '$nombre créneau retenu',
    );
    return '$_temp0';
  }

  @override
  String get sondages => 'Sondages';

  @override
  String get aucunSondage => 'Aucun sondage.';

  @override
  String creneauxEtVotes(int creneaux, int votes) {
    return '$creneaux créneaux · $votes votes';
  }

  @override
  String get retenirCeCreneauQuestion => 'Retenir ce créneau ?';

  @override
  String sondageSeFermeEtEvenementCree(String date) {
    return 'Le sondage se ferme et l’événement est créé le $date.';
  }

  @override
  String get supprimerLeSondage => 'Supprimer le sondage';

  @override
  String get creneaux => 'Créneaux';

  @override
  String nombreDeCreneaux(int nombre) {
    String _temp0 = intl.Intl.pluralLogic(
      nombre,
      locale: localeName,
      other: '$nombre créneaux',
      one: '$nombre créneau',
    );
    return '$_temp0';
  }

  @override
  String get creneauRetenu => 'Créneau retenu';

  @override
  String get retenirCeCreneau => 'Retenir ce créneau';

  @override
  String get supprimerCeSondage => 'Supprimer ce sondage ?';

  @override
  String get votesPerdus => 'Les votes déjà exprimés seront perdus.';

  @override
  String get masquerLesFaites => 'Masquer les faites';

  @override
  String get nouvelleTache => 'Nouvelle tâche';

  @override
  String get aucuneTache => 'Aucune tâche.';

  @override
  String get rienAFaire => 'Rien à faire.';

  @override
  String get supprimerCetteTache => 'Supprimer cette tâche ?';

  @override
  String get sansEcheance => 'Sans échéance';

  @override
  String get retirerLEcheance => 'Retirer l\'échéance';

  @override
  String get rendezVous => 'Rendez-vous';

  @override
  String get aucunTypeDeRendezVous => 'Aucun type de rendez-vous.';

  @override
  String get typesCreesDepuisLeWeb =>
      'Ils se créent depuis le web : une quinzaine de réglages qui se règlent mal à un pouce.';

  @override
  String get ferme => 'fermé';

  @override
  String get copierLeLienDeReservation => 'Copier le lien de réservation';

  @override
  String lienCopie(String lien) {
    return 'Lien copié : $lien';
  }

  @override
  String serveurARepondu(int code) {
    return 'Le serveur a répondu $code.';
  }

  @override
  String get phraseNOuvrePas => 'Cette phrase n\'ouvre pas le coffre.';

  @override
  String get coffreFermeChiffrementImpossible =>
      'Le coffre est fermé : impossible de chiffrer ce contenu.';

  @override
  String get adresseDeServeurInvalide => 'Adresse de serveur invalide.';

  @override
  String get sessionExpiree => 'La session a expiré. Reconnectez-vous.';

  @override
  String get roleProprietaire => 'Propriétaire';

  @override
  String get roleAdministrateur => 'Administrateur';

  @override
  String get roleMembre => 'Membre';

  @override
  String get invitePromptTitre => 'Ouvrir le coffre';

  @override
  String get invitePromptRefus => 'Utiliser la phrase';

  @override
  String get verrouillageImmediat => 'Immédiatement';

  @override
  String get verrouillage1Minute => 'Après 1 minute';

  @override
  String get verrouillage5Minutes => 'Après 5 minutes';

  @override
  String get verrouillage15Minutes => 'Après 15 minutes';

  @override
  String get codeDeVerification => 'Code de vérification';

  @override
  String get codeDeVerificationAide =>
      'Votre compte demande un second facteur. Entrez le code affiché par votre application d\'authentification.';

  @override
  String get codeDeVerificationRefuse =>
      'Ce code n\'a pas été accepté. Le suivant sera peut-être le bon : ils changent toutes les trente secondes.';

  @override
  String codeDeVerificationBloque(String heure) {
    return 'Trop d\'essais. Le serveur refusera jusqu\'à $heure.';
  }

  @override
  String get valider => 'Valider';

  @override
  String get revenir => 'Revenir';
}
