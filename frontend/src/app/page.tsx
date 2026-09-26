import { redirect } from "next/navigation";

// L'accueil est l'écran de connexion, comme dans GhostPass.
//
// Il présentait avant une page d'accroche : le nom, une phrase, « Commencer » et
// « Se connecter ». Elle était plus belle. Mais la personne qui tape l'adresse de
// GhostCal au quotidien vient se connecter, et devait cliquer une fois de plus pour
// atteindre le formulaire — chaque jour, pour lire une phrase qu'elle connaît.
//
// Une redirection plutôt qu'une copie du formulaire : deux pages qui rendent le même
// écran divergent, et c'est toujours celle qu'on regarde le moins qui prend du retard.
// `/login` reste l'adresse canonique, et les liens existants continuent de marcher.
//
// Le lien de démonstration vivait ici ; il a suivi dans le pied de la carte de
// connexion, sans quoi la variable `NEXT_PUBLIC_DEMO_PATH` serait devenue muette sans
// que personne le remarque.
export default function Home() {
  redirect("/login");
}
