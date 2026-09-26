import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localisations_en.dart';
import 'app_localisations_fr.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of L
/// returned by `L.of(context)`.
///
/// Applications need to include `L.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localisations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: L.localizationsDelegates,
///   supportedLocales: L.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the L.supportedLocales
/// property.
abstract class L {
  L(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static L of(BuildContext context) {
    return Localizations.of<L>(context, L)!;
  }

  static const LocalizationsDelegate<L> delegate = _LDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('fr'),
  ];

  /// No description provided for @ongletAgenda.
  ///
  /// In fr, this message translates to:
  /// **'Agenda'**
  String get ongletAgenda;

  /// No description provided for @ongletTaches.
  ///
  /// In fr, this message translates to:
  /// **'Tâches'**
  String get ongletTaches;

  /// No description provided for @ongletReunions.
  ///
  /// In fr, this message translates to:
  /// **'Réunions'**
  String get ongletReunions;

  /// No description provided for @ongletRdv.
  ///
  /// In fr, this message translates to:
  /// **'RDV'**
  String get ongletRdv;

  /// No description provided for @ongletReglages.
  ///
  /// In fr, this message translates to:
  /// **'Réglages'**
  String get ongletReglages;

  /// No description provided for @verrouillerLeCoffre.
  ///
  /// In fr, this message translates to:
  /// **'Verrouiller le coffre'**
  String get verrouillerLeCoffre;

  /// No description provided for @jourPrecedent.
  ///
  /// In fr, this message translates to:
  /// **'Jour précédent'**
  String get jourPrecedent;

  /// No description provided for @jourSuivant.
  ///
  /// In fr, this message translates to:
  /// **'Jour suivant'**
  String get jourSuivant;

  /// No description provided for @allerAUneDate.
  ///
  /// In fr, this message translates to:
  /// **'Aller à une date'**
  String get allerAUneDate;

  /// No description provided for @nouvelEvenement.
  ///
  /// In fr, this message translates to:
  /// **'Nouvel événement'**
  String get nouvelEvenement;

  /// No description provided for @modifierLEvenement.
  ///
  /// In fr, this message translates to:
  /// **'Modifier l\'événement'**
  String get modifierLEvenement;

  /// No description provided for @rienCeJourLa.
  ///
  /// In fr, this message translates to:
  /// **'Rien ce jour-là.'**
  String get rienCeJourLa;

  /// No description provided for @journee.
  ///
  /// In fr, this message translates to:
  /// **'Journée'**
  String get journee;

  /// Un événement ou une tâche que la clé du trousseau n'ouvre pas. La ligne reste affichée : une ligne absente se lirait « libre », ce qui serait faux.
  ///
  /// In fr, this message translates to:
  /// **'Contenu illisible — clé manquante'**
  String get contenuIllisible;

  /// No description provided for @sansTitre.
  ///
  /// In fr, this message translates to:
  /// **'Sans titre'**
  String get sansTitre;

  /// No description provided for @sceauIllisible.
  ///
  /// In fr, this message translates to:
  /// **'le sceau est illisible'**
  String get sceauIllisible;

  /// No description provided for @phraseScelleeObsolete.
  ///
  /// In fr, this message translates to:
  /// **'La phrase scellée n\'ouvre plus ce coffre — elle a sans doute changé depuis. Tapez-la pour la resceller.'**
  String get phraseScelleeObsolete;

  /// No description provided for @biometrieDesactivee.
  ///
  /// In fr, this message translates to:
  /// **'L\'ouverture par {biometrie} a été désactivée : le sceau posé sur cet appareil n\'est plus lisible — le plus souvent parce qu\'une biométrie y a été ajoutée ou retirée. Tapez votre phrase pour la rétablir.'**
  String biometrieDesactivee(String biometrie);

  /// No description provided for @magasinIllisible.
  ///
  /// In fr, this message translates to:
  /// **'Le magasin sécurisé n\'a pas pu être lu : {raison}.'**
  String magasinIllisible(String raison);

