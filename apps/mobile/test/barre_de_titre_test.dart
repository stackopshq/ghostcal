import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:ghostcal/ecrans/barre_de_titre.dart';
import 'package:ghostcal/l10n/generated/app_localisations.dart';
import 'package:ghostcal/main.dart';
import 'package:ghostcal/services/vue_agenda.dart';
import 'package:ghostcal/services/session.dart';
import 'package:ghostcal/theme.dart';
import 'package:ghostcal/services/verrouillage.dart' as v;

/// Ce qui est poussé par-dessus l'accueil doit commencer **sous** la barre de titre.
///
/// ─── Le défaut que ce témoin garde ───
///
/// `MainFlutterWindow` rend la barre de titre transparente et fait passer la vue Flutter
/// dessous, pour que la barre d'outils de l'accueil se tienne sur la même ligne que les
/// trois pastilles de la fenêtre. Tout écran poussé héritait de cela sans l'avoir
/// demandé : il commençait à y = 0, et sa flèche de retour se posait exactement sous les
/// pastilles — mesurées à x = 18 … 80 sur la machine.
///
/// Le bouton restait visible et devenait inatteignable. Rien ne le disait : ni erreur,
/// ni avertissement, ni débordement. Vu en capture, pas en test.
void main() {
  Widget pousse(Widget suivant) => Builder(
    builder: (context) => Scaffold(
      body: Center(
        child: TextButton(
          onPressed: () =>
              Navigator.of(context)
                  .push(MaterialPageRoute<void>(builder: (_) => suivant)),
          child: const Text('ouvrir'),
        ),
      ),
    ),
  );

  Future<void> monter(WidgetTester tester, Widget accueil) => tester.pumpWidget(
    GhostcalApp(
      session: Session(),
      verrouillage: v.Verrouillage(),
      accueilDEpreuve: accueil,
    ),
  );

  testWidgets('sur macOS, un écran poussé descend sous les pastilles', (
    tester,
  ) async {
    // Remise dans le corps et non par `addTearDown` : la vérification d'invariants de
    // Flutter passe **avant** les démontages, et refuse une variable de débogage laissée
    // en place — « The value of a foundation debug variable was changed by the test ».
    debugDefaultTargetPlatformOverride = TargetPlatform.macOS;
    await monter(
      tester,
      pousse(
        Scaffold(
          appBar: AppBar(title: const Text('détail')),
          body: const SizedBox(),
        ),
      ),
    );
    await tester.tap(find.text('ouvrir'));
    await tester.pumpAndSettle();

    final fleche = tester.getRect(find.byType(BackButton));
    debugDefaultTargetPlatformOverride = null;
    expect(
      fleche.top,
      greaterThanOrEqualTo(52.0),
      reason:
          'la flèche de retour est sous les pastilles de la fenêtre, '
          'donc inatteignable',
    );
  });

  /// ─── L'encoche d'un iPad n'est pas une barre de titre ───
  ///
  /// La chrome de bureau s'allume à 900 points, donc sur un iPad dans les deux
  /// orientations. Mais seul macOS fait passer la vue sous la barre de titre, et seul
  /// macOS a des pastilles à éviter. L'accueil retirait pourtant la marge haute dès que
  /// la chrome s'allumait : sur iPad, où rien n'avait été ajouté, ce retrait emportait
  /// l'encoche réelle de la barre d'état, et l'heure du système se posait par-dessus la
  /// barre d'outils.
  ///
  /// Trouvé en lisant le code, pas sur une capture.
  ///
  /// La règle s'éprouve seule et non à travers l'écran : la première version de ce
  /// témoin montait `GhostcalApp` avec un `accueilDEpreuve`, qui **remplace** l'accueil
  /// — le code à garder n'était jamais exécuté, et le témoin passait au vert avec le
  /// défaut remis en place. Un témoin qui ne mord pas est pire qu'absent : il dit que
  /// la question est réglée.
  group('la barre de titre traversée est une affaire de plateforme', () {
    test('un Mac large y passe', () {
      expect(
        Mesures.dansLaBarreDeTitre(
          bureau: true,
          plateforme: TargetPlatform.macOS,
        ),
        isTrue,
      );
    });

    test('un iPad large, non — son encoche lui appartient', () {
      expect(
        Mesures.dansLaBarreDeTitre(
          bureau: true,
          plateforme: TargetPlatform.iOS,
        ),
        isFalse,
        reason: "retirer sa marge haute pose l'heure du système sur la barre d'outils",
      );
      expect(
        Mesures.dansLaBarreDeTitre(
          bureau: true,
          plateforme: TargetPlatform.android,
        ),
        isFalse,
      );
    });

    test('et un Mac étroit non plus : il n\'a pas de barre d\'outils', () {
      expect(
        Mesures.dansLaBarreDeTitre(
          bureau: false,
          plateforme: TargetPlatform.macOS,
        ),
        isFalse,
      );
    });
  });

  /// La même application sur un téléphone ne doit pas gagner 52 points de vide : la
  /// barre de titre n'existe que sur macOS, et réserver sa place ailleurs serait un
  /// bandeau sans raison en haut de chaque écran.
  testWidgets('et nulle part ailleurs', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    await monter(
      tester,
      pousse(
        Scaffold(
          appBar: AppBar(title: const Text('détail')),
          body: const SizedBox(),
        ),
      ),
    );
    await tester.tap(find.text('ouvrir'));
    await tester.pumpAndSettle();

    final haut = tester.getRect(find.byType(BackButton)).top;
    debugDefaultTargetPlatformOverride = null;
    expect(haut, lessThan(52.0));
  });

  /// ─── Le défaut que ce groupe garde, et pourquoi les deux premiers témoins ne le
  /// gardaient pas ───
  ///
  /// La barre d'outils du bureau se dessinait par-dessus l'heure de l'iPad. Deux fois :
  /// d'abord parce que l'accueil retirait la marge haute dès que la chrome de bureau
  /// s'allumait — ce que le groupe ci-dessus garde maintenant —, puis parce que la marge
  /// était bien **préservée** et que personne ne la **lisait**. Un `PreferredSizeWidget`
  /// ordinaire n'est pas un `AppBar` : il se pose à y = 0 quoi qu'il arrive.
  ///
  /// Les témoins du dessus sont restés verts les deux fois, et c'est structurel : une
  /// fonction pure reste verte quand le défaut est de ne **pas** l'appeler. Or c'était
  /// exactement le défaut. Il faut donc mesurer la boîte rendue, et pas le calcul.
  ///
  /// La barre est montée dans l'`appBar` d'un `Scaffold`, et non seule : c'est ce qui
  /// éprouve les **deux** moitiés d'un coup. Le `Scaffold` alloue `preferredSize`, et la
  /// barre dessine sa propre hauteur dedans — si l'une des deux oublie l'encoche, la
  /// hauteur rendue le dit, ou le rendu déborde.
  group('la barre d\'outils laisse la place à la barre d\'état', () {
    /// 44 points : l'encoche d'un iPad Pro. La valeur exacte importe peu, qu'elle ne
    /// soit ni nulle ni égale à la hauteur de la barre importe beaucoup — sinon un
    /// « 52 » de trop ou de pas assez passerait inaperçu.
    const encoche = 44.0;

    Future<Rect> rendue(
      WidgetTester tester, {
      required TargetPlatform plateforme,
    }) async {
      tester.view.physicalSize = const Size(1200 * 2, 900 * 2);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(
        MaterialApp(
          locale: const Locale('fr'),
          localizationsDelegates: const [
            ...L.localizationsDelegates,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
          ],
          supportedLocales: L.supportedLocales,
          theme: themeGhostcal(Brightness.light),
          home: MediaQuery(
            data: const MediaQueryData(
              size: Size(1200, 900),
              padding: EdgeInsets.only(top: encoche),
            ),
            child: Builder(
              builder: (context) => Scaffold(
                appBar: BarreDeTitreDeBureau(
                  // Le même appel que fait l'accueil : un témoin qui calculerait
                  // l'encoche lui-même ne garderait que son propre calcul.
                  encoche: BarreDeTitreDeBureau.encocheSelon(
                    context,
                    plateforme,
                  ),
                  vue: VueDAgenda.jour,
                  surVue: (_) {},
                  surRecherche: () {},
                  peutCreer: true,
                  surNouveau: () {},
                ),
                body: const SizedBox(key: Key('epreuve.corps')),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(
        tester.takeException(),
        isNull,
        reason: 'la barre déborde de la place que le Scaffold lui donne',
      );
      return tester.getRect(find.byType(BarreDeTitreDeBureau));
    }

    /// Où commence le corps : la barre ne doit pas le recouvrir.
    ///
    /// ─── Ce que ce témoin ne garde pas, et pourquoi ───
    ///
    /// Un `preferredSize` faux **ne se voit pas ici**, et aucune mesure ne l'attrape :
    /// `_ScaffoldLayout` dispose son `appBar` sous des contraintes de hauteur libres,
    /// puis place le corps sous la hauteur **rendue**. Le `preferredSize` ne sert donc à
    /// rien dans cette mise en page — vérifié en le remettant à `hauteur` seule : les
    /// huit témoins restaient verts, y compris celui-ci.
    ///
    /// Ce n'est pas une lacune qu'on se résigne à avoir, c'est l'absence de défaut : la
    /// barre n'est utilisée qu'en `Scaffold.appBar`, et ce chemin-là ne lit pas le
    /// nombre. Il reste juste parce que c'est le contrat du type, pas parce que l'écran
    /// en dépend. Si elle sert un jour ailleurs — un `NestedScrollView`, une
    /// `FlexibleSpaceBar` —, il faudra un témoin pour **ce** chemin.
    double hautDuCorps(WidgetTester tester) =>
        tester.getRect(find.byKey(const Key('epreuve.corps'))).top;

    testWidgets('sur un iPad, elle descend de toute l\'encoche', (
      tester,
    ) async {
      final boite = await rendue(tester, plateforme: TargetPlatform.iOS);
      expect(
        boite.height,
        BarreDeTitreDeBureau.hauteur + encoche,
        reason:
            "l'heure, le wifi et la batterie se posent sur la barre d'outils",
      );
      // La bande du haut est la marge, pas de la barre : les commandes commencent après.
      expect(
        tester.getRect(find.byKey(const Key('bureau.vues'))).top,
        greaterThanOrEqualTo(encoche),
        reason: 'le segmenté est dans la barre d\'état',
      );
      expect(
        hautDuCorps(tester),
        BarreDeTitreDeBureau.hauteur + encoche,
        reason: 'la barre recouvre le haut du corps',
      );
    });

    testWidgets('sur un Mac, non : la marge est la barre de titre', (
      tester,
    ) async {
      final boite = await rendue(tester, plateforme: TargetPlatform.macOS);
      expect(
        boite.height,
        BarreDeTitreDeBureau.hauteur,
        reason:
            'la marge haute de macOS est la barre de titre que la barre occupe déjà ; '
            's\'y ajouter laisserait la bande vide qu\'on a justement enlevée',
      );
      expect(hautDuCorps(tester), BarreDeTitreDeBureau.hauteur);
    });

    /// Le bord gauche appartient aux trois pastilles de la fenêtre. Un bouton qui s'y
    /// pose reste visible et devient inatteignable, sans qu'aucune erreur le dise.
    testWidgets('et le premier élément ne touche pas les pastilles', (
      tester,
    ) async {
      await rendue(tester, plateforme: TargetPlatform.macOS);
      expect(
        tester.getRect(find.byKey(const Key('bureau.vues'))).left,
        greaterThanOrEqualTo(80.0),
        reason: 'mesurées à x = 18 … 80 sur la machine',
      );
    });
  });
}