  /// Le troisième état du trousseau, celui qui n'est ni un succès ni un refus : la question n'a pas été posée. Le taire laisse une icône qui ne fait rien — la panne muette de GhostPass du 2026-09-25. La formulation dit explicitement que le sceau est intact, pour qu'on n'aille pas croire qu'il faut tout refaire.
  ///
  /// In fr, this message translates to:
  /// **'{biometrie} n\'a pas pu être demandé : l\'appareil n\'était pas en état de présenter la demande. Rien n\'a changé — touchez l\'icône dans un instant, ou tapez votre phrase.'**
  String biometriePasDemandee(String biometrie);

  /// No description provided for @raisonInconnue.
  ///
  /// In fr, this message translates to:
  /// **'raison inconnue'**
  String get raisonInconnue;

  /// No description provided for @laBiometrie.
  ///
  /// In fr, this message translates to:
  /// **'la biométrie'**
  String get laBiometrie;

  /// No description provided for @coffreEnregistre.
  ///
  /// In fr, this message translates to:
  /// **'Coffre enregistré sur cet appareil'**
  String get coffreEnregistre;

  /// No description provided for @agendaChiffre.
  ///
  /// In fr, this message translates to:
  /// **'Agenda chiffré de bout en bout'**
  String get agendaChiffre;

  /// No description provided for @deverrouiller.
  ///
  /// In fr, this message translates to:
  /// **'Déverrouiller'**
  String get deverrouiller;

  /// No description provided for @seConnecter.
  ///
  /// In fr, this message translates to:
  /// **'Se connecter'**
  String get seConnecter;

  /// No description provided for @ouvrirAvec.
  ///
  /// In fr, this message translates to:
  /// **'Ouvrir avec {biometrie}'**
  String ouvrirAvec(String biometrie);

  /// La seconde phrase vient de BiometricSetupView de GhostPass : sans elle, l'invalidation au prochain enrôlement ressemble à une panne. Annoncée d'avance, c'est une garantie.
  ///
  /// In fr, this message translates to:
  /// **'La phrase est scellée sur cet appareil, relisible par {biometrie} seul. Ajouter ou retirer un visage ou une empreinte annule cet accès.'**
  String phraseSceleeSurAppareil(String biometrie);

  /// No description provided for @afficherLaPhrase.
  ///
  /// In fr, this message translates to:
  /// **'Afficher la phrase'**
  String get afficherLaPhrase;

  /// No description provided for @masquerLaPhrase.
  ///
  /// In fr, this message translates to:
  /// **'Masquer la phrase'**
  String get masquerLaPhrase;

  /// No description provided for @connecteMaisCoffreFerme.
  ///
  /// In fr, this message translates to:
  /// **'Vous êtes connecté, mais le coffre est resté fermé : {raison}'**
  String connecteMaisCoffreFerme(String raison);

  /// No description provided for @phraseNOuvrePasLeCoffre.
  ///
  /// In fr, this message translates to:
  /// **'cette phrase n\'ouvre pas le coffre'**
  String get phraseNOuvrePasLeCoffre;

  /// No description provided for @serveur.
  ///
  /// In fr, this message translates to:
  /// **'Serveur'**
  String get serveur;

  /// No description provided for @adresseElectronique.
  ///
  /// In fr, this message translates to:
  /// **'Adresse e-mail'**
  String get adresseElectronique;

  /// No description provided for @exempleAdresse.
  ///
  /// In fr, this message translates to:
  /// **'vous@exemple.ch'**
  String get exempleAdresse;

  /// No description provided for @retenirCetAppareil.
  ///
  /// In fr, this message translates to:
  /// **'Retenir cet appareil'**
  String get retenirCetAppareil;

  /// No description provided for @utiliserMonMotDePasse.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser mon mot de passe'**
  String get utiliserMonMotDePasse;

  /// No description provided for @utiliserMaPhraseDeRecuperation.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser ma phrase de récupération'**
  String get utiliserMaPhraseDeRecuperation;

  /// No description provided for @utiliserUnAutreCompte.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser un autre compte'**
  String get utiliserUnAutreCompte;

  /// No description provided for @phraseDeRecuperation.
  ///
  /// In fr, this message translates to:
  /// **'Phrase de récupération'**
  String get phraseDeRecuperation;

  /// No description provided for @motDePasseMaitre.
  ///
  /// In fr, this message translates to:
  /// **'Mot de passe maître'**
  String get motDePasseMaitre;

  /// No description provided for @votreMotDePasse.
  ///
  /// In fr, this message translates to:
  /// **'Votre mot de passe'**
  String get votreMotDePasse;

  /// No description provided for @ouvrirLeCoffre.
  ///
  /// In fr, this message translates to:
  /// **'Ouvrir le coffre'**
  String get ouvrirLeCoffre;

  /// No description provided for @utiliserLaPhrase.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser la phrase'**
  String get utiliserLaPhrase;

  /// No description provided for @equipe.
  ///
  /// In fr, this message translates to:
  /// **'Équipe'**
  String get equipe;

  /// No description provided for @retirerDeLEquipe.
  ///
  /// In fr, this message translates to:
  /// **'Retirer de l\'équipe'**
  String get retirerDeLEquipe;

  /// No description provided for @perteDAccesOrganisation.
  ///
  /// In fr, this message translates to:
  /// **'Cette personne perdra l’accès aux calendriers de l’organisation.'**
  String get perteDAccesOrganisation;

  /// No description provided for @proprietaire.
  ///
  /// In fr, this message translates to:
  /// **'Propriétaire'**
  String get proprietaire;

  /// No description provided for @contenuNonDechiffre.
  ///
  /// In fr, this message translates to:
  /// **'Le contenu de cet événement n\'a pas pu être déchiffré. L\'enregistrer remplacerait un titre que vous n\'avez pas pu lire.'**
  String get contenuNonDechiffre;

  /// No description provided for @finAvantDebut.
  ///
  /// In fr, this message translates to:
  /// **'La fin est avant le début.'**
  String get finAvantDebut;

  /// No description provided for @supprimerCetEvenement.
  ///
  /// In fr, this message translates to:
  /// **'Supprimer cet événement ?'**
  String get supprimerCetEvenement;

  /// No description provided for @disparaitraPourTous.
  ///
  /// In fr, this message translates to:
  /// **'Il disparaîtra pour tous les participants.'**
  String get disparaitraPourTous;

  /// No description provided for @titre.
  ///
  /// In fr, this message translates to:
  /// **'Titre'**
  String get titre;

  /// No description provided for @lieu.
  ///
  /// In fr, this message translates to:
  /// **'Lieu'**
  String get lieu;

  /// No description provided for @description.
  ///
  /// In fr, this message translates to:
  /// **'Description'**
  String get description;

  /// No description provided for @journeeEntiere.
  ///
  /// In fr, this message translates to:
  /// **'Journée entière'**
  String get journeeEntiere;

  /// No description provided for @debut.
  ///
  /// In fr, this message translates to:
  /// **'Début'**
  String get debut;

  /// No description provided for @fin.
  ///
  /// In fr, this message translates to:
  /// **'Fin'**
  String get fin;

  /// No description provided for @calendrier.
  ///
  /// In fr, this message translates to:
  /// **'Calendrier'**
  String get calendrier;

  /// No description provided for @enregistrer.
  ///
  /// In fr, this message translates to:
  /// **'Enregistrer'**
  String get enregistrer;

  /// No description provided for @supprimer.
  ///
  /// In fr, this message translates to:
  /// **'Supprimer'**
  String get supprimer;

  /// No description provided for @annuler.
  ///
  /// In fr, this message translates to:
  /// **'Annuler'**
  String get annuler;

  /// No description provided for @creer.
  ///
  /// In fr, this message translates to:
  /// **'Créer'**
  String get creer;

  /// La phrase centrale du produit. Elle dit ce qui est chiffré ET ce qui ne l'est pas ; l'abréger en « tout est chiffré » serait faux.
  ///
  /// In fr, this message translates to:
  /// **'Le titre, le lieu et la description sont chiffrés sur cet appareil. Les heures partent en clair : sans elles, le serveur ne pourrait ni répondre « occupé » à un lien de réservation, ni envoyer de rappel.'**
  String get ceQuiEstChiffre;

  /// No description provided for @profil.
  ///
  /// In fr, this message translates to:
  /// **'Profil'**
  String get profil;

  /// No description provided for @profilEnregistre.
  ///
  /// In fr, this message translates to:
  /// **'Profil enregistré.'**
  String get profilEnregistre;

  /// No description provided for @nonVerifiee.
  ///
  /// In fr, this message translates to:
  /// **'non vérifiée'**
  String get nonVerifiee;

  /// No description provided for @changementDAdresseParLeWeb.
  ///
  /// In fr, this message translates to:
  /// **'La changer demande une vérification, qui se fait depuis le web.'**
  String get changementDAdresseParLeWeb;

  /// No description provided for @utiliserLeFuseauDeLAppareil.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser le fuseau de cet appareil'**
  String get utiliserLeFuseauDeLAppareil;

  /// No description provided for @retirerLaPhoto.
  ///
  /// In fr, this message translates to:
  /// **'Retirer la photo'**
  String get retirerLaPhoto;

  /// No description provided for @photoEffaceeALEnregistrement.
  ///
  /// In fr, this message translates to:
  /// **'Elle sera effacée à l’enregistrement.'**
  String get photoEffaceeALEnregistrement;

  /// No description provided for @securite.
  ///
  /// In fr, this message translates to:
  /// **'Sécurité'**
  String get securite;

  /// No description provided for @clesQuittentLaMemoire.
  ///
  /// In fr, this message translates to:
  /// **'Les clés quittent la mémoire ; la session reste ouverte.'**
  String get clesQuittentLaMemoire;

  /// Le titre de la ligne des réglages qui dit l'état du sceau. « Ouverture » et non « Activation » : on ne bascule pas un réglage, on constate ce que le trousseau garde réellement.
  ///
  /// In fr, this message translates to:
  /// **'Ouverture biométrique'**
  String get sceauBiometrique;

  /// No description provided for @sceauPose.
  ///
  /// In fr, this message translates to:
  /// **'Scellée, relisible par {biometrie} seul.'**
  String sceauPose(String biometrie);

  /// No description provided for @sceauAbsent.
  ///
  /// In fr, this message translates to:
  /// **'Rien n\'est scellé. La proposition revient au prochain déverrouillage.'**
  String get sceauAbsent;

  /// No description provided for @sceauInvalide.
  ///
  /// In fr, this message translates to:
  /// **'Le sceau n\'est plus lisible : une biométrie a été ajoutée ou retirée sur cet appareil. Retapez votre phrase au prochain déverrouillage.'**
  String get sceauInvalide;

  /// Le troisième état, jusque dans les réglages. Afficher « désactivé » ici serait affirmer une chose qu'on n'a pas vérifiée — c'est exactement le réglage menteur de GhostPass le 2026-09-25.
  ///
  /// In fr, this message translates to:
  /// **'L\'état du sceau n\'a pas pu être lu. Ce n\'est ni un oui ni un non : le magasin n\'a pas répondu.'**
  String get sceauIndetermine;

  /// No description provided for @sansBiometrieSurCetAppareil.
  ///
  /// In fr, this message translates to:
  /// **'Aucune biométrie utilisable sur cet appareil.'**
  String get sansBiometrieSurCetAppareil;

  /// No description provided for @retirerLeSceau.
  ///
  /// In fr, this message translates to:
  /// **'Retirer le sceau'**
  String get retirerLeSceau;

  /// No description provided for @sceauRetire.
  ///
  /// In fr, this message translates to:
  /// **'Le sceau a été retiré. La phrase sera redemandée au prochain déverrouillage.'**
  String get sceauRetire;

  /// No description provided for @coffreFermePourOrganisation.
  ///
  /// In fr, this message translates to:
  /// **'{role} · coffre fermé pour cette organisation'**
  String coffreFermePourOrganisation(String role);

  /// No description provided for @disponibilites.
  ///
  /// In fr, this message translates to:
  /// **'Disponibilités'**
  String get disponibilites;

  /// No description provided for @aucunHoraire.
  ///
  /// In fr, this message translates to:
  /// **'Aucun horaire'**
  String get aucunHoraire;

  /// No description provided for @horairesDepuisLeWeb.
  ///
  /// In fr, this message translates to:
  /// **'Ils se définissent depuis le web.'**
  String get horairesDepuisLeWeb;

  /// No description provided for @seDeconnecter.
  ///
  /// In fr, this message translates to:
  /// **'Se déconnecter'**
  String get seDeconnecter;

  /// No description provided for @aucunePlage.
  ///
  /// In fr, this message translates to:
  /// **'Aucune plage · {fuseau}'**
  String aucunePlage(String fuseau);

  /// No description provided for @aVenir.
  ///
  /// In fr, this message translates to:
  /// **'À venir'**
  String get aVenir;

  /// No description provided for @passees.
  ///
  /// In fr, this message translates to:
  /// **'Passées'**
  String get passees;

  /// No description provided for @aucuneReunionAVenir.
  ///
  /// In fr, this message translates to:
  /// **'Aucune réunion à venir.'**
  String get aucuneReunionAVenir;

  /// No description provided for @aucuneReunionPassee.
  ///
  /// In fr, this message translates to:
  /// **'Aucune réunion passée.'**
  String get aucuneReunionPassee;

  /// No description provided for @annulee.
  ///
  /// In fr, this message translates to:
  /// **'Annulée'**
  String get annulee;

  /// No description provided for @identiteIllisible.
  ///
  /// In fr, this message translates to:
  /// **'Identité illisible — clé manquante'**
  String get identiteIllisible;

  /// No description provided for @inviteInconnu.
  ///
  /// In fr, this message translates to:
  /// **'Invité inconnu'**
  String get inviteInconnu;

  /// No description provided for @fuseauDeLInvite.
  ///
  /// In fr, this message translates to:
  /// **'Fuseau de l’invité : {fuseau}'**
  String fuseauDeLInvite(String fuseau);

  /// No description provided for @reponses.
  ///
  /// In fr, this message translates to:
  /// **'RÉPONSES'**
  String get reponses;

  /// No description provided for @annulerCetteReunion.
  ///
  /// In fr, this message translates to:
  /// **'Annuler cette réunion ?'**
  String get annulerCetteReunion;

  /// No description provided for @invitePrevenuParServeur.
  ///
  /// In fr, this message translates to:
  /// **'L’invité en sera informé par le serveur.'**
  String get invitePrevenuParServeur;

  /// No description provided for @annulerLaReunion.
  ///
  /// In fr, this message translates to:
  /// **'Annuler la réunion'**
  String get annulerLaReunion;

  /// No description provided for @clos.
  ///
  /// In fr, this message translates to:
  /// **'clos'**
  String get clos;

  /// No description provided for @creneauxRetenus.
  ///
  /// In fr, this message translates to:
  /// **'{nombre, plural, one{{nombre} créneau retenu} other{{nombre} créneaux retenus}}'**
  String creneauxRetenus(int nombre);

  /// No description provided for @sondages.
  ///
  /// In fr, this message translates to:
  /// **'Sondages'**
  String get sondages;

  /// No description provided for @aucunSondage.
  ///
  /// In fr, this message translates to:
  /// **'Aucun sondage.'**
  String get aucunSondage;

  /// No description provided for @creneauxEtVotes.
  ///
  /// In fr, this message translates to:
  /// **'{creneaux} créneaux · {votes} votes'**
  String creneauxEtVotes(int creneaux, int votes);

  /// No description provided for @retenirCeCreneauQuestion.
  ///
  /// In fr, this message translates to:
  /// **'Retenir ce créneau ?'**
  String get retenirCeCreneauQuestion;

  /// No description provided for @sondageSeFermeEtEvenementCree.
  ///
  /// In fr, this message translates to:
  /// **'Le sondage se ferme et l’événement est créé le {date}.'**
  String sondageSeFermeEtEvenementCree(String date);

  /// No description provided for @supprimerLeSondage.
  ///
  /// In fr, this message translates to:
  /// **'Supprimer le sondage'**
  String get supprimerLeSondage;

  /// No description provided for @creneaux.
  ///
  /// In fr, this message translates to:
  /// **'Créneaux'**
  String get creneaux;

  /// No description provided for @nombreDeCreneaux.
  ///
  /// In fr, this message translates to:
  /// **'{nombre, plural, one{{nombre} créneau} other{{nombre} créneaux}}'**
  String nombreDeCreneaux(int nombre);

  /// No description provided for @creneauRetenu.
  ///
  /// In fr, this message translates to:
  /// **'Créneau retenu'**
  String get creneauRetenu;

  /// No description provided for @retenirCeCreneau.
  ///
  /// In fr, this message translates to:
  /// **'Retenir ce créneau'**
  String get retenirCeCreneau;

  /// No description provided for @supprimerCeSondage.
  ///
  /// In fr, this message translates to:
  /// **'Supprimer ce sondage ?'**
  String get supprimerCeSondage;

  /// No description provided for @votesPerdus.
  ///
  /// In fr, this message translates to:
  /// **'Les votes déjà exprimés seront perdus.'**
  String get votesPerdus;

  /// No description provided for @masquerLesFaites.
  ///
  /// In fr, this message translates to:
  /// **'Masquer les faites'**
  String get masquerLesFaites;

  /// No description provided for @nouvelleTache.
  ///
  /// In fr, this message translates to:
  /// **'Nouvelle tâche'**
  String get nouvelleTache;

  /// No description provided for @aucuneTache.
  ///
  /// In fr, this message translates to:
  /// **'Aucune tâche.'**
  String get aucuneTache;

  /// No description provided for @rienAFaire.
  ///
  /// In fr, this message translates to:
  /// **'Rien à faire.'**
  String get rienAFaire;

  /// No description provided for @supprimerCetteTache.
  ///
  /// In fr, this message translates to:
  /// **'Supprimer cette tâche ?'**
  String get supprimerCetteTache;

  /// No description provided for @sansEcheance.
  ///
  /// In fr, this message translates to:
  /// **'Sans échéance'**
  String get sansEcheance;

  /// No description provided for @retirerLEcheance.
  ///
  /// In fr, this message translates to:
  /// **'Retirer l\'échéance'**
  String get retirerLEcheance;

  /// No description provided for @rendezVous.
  ///
  /// In fr, this message translates to:
  /// **'Rendez-vous'**
  String get rendezVous;

  /// No description provided for @aucunTypeDeRendezVous.
  ///
  /// In fr, this message translates to:
  /// **'Aucun type de rendez-vous.'**
  String get aucunTypeDeRendezVous;

  /// No description provided for @typesCreesDepuisLeWeb.
  ///
  /// In fr, this message translates to:
  /// **'Ils se créent depuis le web : une quinzaine de réglages qui se règlent mal à un pouce.'**
  String get typesCreesDepuisLeWeb;

  /// No description provided for @ferme.
  ///
  /// In fr, this message translates to:
  /// **'fermé'**
  String get ferme;

  /// No description provided for @copierLeLienDeReservation.
  ///
  /// In fr, this message translates to:
  /// **'Copier le lien de réservation'**
  String get copierLeLienDeReservation;

  /// No description provided for @lienCopie.
  ///
  /// In fr, this message translates to:
  /// **'Lien copié : {lien}'**
  String lienCopie(String lien);

  /// No description provided for @serveurARepondu.
  ///
  /// In fr, this message translates to:
  /// **'Le serveur a répondu {code}.'**
  String serveurARepondu(int code);

  /// No description provided for @phraseNOuvrePas.
  ///
  /// In fr, this message translates to:
  /// **'Cette phrase n\'ouvre pas le coffre.'**
  String get phraseNOuvrePas;

  /// No description provided for @coffreFermeChiffrementImpossible.
  ///
  /// In fr, this message translates to:
  /// **'Le coffre est fermé : impossible de chiffrer ce contenu.'**
  String get coffreFermeChiffrementImpossible;

  /// No description provided for @adresseDeServeurInvalide.
  ///
  /// In fr, this message translates to:
  /// **'Adresse de serveur invalide.'**
  String get adresseDeServeurInvalide;

  /// No description provided for @sessionExpiree.
  ///
  /// In fr, this message translates to:
  /// **'La session a expiré. Reconnectez-vous.'**
  String get sessionExpiree;

  /// No description provided for @roleProprietaire.
  ///
  /// In fr, this message translates to:
  /// **'Propriétaire'**
  String get roleProprietaire;

  /// No description provided for @roleAdministrateur.
  ///
  /// In fr, this message translates to:
  /// **'Administrateur'**
  String get roleAdministrateur;

  /// No description provided for @roleMembre.
  ///
  /// In fr, this message translates to:
  /// **'Membre'**
  String get roleMembre;

  /// No description provided for @invitePromptTitre.
  ///
  /// In fr, this message translates to:
  /// **'Ouvrir le coffre'**
  String get invitePromptTitre;

  /// No description provided for @invitePromptRefus.
  ///
  /// In fr, this message translates to:
  /// **'Utiliser la phrase'**
  String get invitePromptRefus;

  /// No description provided for @verrouillageImmediat.
  ///
  /// In fr, this message translates to:
  /// **'Immédiatement'**
  String get verrouillageImmediat;

  /// No description provided for @verrouillage1Minute.
  ///
  /// In fr, this message translates to:
  /// **'Après 1 minute'**
  String get verrouillage1Minute;

  /// No description provided for @verrouillage5Minutes.
  ///
  /// In fr, this message translates to:
  /// **'Après 5 minutes'**
  String get verrouillage5Minutes;

  /// No description provided for @verrouillage15Minutes.
  ///
  /// In fr, this message translates to:
  /// **'Après 15 minutes'**
  String get verrouillage15Minutes;

  /// No description provided for @codeDeVerification.
  ///
  /// In fr, this message translates to:
  /// **'Code de vérification'**
  String get codeDeVerification;

  /// No description provided for @codeDeVerificationAide.
  ///
  /// In fr, this message translates to:
  /// **'Votre compte demande un second facteur. Entrez le code affiché par votre application d\'authentification.'**
  String get codeDeVerificationAide;

  /// No description provided for @codeDeVerificationRefuse.
  ///
  /// In fr, this message translates to:
  /// **'Ce code n\'a pas été accepté. Le suivant sera peut-être le bon : ils changent toutes les trente secondes.'**
  String get codeDeVerificationRefuse;

  /// Le 429 du serveur, qui dit jusqu'à quand. Sans cette heure, on réessaie en boucle une saisie qui ne peut pas aboutir.
  ///
  /// In fr, this message translates to:
  /// **'Trop d\'essais. Le serveur refusera jusqu\'à {heure}.'**
  String codeDeVerificationBloque(String heure);

  /// No description provided for @valider.
  ///
  /// In fr, this message translates to:
  /// **'Valider'**
  String get valider;

  /// No description provided for @revenir.
  ///
  /// In fr, this message translates to:
  /// **'Revenir'**
  String get revenir;
}

class _LDelegate extends LocalizationsDelegate<L> {
  const _LDelegate();

  @override
  Future<L> load(Locale locale) {
    return SynchronousFuture<L>(lookupL(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'fr'].contains(locale.languageCode);

  @override
  bool shouldReload(_LDelegate old) => false;
}

L lookupL(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return LEn();
    case 'fr':
      return LFr();
  }

  throw FlutterError(
    'L.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
